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


def mdna_start(pages):
    """Index of the first page of the MD&A. Most reports repeat it as a running header, so the first run
    of three pages that mention it; contents pages and cross-references mention it once. Failing that,
    the first page past the front matter with it as a heading near the top."""
    run = 0
    for i, text in enumerate(pages):
        run = run + 1 if MDA.search(text) else 0
        if run == 3:
            return i - 2
    for i in range(8, len(pages)):
        if MDA.search(pages[i][:300]):
            return i
    return None


def annual_report_mdna(co, pages=28):
    """Just the MD&A of the latest annual report. The full AR runs to 300-500 pages; the MD&A is where
    the business, segments and outlook live, so that is all we pay the model to read."""
    for ar in co["documents"]["annual_reports"][:2]:
        try:
            body = pdfs.text(ar["url"])
        except Exception as e:
            log.info("annual report %s unavailable: %s", ar["title"], e)
            continue
        texts = re.split(r"\[p\.\d+\]\n", body)[1:]
        start = mdna_start(texts)
        title = ar["title"]
        if start is None:
            start, title = min(6, max(len(texts) - 1, 0)), f"{ar['title']} (opening pages; MD&A not found)"
        chunks = [f"[AR p.{i + 1}]\n{texts[i]}" for i in range(start, min(len(texts), start + pages))]
        text = "\n".join(chunks)
        if len(text) > 2000:
            return {"title": title, "url": ar["url"], "text": text}
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
