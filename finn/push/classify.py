"""Filing classification is rules, not an LLM. NSE's own category field plus the subject line
get ~95% of filings right for free; the LLM only sees the ones that survive triage."""

import re

# NSE's category wins outright when it is specific and the subject rules are known to misread it
# (a monitoring agency named "India Ratings" is not a credit rating). Catch-all categories like
# "General Updates" or "Outcome of Board Meeting" fall through to the subject rules.
DESC_RULES = [
    ("unclassified", "routine", r"monitoring agency report|statement of deviation|esop|trading window|"
                                r"amendment to aoa|address change|certificate under|options to purchase"),
    ("management_change", "auditor", r"resignation of statutory auditor"),
    ("management_change", "change", r"demise|change in company secretary"),
    ("capex", "capex", r"capacity addition"),
    ("M&A", "deal", r"open offer|acquisition|amalgamation|scheme of arrangement|other restructuring"),
    ("litigation", "matter", r"corporate insolvency|action\(s\) (taken|initiated)|pendency of litigation"),
]

# Order matters: first match wins.
RULES = [
    ("results", "ad", r"newspaper.*result|result.*newspaper|publication of.*result"),
    ("unclassified", "routine",
     r"newspaper|loss of share|duplicate share|trading window|regulation 74|reg\.? ?74|"
     r"certificate (under|pursuant)|compliance certificate|registrar|share transfer agent|esop|esos|esps|"
     r"employee stock|change in (the )?(registered office|corporate office|address)|book closure|"
     r"investor complaint|secretarial|business responsibility|brsr|esg|sustainability report|"
     r"statement of deviation|redemption of commercial paper|partly paid"),
    # Calls come before results: a transcript "to discuss the financial results" is still a transcript.
    ("earnings_call", "transcript", r"transcript"),
    ("earnings_call", "recording", r"recording"),
    ("earnings_call", "notice", r"con\.? ?call|conference call|earnings call"),
    ("results", "notice", r"(intimation|to consider).*(financial )?results|board meeting intimation"),
    ("results", "press", r"press release.*result"),
    # A parent's or partner's results filed for information, e.g. Maruti relaying Suzuki's.
    ("press_release", "news", r"results (issued|declared|announced|published) by"),
    ("results", "deck", r"investor presentation|earnings presentation|shareholder letter|quarterly report"),
    ("results", "filing",
     r"financial result|integrated filing.?- ?financial|unaudited.*results|audited.*results|"
     r"results for the quarter"),
    ("investor_meetings", "meet", r"analyst|institutional investor|investor meet|investor conference|"
                                  r"non.?deal roadshow"),
    ("pledging", "pledge", r"pledg|encumbr|regulation 31"),
    ("insider_trading", "disclosure", r"insider trading|\(pit\)|takeover|sast|regulation 29|reg\.? ?29|"
                                      r"regulation 7\(2\)"),
    ("management_change", "change",
     r"change in director|key managerial|resignation|resigns|appointment|appointed|cessation|"
     r"change in management|re-?appoint|retire|superannuat|redesignat|company secretary|demise"),
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
_DESC = [(c, s, re.compile(p, re.I)) for c, s, p in DESC_RULES]
_COMPILED = [(c, s, re.compile(p, re.I)) for c, s, p in RULES]

SENIOR = re.compile(r"\b(ceo|cfo|coo|chief executive|chief financial|chief operating|managing director|"
                    r"\bmd\b|whole[- ]time director|(?<!non-)(?<!non- )(?<!non )executive director|"
                    r"(?<!vice-)(?<!vice )(?<!vice- )chair(man|person))\b", re.I)
MINOR_ROLE = re.compile(r"company secretary|compliance officer|auditor|senior management personnel|"
                        r"(?<!non-)(?<!non- )(?<!non )independent director", re.I)


NSE_MEET = re.compile(r"analysts/institutional investor meet/con\. call updates", re.I)


def _rating_direction(text):
    low = text.lower()
    if "downgrad" in low or "negative" in low:
        return "downgrade"
    if "upgrad" in low or "positive" in low:
        return "upgrade"
    if re.search(r"reaffirm|re-affirm|retain|maintain", low):
        return "reaffirm"
    # NSE's "Credit Rating- Revision" says something moved but not which way; the PDF knows.
    return "revision" if "revision" in low or "revised" in low else "rating"


def seniority(text):
    if SENIOR.search(text):
        return "senior"
    if MINOR_ROLE.search(text):
        return "minor"
    return "change"


def _refine(cat, sub, text):
    if cat == "management_change" and sub == "change":
        return seniority(text)
    if cat == "credit_rating":
        return _rating_direction(text)
    return sub


def classify(nse_category, subject):
    for cat, sub, rx in _DESC:
        if rx.search(nse_category):
            return cat, _refine(cat, sub, f"{nse_category} | {subject}")
    # NSE lumps analyst meets and earnings calls under one label, so let the subject decide.
    text = f"{NSE_MEET.sub('analyst meet', nse_category)} | {subject}"
    for cat, sub, rx in _COMPILED:
        if rx.search(text):
            return cat, _refine(cat, sub, text)
    return "unclassified", "routine"
