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
        "total_income": LINE,
        "total_expenses": LINE,
        "finance_costs": LINE,
        "depreciation": LINE,
        "exceptional_items": LINE,
        "operating_profit_before_provisions": LINE,
        "provisions": LINE,
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
- total_income = the "Total income" line exactly as printed (it may include extra lines such as fair value gains).
- total_expenses = the "Total expenses" (banks: "Total expenditure") line as printed.
- pbt = Profit before tax (after exceptional items). pat = Net profit for the period (total, before OCI).
- exceptional_items: as printed, positive if it adds to profit, negative if a loss. null if the line does not exist.
- operating_profit_before_provisions and provisions (other than tax, and contingencies): banks/NBFCs only.
- Copy numbers exactly as printed. Brackets mean negative. Never compute or guess; use null if absent.
- A blank cell is null for that period. Never shift a number from another column to fill it.

FILING TEXT:
{text}"""


def _to_crore(v, factor):
    return None if v is None else round(v * factor, 2)


def _pct(a, b):
    if a is None or b in (None, 0):
        return None
    return round((a - b) / abs(b) * 100, 1)


PERIODS = ("current", "previous", "year_ago")


def reconcile(raw):
    """Check each period against the statement's own arithmetic, which is where a column shifted by a
    blank cell or a bad OCR shows up. Returns (periods checked, periods that fail). Fixes the sign of an
    exceptional item printed as a positive expense, since both conventions appear in real filings."""
    v = lambda k, p: (raw.get(k) or {}).get(p)  # noqa: E731
    bank = raw.get("format") == "bank"
    exc = raw.setdefault("exceptional_items", {}) or {}
    raw["exceptional_items"] = exc
    printed = {abs(x) for x in exc.values() if x}
    checked, bad = [], []
    for p in PERIODS:
        pbt = v("pbt", p)
        a, b = ((v("operating_profit_before_provisions", p), v("provisions", p)) if bank else
                (v("total_income", p), v("total_expenses", p)))
        if pbt is None or a is None or b is None:
            continue
        checked.append(p)
        # A company's associates' share sits between these lines; nothing does for a bank.
        tol = max(0.005 * abs(pbt), 1) if bank else max(0.03 * abs(pbt), 0.001 * abs(a), 0.5)
        ex = exc.get(p) or 0
        if ex and abs(a - b - ex - pbt) < abs(a - b + ex - pbt):
            ex = exc[p] = -ex
        if abs(a - b + ex - pbt) <= tol:
            continue
        # The usual failure is the exceptional row shifted across a blank cell. If the gap is zero or
        # equals a value printed in another column, put that value here.
        implied = pbt - (a - b)
        fit = next((c for c in [0, *printed] if abs(abs(implied) - c) <= tol), None)
        if fit is None:
            bad.append(p)
        else:
            exc[p] = None if fit == 0 else (fit if implied > 0 else -fit)
    return checked, bad


def build_results_card(raw, screener_quarters=None, screener_basis=None):
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
    nonop = _non_operating(get, "current")
    if nonop and pbt and abs(nonop) > 0.1 * abs(pbt):
        flags.append(f"₹{nonop:,.0f} cr of non-operating income sits in total income: excluded from "
                     f"EBITDA, still inside PBT/PAT")

    check = None
    if screener_quarters and rev and screener_basis in (None, raw.get("basis")):
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
    # Operating EBITDA: strip financing, D&A, treasury income, non-operating gains and one-offs.
    return round(pbt + fin + dep - other - (_non_operating(get, p) or 0) - exceptional, 2)


def _non_operating(get, p):
    """Lines added into total income besides revenue and other income, e.g. Titan's fair value gain on a
    put option. Derived, not extracted, so the model never has to recognise them by name."""
    total, rev = get("total_income", p), get("revenue", p)
    if total is None or rev is None:
        return None
    gap = round(total - rev - (get("other_income", p) or 0), 2)
    # Ignore rounding noise in the printed totals.
    return gap if abs(gap) > 0.005 * abs(total) else None


def _extract(text, pdf=None):
    return llm.call(RESULTS_PROMPT.format(text=text), task="results_extract", as_json=True,
                    schema=RESULTS_SCHEMA, pdf=pdf)


def results_card(filing, screener_quarters=None, screener_basis=None):
    url = filing["attachment"]
    body = pdfs.text(url, max_pages=12)
    raw, checked, bad = None, [], list(PERIODS)
    if not pdfs.is_scanned(body):
        raw = _extract(body[:60000])
        checked, bad = reconcile(raw)
    if bad:
        # Text extraction loses table layout on scans and blank cells; the PDF itself keeps it.
        retry = _extract("(attached PDF)", pdf=pdfs.first_pages(url, 12))
        r_checked, r_bad = reconcile(retry)
        if raw is None or len(r_bad) < len(bad):
            raw, checked, bad = retry, r_checked, r_bad
    card = build_results_card(raw, screener_quarters, screener_basis)
    if bad:
        names = ", ".join((raw.get("periods") or {}).get(p) or p for p in bad)
        card["flags"].append(f"Figures don't add up for {names}; check the filing before relying on them")
    card["reconciled"] = bool(checked) and not bad
    return card


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
