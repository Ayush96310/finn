import re

BASE = {
    ("results", "filing"): 85, ("results", "deck"): 45, ("results", "notice"): 25, ("results", "ad"): 5,
    ("results", "press"): 25,
    ("M&A", "deal"): 70,
    ("management_change", "senior"): 80, ("management_change", "change"): 45,
    ("management_change", "minor"): 20, ("management_change", "auditor"): 50,
    ("litigation", "matter"): 55,
    ("fund_raise", "raise"): 60,
    ("credit_rating", "downgrade"): 80, ("credit_rating", "upgrade"): 55, ("credit_rating", "reaffirm"): 15,
    ("credit_rating", "revision"): 50, ("credit_rating", "rating"): 30,
    ("pledging", "pledge"): 60,
    ("insider_trading", "disclosure"): 35,
    ("capex", "capex"): 55,
    ("bonus_split", "action"): 45,
    ("dividend", "dividend"): 30,
    ("press_release", "news"): 35, ("press_release", "board"): 30,
    ("earnings_call", "transcript"): 40, ("earnings_call", "recording"): 10, ("earnings_call", "notice"): 15,
    ("investor_meetings", "meet"): 10,
    ("postal_ballot", "ballot"): 15,
    ("agm_egm", "meeting"): 15,
    ("unclassified", "routine"): 3,
}

ALARM = re.compile(r"fraud|default|forensic|resign.*(auditor|cfo|ceo)|qualified opinion|"
                   r"sebi order|search and seizure|raid|insolvency|suspension|whistle", re.I)
ROUTINE_HINT = re.compile(r"intimation|clarification sought|reminder|corrigendum|addendum", re.I)

TIERS = (("act", 65), ("glance", 35), ("routine", 0))


def score(category, subtype, subject, weight, watched, reaction=None, llm_materiality=None, followup=False):
    s = BASE.get((category, subtype), 25)
    alarm = bool(ALARM.search(subject or ""))
    if alarm:
        s += 25
    if ROUTINE_HINT.search(subject or "") and category != "results":
        s -= 10
    if category in watched and s >= 30:
        s += 10
    s += 8 if weight >= 7 else 4 if weight >= 5 else 0
    if reaction and (abs(reaction["change_pct"]) >= 3 or reaction["vol_ratio"] >= 2):
        s += 12
    if followup:
        s -= 20
    if llm_materiality == "high":
        s += 10
    elif llm_materiality == "low" and not alarm:
        # The model read the document and called it paperwork; a watched category shouldn't overrule that.
        s = min(s - 15, 30)
    return max(0, min(100, s))


def tier(s):
    for name, floor in TIERS:
        if s >= floor:
            return name
    return "routine"
