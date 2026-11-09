import hashlib
import io
import logging

import requests

from ..config import DATA_DIR, USER_AGENT

log = logging.getLogger(__name__)
CACHE = DATA_DIR / "pdf"
CACHE.mkdir(exist_ok=True)


def _key(url):
    return hashlib.sha1(url.encode()).hexdigest()[:20]


def fetch_bytes(url):
    path = CACHE / f"{_key(url)}.pdf"
    if path.exists():
        return path.read_bytes()
    headers = {"User-Agent": USER_AGENT, "Accept": "application/pdf,*/*"}
    if "nseindia.com" in url:
        headers["Referer"] = "https://www.nseindia.com/"
    r = requests.get(url, headers=headers, timeout=60)
    r.raise_for_status()
    path.write_bytes(r.content)
    return r.content


def text(url, max_pages=None):
    """Plain text with [p.N] markers so downstream prompts can cite pages."""
    path = CACHE / f"{_key(url)}.{max_pages or 'all'}.txt"
    if path.exists():
        return path.read_text()
    from pypdf import PdfReader

    data = fetch_bytes(url)
    try:
        reader = PdfReader(io.BytesIO(data))
        pages = reader.pages[:max_pages] if max_pages else reader.pages
        out = []
        for i, page in enumerate(pages, 1):
            try:
                out.append(f"[p.{i}]\n{page.extract_text() or ''}")
            except Exception:  # pypdf throws a zoo of errors on malformed pages
                out.append(f"[p.{i}]\n")
        body = "\n".join(out)
    except Exception as e:
        log.warning("could not parse %s: %s", url, e)
        body = ""
    path.write_text(body)
    return body


def is_scanned(body):
    # Scanned filings come back as page markers and little else.
    stripped = "".join(line for line in body.splitlines() if not line.startswith("[p."))
    return len(stripped.strip()) < 200
