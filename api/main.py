"""AI discoverability scanner API."""
from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

import db
from audit import Ctx, analyse, snapshot
from visibility import aggregate, configured_engines, generate_prompts, run_matrix

MAX_PROMPTS = 10
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

store = db.make_store()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await store.connect()
    yield
    await store.close()


app = FastAPI(title="AI Discoverability Scanner", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


class ScanRequest(BaseModel):
    url: str

    @field_validator("url")
    @classmethod
    def valid_public_url(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("url is required")
        if not urlparse(v).scheme:
            v = f"https://{v}"
        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("url must be http or https")
        host = (parsed.hostname or "").lower()
        # This endpoint fetches whatever it is given, so it must not be usable to
        # probe the internal network.
        if not host or host in ("localhost", "0.0.0.0") or host.endswith(".local") or host.endswith(".internal"):
            raise ValueError("url must be a public host")
        if re.match(r"^(127\.|10\.|192\.168\.|169\.254\.|172\.(1[6-9]|2\d|3[01])\.|\[?::1)", host):
            raise ValueError("url must be a public host")
        if "." not in host:
            raise ValueError("url must be a public host")
        return v


class PromptsRequest(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def valid_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not EMAIL_RE.match(v):
            raise ValueError("a valid email is required")
        return v


class LeadRequest(BaseModel):
    email: str
    message: str = ""

    @field_validator("email")
    @classmethod
    def valid_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not EMAIL_RE.match(v):
            raise ValueError("a valid email is required")
        return v

    @field_validator("message")
    @classmethod
    def trim(cls, v: str) -> str:
        return v.strip()[:2000]


class VisibilityRequest(BaseModel):
    brand: str = Field(min_length=1, max_length=120)
    prompts: list[str]

    @field_validator("prompts")
    @classmethod
    def clean(cls, v: list[str]) -> list[str]:
        out = [p.strip() for p in v if p.strip()][:MAX_PROMPTS]
        if not out:
            raise ValueError("at least one prompt is required")
        return out


@app.post("/api/scan")
async def create_scan(req: ScanRequest):
    """Deterministic audit. Synchronous, costs nothing, no email required."""
    try:
        ctx = Ctx(await snapshot(req.url))
    except Exception as e:
        raise HTTPException(422, f"Could not fetch {req.url}: {e}") from e

    result = analyse(ctx)

    scan_id = db.new_id()
    await store.create(
        id=scan_id,
        url=ctx.snap.final_url,
        brand_name=ctx.brand,
        status="audited",
        page_excerpt=ctx.body_text[:6000],
        audit_json=result,
    )
    return {"id": scan_id, "url": ctx.snap.final_url, "brand": ctx.brand, "audit": result}


@app.get("/api/scan/stream")
async def scan_stream(url: str):
    """The same scan, reported as it happens.

    Every event describes a request that actually went out or a link actually
    found in the page. Nothing here is invented to fill the animation.
    """
    try:
        clean = ScanRequest(url=url).url
    except Exception as e:
        raise HTTPException(422, str(e)) from e

    queue: asyncio.Queue = asyncio.Queue()

    async def work() -> None:
        try:
            snap = await snapshot(clean, emit=queue.put_nowait)
            ctx = Ctx(snap)

            # Entity links first: these are the profiles the site itself claims.
            seen: set[str] = set()
            for block in ctx.jsonld:
                same = block.get("sameAs")
                for link in same if isinstance(same, list) else [same] if same else []:
                    if isinstance(link, str) and link not in seen:
                        seen.add(link)
                        queue.put_nowait({"type": "link", "url": link, "kind": "profile"})

            for link, _ in ctx.external_links[:24]:
                if link not in seen:
                    seen.add(link)
                    queue.put_nowait({"type": "link", "url": link, "kind": "external"})

            result = analyse(ctx, emit=queue.put_nowait)
            scan_id = db.new_id()
            await store.create(
                id=scan_id, url=ctx.snap.final_url, brand=ctx.brand, status="audited",
                brand_name=ctx.brand, page_excerpt=ctx.body_text[:6000], audit_json=result,
            )
            queue.put_nowait({
                "type": "done",
                "id": scan_id,
                "brand": ctx.brand,
                "seo": result["seo"]["overall"],
                "geo": result["geo"]["overall"],
                "gap": result["divergence"]["gap"],
                "headline": result["divergence"]["headline"],
                "fix_count": sum(1 for f in result["findings"] if not f["passed"] and f["fix"]),
            })
        except Exception as e:
            queue.put_nowait({"type": "error", "message": f"{type(e).__name__}: {e}"})
        finally:
            queue.put_nowait(None)

    async def events():
        task = asyncio.create_task(work())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield f"data: {json.dumps(item)}\n\n"
        finally:
            task.cancel()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/scan/{scan_id}")
async def get_scan(scan_id: str):
    row = await store.get(scan_id)
    if not row:
        raise HTTPException(404, "scan not found")
    return {
        "id": row["id"],
        "url": row["url"],
        "brand": row.get("brand_name"),
        "status": row["status"],
        "audit": row.get("audit_json"),
        "visibility": row.get("visibility_json"),
    }


@app.post("/api/scan/{scan_id}/prompts")
async def suggest_prompts(scan_id: str, req: PromptsRequest):
    """The email gate. Returns editable prompts; runs nothing expensive yet."""
    row = await store.get(scan_id)
    if not row:
        raise HTTPException(404, "scan not found")

    category, prompts = await generate_prompts(row.get("brand_name") or "", row.get("page_excerpt") or "")
    await store.update(scan_id, email=req.email)
    return {
        "category": category,
        "prompts": prompts,
        "brand": row.get("brand_name"),
        "engines": [e.name for e in configured_engines()],
    }


@app.post("/api/scan/{scan_id}/visibility", status_code=202)
async def start_visibility(scan_id: str, req: VisibilityRequest, background: BackgroundTasks):
    row = await store.get(scan_id)
    if not row:
        raise HTTPException(404, "scan not found")
    if row["status"] == "running":
        return {"status": "running"}

    engines = configured_engines()
    if not engines:
        raise HTTPException(
            503,
            "No AI engine API keys configured. Set at least one of PERPLEXITY_API_KEY, "
            "OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY.",
        )

    await store.update(scan_id, status="running", brand_name=req.brand)
    background.add_task(_run_visibility, scan_id, req.brand, row["url"], req.prompts)
    return {"status": "running", "engines": [e.name for e in engines], "prompts": req.prompts}


async def _run_visibility(scan_id: str, brand: str, url: str, prompts: list[str]) -> None:
    # ponytail: in-process background task, so a scan dies on redeploy. Move to a real
    # queue when concurrent scans outgrow one worker.
    domain = urlparse(url).netloc.removeprefix("www.")
    try:
        responses = await run_matrix(prompts)
        result = aggregate(responses, brand, domain)
        await store.update(scan_id, status="complete", visibility_json=result)
    except Exception as e:
        await store.update(scan_id, status="failed", visibility_json={"error": f"{type(e).__name__}: {e}"})


@app.post("/api/scan/{scan_id}/lead", status_code=201)
async def capture_lead(scan_id: str, req: LeadRequest):
    """The funnel. The scan is the lead magnet; this is the conversion."""
    row = await store.get(scan_id)
    if not row:
        raise HTTPException(404, "scan not found")

    audit = row.get("audit_json") or {}
    promise = audit.get("promise") or {}
    await store.update(
        scan_id,
        email=req.email,
        lead_json={
            "email": req.email,
            "message": req.message,
            "url": row["url"],
            "brand": row.get("brand_name"),
            "seo_now": promise.get("seo_now"),
            "geo_now": promise.get("geo_now"),
            "seo_ceiling": promise.get("seo_ceiling"),
            "geo_ceiling": promise.get("geo_ceiling"),
            "days": promise.get("days"),
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    return {"ok": True, "scan": scan_id}


@app.get("/api/health")
async def health():
    return {"ok": True, "engines": [e.name for e in configured_engines()]}
