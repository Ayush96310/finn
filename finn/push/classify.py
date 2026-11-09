"""Filing classification is rules, not an LLM. NSE's own category field plus the subject line
get ~95% of filings right for free; the LLM only sees the ones that survive triage."""

import re

# Order matters: first match wins.
RULES = [
    ("results", "ad", r"newspaper.*result|result.*newspaper|publication of.*result"),
    ("unclassified", "routine",
     r"newspaper|loss of share|duplicate share|trading window|regulation 74|reg\.? ?74|"
     r"certificate under|compliance certificate|registrar|share transfer agent|esop|esos|esps|"
     r"employee stock|change in registered office|book closure|investor complaint|"
     r"secretarial|business responsibility|brsr|esg|sustainability report|statement of deviation"),
    ("results", "notice", r"(intimation|to consider).*(financial )?results|board meeting intimation"),
    ("results", "filing",
     r"financial result|integrated filing.?- ?financial|unaudited.*results|audited.*results|"
     r"results for the quarter"),
    ("earnings_call", "transcript", r"transcript"),
    ("earnings_call", "recording", r"audio recording|video recording|recording of"),
    ("earnings_call", "notice", r"con\.? ?call|conference call|earnings call"),
    ("results", "deck", r"investor presentation|earnings presentation|shareholder letter"),
    ("investor_meetings", "meet", r"analyst|institutional investor|investor meet|investor conference|"
                                  r"non.?deal roadshow"),
    ("pledging", "pledge", r"pledg|encumbr|regulation 31"),
    ("insider_trading", "disclosure", r"insider trading|\(pit\)|takeover|sast|regulation 29|reg\.? ?29|"
                                      r"regulation 7\(2\)"),
    ("management_change", "change",
     r"change in director|key managerial|resignation|resigns|appointment|appointed|cessation|"
     r"change in management|re-?appoint|retire|superannuat|redesignat"),
    ("M&A", "deal", r"acqui|amalgamat|merger|demerg|scheme of arrangement|joint venture|"
                    r"stake|subsidiar|divest|slump sale|business transfer"),
    ("fund_raise", "raise", r"qualified institutional|\bqip\b|rights issue|preferential|buy-?back|"
                            r"commercial paper|debenture|\bncd|fund.?rais|raising of funds|"
                            r"allotment of securities"),
    ("credit_rating", "rating", r"credit rating|\brating"),
    ("litigation", "matter", r"litigation|order passed|orders passed|action\(s\) initiated|penalt|"
                             r"show cause|tax demand|demand order|\bgst\b|income tax|insolvency|nclt|"
                             r"\bfine\b|court|arbitra|search|investigat|fraud|default"),
    ("bonus_split", "action", r"\bbonus\b|split|sub-?division"),
    ("dividend", "dividend", r"dividend"),
    ("capex", "capex", r"capex|capacity expansion|new plant|commission|greenfield|brownfield|"
                       r"capital expenditure|manufacturing facility"),
    ("postal_ballot", "ballot", r"postal ballot"),
    ("agm_egm", "meeting", r"annual general meeting|\bagm\b|\begm\b|extra-?ordinary general|"
                           r"shareholders meeting|scrutini[sz]er|e-?voting"),
    ("press_release", "news", r"press release|order|contract|launch|partnership|clarification|award|"
                              r"spurt in volume|update"),
    ("press_release", "board", r"outcome of board meeting"),
]
_COMPILED = [(c, s, re.compile(p, re.I)) for c, s, p in RULES]

SENIOR = re.compile(r"\b(ceo|cfo|coo|chief executive|chief financial|chief operating|managing director|"
                    r"\bmd\b|whole[- ]time director|executive director|chairman|chairperson)\b", re.I)
MINOR_ROLE = re.compile(r"company secretary|compliance officer|auditor|senior management personnel|"
                        r"independent director", re.I)


NSE_MEET = re.compile(r"analysts/institutional investor meet/con\. call updates", re.I)


def classify(nse_category, subject):
    # NSE lumps analyst meets and earnings calls under one label, so let the subject decide.
    text = f"{NSE_MEET.sub('analyst meet', nse_category)} | {subject}"
    for cat, sub, rx in _COMPILED:
        if rx.search(text):
            if cat == "management_change":
                if SENIOR.search(text):
                    sub = "senior"
                elif MINOR_ROLE.search(text):
                    sub = "minor"
            if cat == "credit_rating":
                low = text.lower()
                sub = ("downgrade" if "downgrad" in low or "negative" in low else
                       "upgrade" if "upgrad" in low or "positive" in low else "reaffirm")
            return cat, sub
    return "unclassified", "routine"
