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


def _printed_numbers(text):
    # A page number is a line of its own near the top or bottom ("152\nOutlook", "\n144\nAnnual Report").
    t = text.strip()
    return {int(n) for part in (t[:60], t[-60:]) for n in re.findall(r"(?:^|\n)\s*(\d{1,3})\s*(?=\n|$)", part)}


def _contents_entry(pages):
    """The MD&A's printed page number from the contents page. Layouts differ: "Management Discussion &
    Analysis 150" (Titan) but "189 Management Discussion and Analysis Report" (CDSL)."""
    for text in pages[:12]:
        for m in MDA.finditer(text):
            before = re.search(r"(?:^|\n)(\d{1,3})\s+$", text[max(0, m.start() - 8):m.start()])
            after = re.match(r"\W*(?:report)?\W*(\d{1,3})\b", text[m.end():m.end() + 15], re.I)
            if before or after:
                return int((before or after).group(1))
    return None


def mdna_start(pages):
    """Index of the first page of the MD&A, tried four ways:
    a running header (three pages in a row mention it; contents pages and cross-references mention it
    once), the contents page's entry matched to the page that prints that number (some PDFs put two
    printed pages on one, so no fixed offset), a heading near the top of a page past the front matter."""
    run = 0
    for i, text in enumerate(pages):
        run = run + 1 if MDA.search(text) else 0
        if run == 3:
            return i - 2
    target = _contents_entry(pages)
    if target:
        # Section openers rarely print their number, so interpolate from the nearest page that does,
        # trusting a number only when nearby pages carry the numbers that should sit around it.
        nums = [_printed_numbers(p) for p in pages]
        best = None
        for i in range(8, len(pages)):
            for n in nums[i]:
                if abs(n - target) > 60:
                    continue
                agree = sum(n + d in nums[i + d] for d in range(-10, 11) if d and 0 <= i + d < len(pages))
                key = (-abs(n - target), agree)
                if agree >= 2 and (best is None or key > best[0]):
                    best = (key, i + target - n)
        if best and 8 <= best[1] < len(pages):
            return best[1]
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
