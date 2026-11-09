import io
import logging
import re

from ..sources import pdfs

log = logging.getLogger(__name__)


def transcripts(co, n=5):
    """Latest n concall transcripts as (period, url, text). Screener lists newest first."""
    out = []
    for entry in co["documents"]["concalls"][:n + 2]:
        try:
            body = pdfs.text(entry["transcript"])
        except Exception as e:
            log.info("transcript %s unavailable: %s", entry.get("period"), e)
            continue
        if len(body) > 3000 and not pdfs.is_scanned(body):
            out.append({"period": entry["period"], "url": entry["transcript"], "text": body})
        if len(out) == n:
            break
    return out


MDA = re.compile(r"management\W{0,3}s?\W{0,3}discussion\s*(and|&)\s*analysis", re.I)


def annual_report_mdna(co, pages=28):
    """Just the MD&A of the latest annual report. The full AR is 300 pages; the MD&A is where the
    business, segments and outlook live, so that is all we pay to read."""
    from pypdf import PdfReader

    for ar in co["documents"]["annual_reports"][:2]:
        try:
            data = pdfs.fetch_bytes(ar["url"])
            if not data.startswith(b"%PDF"):
                continue
            reader = PdfReader(io.BytesIO(data))
        except Exception as e:
            log.info("annual report %s unavailable: %s", ar["title"], e)
            continue

        total = len(reader.pages)
        start = None
        for i in range(4, min(total, 160)):
            try:
                head = (reader.pages[i].extract_text() or "")[:500]
            except Exception:
                continue
            if MDA.search(head):
                start = i
                break
        start = start if start is not None else min(6, total - 1)
        chunks = []
        for i in range(start, min(total, start + pages)):
            try:
                chunks.append(f"[AR p.{i + 1}]\n{reader.pages[i].extract_text() or ''}")
            except Exception:
                pass
        body = "\n".join(chunks)
        if len(body) > 2000:
            return {"title": ar["title"], "url": ar["url"], "text": body}
    return None


def chunk(text, source, size=1800, overlap=200):
    out, i = [], 0
    page = None
    while i < len(text):
        piece = text[i:i + size]
        m = re.findall(r"\[(?:AR )?p\.(\d+)\]", text[max(0, i - 4000):i + size])
        page = m[-1] if m else page
        out.append({"source": source, "page": page, "text": piece})
        i += size - overlap
    return out
