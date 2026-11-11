"""Promised vs delivered.

Map:    each transcript -> structured guidance + management's own claims  (fast model, cached per file)
Check:  every quote is verified verbatim against the transcript; unverifiable items are dropped
Reduce: one reasoning call judges each promise against the actuals table  (smart model)
"""

import re

from .. import llm
from . import financials

EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "call_period": {"type": "string"},
        "guidance": {"type": "array", "items": {"type": "object", "properties": {
            "metric": {"type": "string", "enum": ["revenue_growth", "margin", "capex", "volume",
                                                  "profit", "balance_sheet", "other"]},
            "promise": {"type": "string"},
            "target": {"type": "string"},
            "horizon": {"type": "string"},
            "quote": {"type": "string"},
            "speaker": {"type": "string"},
        }, "required": ["metric", "promise", "quote"]}},
        "claims": {"type": "array", "items": {"type": "object", "properties": {
            "metric": {"type": "string"}, "claim": {"type": "string"}}}},
        "analyst_pushback": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["call_period", "guidance"],
}

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"},
            "verdict": {"type": "string", "enum": ["delivered", "partly", "missed", "pending", "unclear"]},
            "evidence": {"type": "string"},
        }, "required": ["id", "verdict", "evidence"]}},
        "credibility": {"type": "string"},
        "watch": {"type": "string"},
    },
    "required": ["items", "credibility", "watch"],
}

EXTRACT_PROMPT = """Below is an earnings-call transcript of an Indian listed company ({period} call).

Extract:
1. guidance: every explicit forward-looking commitment by management on revenue/volume growth,
   margins, capex, profitability or balance sheet. Only concrete statements ("we expect 12-14% growth
   in FY26", "margins should return to 20%+ by Q4") - skip vague optimism. For each, give a short
   "promise" in your words, the "target" (number/range), the "horizon" (which period it applies to),
   the "speaker", and a VERBATIM "quote" of at most 35 words copied exactly from the transcript.
2. claims: what management says was delivered THIS quarter (e.g. "revenue grew 11% YoY").
3. analyst_pushback: up to 3 topics analysts pressed hardest on, one line each.
Use only this transcript. call_period = the quarter discussed, e.g. "Q2 FY26".

TRANSCRIPT:
{text}"""

JUDGE_PROMPT = """You are an equity analyst checking whether management of {company} delivered on what
they promised over recent quarters. Use ONLY the material below - no outside knowledge.

ACTUALS (from reported quarterly results; YoY computed for you - do not recompute):
{actuals}

MANAGEMENT'S LATER CLAIMS, by call:
{claims}

PROMISES (each with an id):
{promises}

For each promise, decide:
- verdict: "delivered" | "partly" | "missed" | "pending" (horizon not yet reached) | "unclear" (no data to judge)
- evidence: one sentence citing the specific actual numbers or later claims you used.
Then write:
- credibility: 2 sentences on how reliable this management's guidance has been, and any pattern
  (e.g. revenue promises kept but margin promises repeatedly pushed out).
- watch: the one thing to check on the next call.

Return JSON: {{"items": [{{"id": str, "verdict": str, "evidence": str}}], "credibility": str, "watch": str}}"""


def _norm(s):
    return re.sub(r"[^a-z0-9 ]", "", re.sub(r"\s+", " ", s.lower())).strip()


def quote_in(quote, text_norm):
    q = _norm(quote)
    if len(q) < 12:
        return False
    if q in text_norm:
        return True
    words = q.split()
    grams = [" ".join(words[i:i + 4]) for i in range(max(1, len(words) - 3))]
    hits = sum(1 for g in grams if g in text_norm)
    return hits / len(grams) >= 0.75


def extract(transcript):
    data = llm.call(EXTRACT_PROMPT.format(period=transcript["period"], text=transcript["text"][:150000]),
                    task="guidance_extract", as_json=True, schema=EXTRACT_SCHEMA)
    norm = _norm(transcript["text"])
    kept, dropped = [], 0
    for g in data.get("guidance", []):
        if quote_in(g.get("quote", ""), norm):
            kept.append(g)
        else:
            dropped += 1
    data["guidance"] = kept
    data["dropped_unverified"] = dropped
    data["source"] = {"period": transcript["period"], "url": transcript["url"]}
    return data


def promised_vs_delivered(co, transcripts):
    calls = [extract(t) for t in transcripts]
    if not calls:
        return None

    promises, n = [], 0
    for c in reversed(calls):  # oldest first reads naturally
        for g in c["guidance"]:
            n += 1
            promises.append({**g, "id": f"g{n}", "made_in": c.get("call_period") or c["source"]["period"],
                             "source_url": c["source"]["url"]})
    if not promises:
        return {"items": [], "calls": _call_meta(calls), "credibility": None, "watch": None,
                "note": "No concrete numeric guidance found in the recent calls."}

    claims = "\n".join(
        f"- {c.get('call_period') or c['source']['period']}: " +
        "; ".join(x.get("claim", "") for x in c.get("claims", [])[:6])
        for c in reversed(calls))
    plist = "\n".join(f"[{p['id']}] made in {p['made_in']}: {p['promise']} | target: {p.get('target', '')} "
                      f"| horizon: {p.get('horizon', '')}" for p in promises[:30])
    judged = llm.call(JUDGE_PROMPT.format(company=co.get("name") or co["symbol"],
                                          actuals=financials.quarterly_table_for_prompt(co),
                                          claims=claims, promises=plist),
                      smart=True, task="guidance_judge", as_json=True, schema=JUDGE_SCHEMA)

    verdicts = {j["id"]: j for j in judged.get("items", []) if isinstance(j, dict)}
    items = []
    for p in promises[:30]:
        v = verdicts.get(p["id"], {})
        items.append({**p, "verdict": v.get("verdict", "unclear"), "evidence": v.get("evidence")})

    tally = {}
    for it in items:
        tally[it["verdict"]] = tally.get(it["verdict"], 0) + 1
    return {"items": items, "tally": tally, "calls": _call_meta(calls),
            "credibility": judged.get("credibility"), "watch": judged.get("watch")}


def _call_meta(calls):
    return [{"period": c.get("call_period") or c["source"]["period"], "url": c["source"]["url"],
             "promises": len(c["guidance"]), "dropped_unverified": c.get("dropped_unverified", 0),
             "pushback": c.get("analyst_pushback", [])[:3]} for c in calls]
