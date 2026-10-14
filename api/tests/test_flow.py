"""End-to-end flow with the network stubbed: audit -> email gate -> background scan -> poll."""
import asyncio

import pytest
from fastapi.testclient import TestClient

import main
from audit.fetch import AI_BOTS, BotProbe, SiteSnapshot
from tests.test_audit import FIXTURES, PERMISSIVE_ROBOTS
from visibility.engines import EngineResponse


@pytest.fixture
def client(monkeypatch):
    html = (FIXTURES / "good.html").read_text()

    async def fake_snapshot(url):
        return SiteSnapshot(
            url=url, final_url="https://acme.example/guide", status=200, html=html, headers={},
            ttfb_ms=180.0, bytes=len(html), robots_txt=PERMISSIVE_ROBOTS, llms_txt=None,
            sitemap_urls=["https://acme.example/sitemap.xml"],
            robots_sitemap_refs=["https://acme.example/sitemap.xml"],
            bot_probes=[BotProbe(b, 200, False) for b in AI_BOTS],
        )

    async def fake_matrix(prompts, engines=None):
        await asyncio.sleep(0)
        return [
            EngineResponse("perplexity", prompts[0], "Acme Analytics is the pick.", ["https://acme.example/"]),
            EngineResponse("openai", prompts[0], "Rival is better.", ["https://rival.com/"]),
        ]

    class FakeEngine:
        name = "perplexity"

    monkeypatch.setattr(main, "snapshot", fake_snapshot)
    monkeypatch.setattr(main, "run_matrix", fake_matrix)
    monkeypatch.setattr(main, "configured_engines", lambda: [FakeEngine()])
    main.store = __import__("db").MemoryStore()
    with TestClient(main.app) as c:
        yield c


def test_full_flow(client):
    audit = client.post("/api/scan", json={"url": "acme.example"})
    assert audit.status_code == 200
    body = audit.json()
    scan_id = body["id"]
    assert body["brand"] == "Acme Analytics"
    # A strong fixture, but citability is scored continuously so a perfect GEO is
    # not reachable by passing checks alone — that is the point of the engine.
    assert body["audit"]["seo"]["overall"] >= 75
    assert body["audit"]["geo"]["overall"] >= 70
    assert body["audit"]["citability"]["max_possible"] == 210

    # Report is fetchable by id — the shareable link.
    got = client.get(f"/api/scan/{scan_id}")
    assert got.status_code == 200 and got.json()["status"] == "audited"

    # Email gate returns editable prompts.
    prompts = client.post(f"/api/scan/{scan_id}/prompts", json={"email": "a@b.co"})
    assert prompts.status_code == 200
    suggested = prompts.json()["prompts"]
    assert len(suggested) >= 1

    # Background scan. TestClient runs BackgroundTasks to completion before returning.
    started = client.post(
        f"/api/scan/{scan_id}/visibility", json={"brand": "Acme Analytics", "prompts": suggested[:1]}
    )
    assert started.status_code == 202

    final = client.get(f"/api/scan/{scan_id}").json()
    assert final["status"] == "complete"
    vis = final["visibility"]
    assert vis["cited_count"] == 1
    assert vis["overall"] == 50  # one cited (1.0) + one absent (0) over two responses
    assert vis["competitors"][0]["domain"] == "rival.com"


def test_scan_rejects_internal_urls(client):
    assert client.post("/api/scan", json={"url": "http://169.254.169.254/"}).status_code == 422


def test_visibility_on_unknown_scan_is_404(client):
    r = client.post("/api/scan/nope/visibility", json={"brand": "x", "prompts": ["q"]})
    assert r.status_code == 404
