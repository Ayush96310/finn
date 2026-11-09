import json
import logging
import re

from .. import db, llm
from ..sources import pdfs

log = logging.getLogger(__name__)

TO_CRORE = {"crore": 1, "crores": 1, "cr": 1, "lakh": 0.01, "lakhs": 0.01, "million": 0.1,
            "millions": 0.1, "thousand": 0.0001, "thousands": 0.0001, "rupees": 1e-7, "inr": 1e-7}

LINE = {"type": "object", "properties": {
    "current": {"type": "number", "nullable": True},
    "previous": {"type": "number", "nullable": True},
    "year_ago": {"type": "number", "nullable": True}}}

RESULTS_SCHEMA = {
    "type": "object",
    "properties": {
        "basis": {"type": "string", "enum": ["consolidated", "standalone"]},
        "format": {"type": "string", "enum": ["standard", "bank"]},
        "unit": {"type": "string"},
        "periods": {"type": "object", "properties": {
            "current": {"type": "string"}, "previous": {"type": "string"}, "year_ago": {"type": "string"}}},
        "revenue": LINE,
        "other_income": LINE,
        "finance_costs": LINE,
        "depreciation": LINE,
        "exceptional_items": LINE,
        "operating_profit_before_provisions": LINE,
        "pbt": LINE,
        "pat": LINE,
    },
    "required": ["basis", "format", "unit", "periods", "revenue", "pbt", "pat"],
}

RESULTS_PROMPT = """You are reading an Indian listed company's quarterly results filing.
Extract figures for the latest quarter ("current"), the immediately preceding quarter ("previous") and the
same quarter last year ("year_ago"). These are the first three numeric columns of the standard SEBI format.

Rules:
- Prefer the CONSOLIDATED statement if present, else standalone. Say which in "basis".
- "unit" is the unit stated in the table header (e.g. "crore", "lakh", "million").
- revenue = Revenue from operations (for banks: Interest earned, and set format = "bank").
- pbt = Profit before tax (after exceptional items). pat = Net profit for the period (total, before OCI).
- exceptional_items: as printed, negative if a loss. null if the line does not exist.
- operating_profit_before_provisions: banks/NBFCs only.
- Copy numbers exactly as printed. Brackets mean negative. Never compute or guess; use null if absent.

FILING TEXT:
{text}"""


def _to_crore(v, factor):
    return None if v is None else round(v * factor, 2)


def _pct(a, b):
    if a is None or b in (None, 0):
        return None
    return round((a - b) / abs(b) * 100, 1)


def build_results_card(raw, screener_quarters=None):
    unit = (raw.get("unit") or "crore").lower()
    factor = next((v for k, v in TO_CRORE.items() if k in unit), 1)
    get = lambda k, p: _to_crore((raw.get(k) or {}).get(p), factor)  # noqa: E731

    metrics = []
    is_bank = raw.get("format") == "bank"
    for label, fn in (
        ("Revenue", lambda p: get("revenue", p)),
        ("PPOP" if is_bank else "EBITDA", lambda p: _ebitda(raw, p, get, is_bank)),
        ("PBT", lambda p: get("pbt", p)),
        ("PAT", lambda p: get("pat", p)),
    ):
        cur, prev, ya = fn("current"), fn("previous"), fn("year_ago")
        metrics.append({"label": label, "current": cur, "previous": prev, "year_ago": ya,
                        "qoq": _pct(cur, prev), "yoy": _pct(cur, ya)})

    rev, ebitda = metrics[0]["current"], metrics[1]["current"]
    flags = []
    pbt, pat = metrics[2]["current"], metrics[3]["current"]
    if pbt and pat and pbt > 0 and pat > pbt * 1.02:
        flags.append("PAT above PBT: tax credit or extraction error, check the filing")
    ex = get("exceptional_items", "current")
    if ex and pbt and abs(ex) > 0.1 * abs(pbt):
        flags.append(f"Exceptional item of ₹{ex:,.0f} cr distorts PBT/PAT")

    check = None
    if screener_quarters and rev:
        sales = screener_quarters["rows"].get("Sales") or screener_quarters["rows"].get("Revenue")
        if sales and sales[-1]:
            diff = abs(sales[-1] - rev) / sales[-1]
            check = {"source": "screener", "value": sales[-1], "match": diff < 0.02}

    return {
        "kind": "results",
        "basis": raw.get("basis"),
        "periods": raw.get("periods") or {},
        "metrics": metrics,
        "margin": round(ebitda / rev * 100, 1) if rev and ebitda else None,
        "flags": flags,
        "check": check,
    }


def _ebitda(raw, p, get, is_bank):
    if is_bank:
        return get("operating_profit_before_provisions", p)
    pbt, fin, dep = get("pbt", p), get("finance_costs", p), get("depreciation", p)
    if pbt is None or fin is None or dep is None:
        return None
    other = get("other_income", p) or 0
    exceptional = get("exceptional_items", p) or 0
    # Operating EBITDA: strip financing, D&A, treasury income and one-offs.
    return round(pbt + fin + dep - other - exceptional, 2)


def results_card(filing, screener_quarters=None):
    body = pdfs.text(filing["attachment"], max_pages=12)
    if pdfs.is_scanned(body):
        raw = llm.call(RESULTS_PROMPT.format(text="(attached PDF)"), task="results_extract",
                       as_json=True, schema=RESULTS_SCHEMA, pdf=pdfs.fetch_bytes(filing["attachment"]))
    else:
        raw = llm.call(RESULTS_PROMPT.format(text=body[:60000]), task="results_extract",
                       as_json=True, schema=RESULTS_SCHEMA)
    return build_results_card(raw, screener_quarters)


PEOPLE_PROMPT = """From this Indian stock-exchange disclosure about a management change, list each person
whose role changes. Use only the filing. Return JSON:
{{"people": [{{"name": str, "role": str, "change": "appointed"|"resigned"|"retired"|"redesignated"|"other",
"effective": str|null, "reason": str|null, "profile": str|null}}]}}
"profile" = the brief profile/background the filing gives (max 45 words), else null.
Skip auditors, company secretaries and compliance officers unless they are the only change.

FILING:
{text}"""

BIO_PROMPT = """In 2-3 short factual sentences, give the professional background of {name}, newly {change} as
{role} at {company} (India). Focus on previous employers, roles and tenure. If you cannot find this
specific person with confidence, reply exactly: UNKNOWN"""


def people_card(filing, company):
    body = pdfs.text(filing["attachment"], max_pages=6)
    data = llm.call(PEOPLE_PROMPT.format(text=body[:20000] or filing["subject"]),
                    task="people_extract", as_json=True)
    people = data.get("people", [])[:3]
    for p in people:
        if p.get("change") != "appointed":
            continue
        bio = llm.web_bio(BIO_PROMPT.format(name=p["name"], role=p.get("role", ""),
                                            change=p["change"], company=company))
        if bio:
            p["bio"], p["bio_sources"] = bio
    return {"kind": "people", "people": people}


SUMMARY_PROMPT = """You triage stock-exchange filings for a busy fund manager who owns these stocks.
For each filing, write ONE line (max 22 words) saying what actually changed, leading with the number
or fact that matters (amount, counterparty, rating, date). No filler like "The company announced".
Also rate materiality to the share price: "high", "normal" or "low" (routine paperwork = low).
Use only the text given. If the text is empty, work from the subject.

Return JSON: [{{"id": str, "line": str, "materiality": "high"|"normal"|"low"}}]

FILINGS:
{items}"""


def summarise_batch(filings):
    blocks = []
    for f in filings:
        try:
            body = pdfs.text(f["attachment"], max_pages=3)[:2500] if f["attachment"] else ""
        except Exception as e:
            log.info("attachment fetch failed for %s: %s", f["id"], e)
            body = ""
        body = re.sub(r"\s+", " ", body)
        blocks.append(f"### id={f['id']} | {f['symbol']} | {f['nse_category']}\n"
                      f"Subject: {f['subject']}\nText: {body}")
    out = llm.call(SUMMARY_PROMPT.format(items="\n\n".join(blocks)), task="filing_summary", as_json=True)
    return {o["id"]: o for o in out if isinstance(o, dict) and "id" in o}


def save_card(filing_id, card=None, summary=None, score=None, tier=None):
    with db.session() as c:
        c.execute(
            "update filings set card = coalesce(?, card), summary = coalesce(?, summary), "
            "score = coalesce(?, score), tier = coalesce(?, tier), enriched = 1 where id = ?",
            (json.dumps(card) if card else None, summary, score, tier, filing_id))
