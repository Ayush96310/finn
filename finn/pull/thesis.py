from .. import llm

THESIS_PROMPT = """You are writing a research note on {company} for a portfolio manager.
Use ONLY the primary-source material below (annual report MD&A, latest earnings call, and the computed
financial summary). Do not use outside knowledge of the company. If something is not in the material,
leave it out.

Cite each point with its source tag, e.g. [AR p.54] or [{call} call].

Return JSON:
{{
 "business": {{
   "one_liner": str (what the company does, max 25 words),
   "segments": [{{"name": str, "share": str|null, "note": str}}] (revenue mix if disclosed),
   "moat": str|null
 }},
 "narrative_vs_numbers": [{{"claim": str, "numbers_say": str, "agrees": bool, "cite": str}}] (2-4 items:
   where management's story lines up with, or diverges from, the computed financials),
 "bull": [str, str, str],
 "bear": [str, str, str]
}}
Bull and bear points must be specific and falsifiable (numbers, segments, timelines), max 30 words each.

COMPUTED FINANCIALS:
{numbers}

ANNUAL REPORT (MD&A excerpt):
{ar}

LATEST EARNINGS CALL ({call}):
{transcript}"""


def numbers_brief(snap, traj, bs, cash):
    def fmt(pairs):
        return ", ".join(f"{p}: {v}" for p, v in pairs[-5:])
    lines = [
        f"Market cap ₹{snap.get('market_cap')} cr, P/E {snap.get('pe')}, ROCE {snap.get('roce')}%, ROE {snap.get('roe')}%",
        f"Revenue CAGR 3y {traj.get('sales_cagr_3y')}%, 5y {traj.get('sales_cagr_5y')}%; "
        f"profit CAGR 3y {traj.get('np_cagr_3y')}%, 5y {traj.get('np_cagr_5y')}%",
        f"Annual revenue: {fmt(traj['annual']['sales'])}",
        f"Annual operating margin %: {fmt(traj['annual']['opm'])}",
        f"Annual net profit: {fmt(traj['annual']['np'])}",
        f"Debt/equity: {fmt(bs['debt_to_equity'])}",
        f"Cash conversion (CFO/PAT) 5y: {cash.get('conversion_5y')}",
        f"Working capital days: {fmt(bs['working_capital'].get('wc_days', []))}",
    ]
    return "\n".join(lines)


def build(co, numbers, ar, latest_call):
    call = latest_call["period"] if latest_call else "n/a"
    return llm.call(THESIS_PROMPT.format(
        company=co.get("name") or co["symbol"], numbers=numbers,
        ar=(ar["text"][:70000] if ar else "(not available)"),
        call=call, transcript=(latest_call["text"][:60000] if latest_call else "(not available)")),
        smart=True, task="thesis", as_json=True)
