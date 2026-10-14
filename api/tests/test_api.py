import pytest
from pydantic import ValidationError

from main import ScanRequest, VisibilityRequest, PromptsRequest


@pytest.mark.parametrize("url", [
    "acme.example", "https://acme.example", "http://acme.example/path?q=1", "  https://acme.example  ",
])
def test_public_urls_accepted_and_normalised(url):
    assert ScanRequest(url=url).url.startswith(("http://", "https://"))


@pytest.mark.parametrize("url", [
    "http://localhost:8000", "http://127.0.0.1/", "http://10.0.0.5/", "http://192.168.1.1/",
    "http://172.16.0.1/", "http://169.254.169.254/latest/meta-data/",  # cloud metadata
    "http://0.0.0.0/", "http://db.internal/", "http://printer.local/",
    "file:///etc/passwd", "gopher://evil", "", "   ", "http://nodot/",
])
def test_internal_and_non_http_urls_rejected(url):
    """This endpoint fetches whatever it is handed, so the guard is a trust boundary."""
    with pytest.raises(ValidationError):
        ScanRequest(url=url)


@pytest.mark.parametrize("email", ["a@b.co", "First.Last+tag@sub.domain.org"])
def test_valid_emails(email):
    assert PromptsRequest(email=email).email == email.strip().lower()


@pytest.mark.parametrize("email", ["", "nope", "a@b", "a b@c.com", "@b.co"])
def test_invalid_emails_rejected(email):
    with pytest.raises(ValidationError):
        PromptsRequest(email=email)


def test_prompts_are_trimmed_deduped_of_blanks_and_capped():
    req = VisibilityRequest(brand="Acme", prompts=["  best tool  ", "", "   ", *[f"q{i}" for i in range(20)]])
    assert req.prompts[0] == "best tool"
    assert len(req.prompts) == 10
    assert all(p.strip() for p in req.prompts)


def test_visibility_requires_at_least_one_prompt():
    with pytest.raises(ValidationError):
        VisibilityRequest(brand="Acme", prompts=["", "  "])


def test_visibility_requires_a_brand():
    with pytest.raises(ValidationError):
        VisibilityRequest(brand="", prompts=["q"])
