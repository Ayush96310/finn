"""Fills a throwaway DB with FICTIONAL companies so the UI can be developed offline.
Every name here is made up. Run with FINN_DATA_DIR pointing somewhere other than data/:

    FINN_DATA_DIR=data-sample python scripts/seed_sample.py
    FINN_DATA_DIR=data-sample python -m finn serve
"""

import json
import os
import random
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
if "FINN_DATA_DIR" not in os.environ or os.environ["FINN_DATA_DIR"].rstrip("/").endswith("data"):
    sys.exit("refusing to seed sample data into the real data dir; set FINN_DATA_DIR=data-sample")

from finn import db  # noqa: E402
from finn.push import classify, score  # noqa: E402

random.seed(7)
NOW = datetime(2026, 11, 9, 21, 0)

BOOK = [
    ("ORIONBK", "Orion Bank", 9), ("KESTREL", "Kestrel Infotech", 7), ("VEGAPWR", "Vega Power", 6),
    ("HALCYON", "Halcyon Pharma", 5), ("MERIDIAN", "Meridian Motors", 6), ("TERRA", "Terra Cements", 4),
    ("ZEPHYR", "Zephyr Foods", 4), ("COBALT", "Cobalt Wires", 4), ("NIMBUS", "Nimbus Telecom", 7),
    ("SABLE", "Sable Chemicals", 3), ("ARGUS", "Argus Defence", 5), ("LUMEN", "Lumen Retail", 5),
    ("QUILL", "Quill Finance", 6), ("BRISK", "Brisk Logistics", 3), ("ONYX", "Onyx Mining", 5),
    ("PELICAN", "Pelican Electronics", 4),
]

FILINGS = [
    ("KESTREL", 3, "Outcome of Board Meeting", "Board approved unaudited financial results for the quarter ended September 30, 2026",
     "Revenue +14% YoY · PAT +9% YoY · EBITDA margin 22.4%", "results"),
    ("VEGAPWR", 5, "Change in Directors/ Key Managerial Personnel", "Resignation of Chief Financial Officer and appointment of Ms. Ananya Rao as CFO",
     "CFO exits after 6 years; successor Ananya Rao joins from a listed utility, effective Dec 1", "people"),
    ("ONYX", 8, "Credit Rating", "Revision in credit rating: long-term rating downgraded to AA- (Negative)",
     "Rating cut one notch to AA- with negative outlook, citing rising leverage from the Odisha mine capex", None),
    ("MERIDIAN", 14, "Acquisition", "Acquisition of 76% stake in a battery-pack maker",
     "Buying 76% of an EV battery-pack maker for ₹840 cr cash; adds ~₹1,100 cr revenue at lower margins", None),
    ("ARGUS", 20, "Updates", "Receipt of order from Ministry of Defence",
     "₹2,350 cr radar order from MoD, about 0.4× FY26 revenue, executable over 36 months", None),
    ("QUILL", 22, "Disclosure under SEBI Takeover Regulations", "Disclosure of creation of encumbrance under Regulation 31",
     "Promoter pledges a further 3.1% stake; total pledged now 18% of promoter holding", None),
    ("HALCYON", 30, "Action(s) initiated or orders passed", "Receipt of warning letter from USFDA for Hyderabad facility",
     "USFDA warning letter on the Hyderabad oral-solids plant, ~11% of US revenue at risk", None),
    ("NIMBUS", 26, "Press Release", "Tariff revision for prepaid plans",
     "Raises prepaid tariffs 10-12% from Nov 20; entry plan moves to ₹219", None),
    ("TERRA", 31, "Board Meeting Intimation", "Intimation of board meeting to consider financial results for Q2", None, None),
    ("ZEPHYR", 34, "Dividend", "Declaration of interim dividend of ₹6 per share; record date November 18", "Interim dividend ₹6/share; record date Nov 18", None),
    ("COBALT", 40, "Capex", "Board approves capacity expansion at Gujarat plant",
     "₹420 cr brownfield expansion lifts cable capacity 30% by Q3 FY28, funded internally", None),
    ("LUMEN", 44, "Analysts/Institutional Investor Meet/Con. Call Updates", "Transcript of the earnings conference call for Q2 FY27",
     "Q2 call transcript is up: management keeps 20 store-addition target, flags weak October footfall", None),
    ("ORIONBK", 52, "Insider Trading - SEBI (PIT) Regulations", "Disclosure under Regulation 7(2) - sale by director",
     "Independent director sells 12,000 shares (~₹2.1 cr)", None),
    ("SABLE", 60, "Bonus", "Recommendation of bonus issue in the ratio 1:1", "1:1 bonus issue recommended, subject to shareholder approval", None),
]
ROUTINE = [
    ("Trading Window", "Closure of trading window"), ("Copy of Newspaper Publication", "Newspaper publication of notice"),
    ("ESOP/ESOS/ESPS", "Allotment of equity shares under ESOP scheme"),
    ("Certificate under SEBI (Depositories and Participants) Regulations, 2018", "Certificate under Regulation 74(5)"),
    ("Analysts/Institutional Investor Meet/Con. Call Updates", "Schedule of investor meetings"),
    ("Shareholders meeting", "Scrutinizer's report on postal ballot"), ("Copy of Newspaper Publication", "Newspaper publication of financial results"),
    ("Loss of Share Certificates", "Intimation of loss of share certificate"),
]


def walk(n, start, vol):
    px, out = start, []
    for _ in range(n):
        px *= 1 + random.gauss(0.0004, vol)
        out.append(px)
    return out


def main():
    with db.session() as c:
        for t in ("prices", "filings", "alerts", "kv"):
            c.execute(f"delete from {t}")
    db.kv_set("sample_data", True)
    db.kv_set("portfolio", [{"symbol": s, "name": n, "sector": "", "weight": w} for s, n, w in BOOK])
    db.kv_set("last_refresh", NOW.isoformat())

    days = [NOW.date() - timedelta(days=i) for i in range(160)]
    days = [d for d in reversed(days) if d.weekday() < 5][-110:]
    shock = {"ONYX": (-6.1, 3.4), "ARGUS": (5.3, 2.6), "HALCYON": (-2.2, 1.9), "KESTREL": (3.1, 2.2)}
    rows = []
    for sym, _, _ in BOOK:
        closes = walk(len(days), random.uniform(200, 3000), 0.013)
        vols = [int(random.uniform(0.7, 1.3) * 1e6) for _ in days]
        if sym in shock:
            chg, vm = shock[sym]
            closes[-1] = closes[-2] * (1 + chg / 100)
            vols[-1] = int(sum(vols[-21:-1]) / 20 * vm)
        for d, cl, v in zip(days, closes, vols):
            rows.append((sym, d.isoformat(), cl, cl, cl, cl, v))
    with db.session() as c:
        c.executemany("insert into prices values (?,?,?,?,?,?,?)", rows)

    weights = {s: w for s, _, w in BOOK}
    watched = ["results", "M&A", "management_change", "litigation", "credit_rating", "fund_raise", "pledging"]
    items = list(FILINGS)
    for i in range(34):
        d, s = random.choice(ROUTINE)
        items.append((random.choice(BOOK)[0], random.randint(1, 160), d, s, None, None))

    with db.session() as c:
        for i, (sym, hrs, desc, subj, summary, kind) in enumerate(items):
            cat, sub = classify.classify(desc, subj)
            s = score.score(cat, sub, subj, weights[sym], watched,
                            reaction={"change_pct": shock[sym][0], "vol_ratio": shock[sym][1]} if sym in shock and hrs < 24 else None)
            card = None
            if kind == "results":
                card = {"kind": "results", "basis": "consolidated",
                        "periods": {"current": "Q2 FY27", "previous": "Q1 FY27", "year_ago": "Q2 FY26"},
                        "metrics": [
                            {"label": "Revenue", "current": 11842, "previous": 11210, "year_ago": 10388, "qoq": 5.6, "yoy": 14.0},
                            {"label": "EBITDA", "current": 2653, "previous": 2410, "year_ago": 2399, "qoq": 10.1, "yoy": 10.6},
                            {"label": "PBT", "current": 2190, "previous": 2050, "year_ago": 2011, "qoq": 6.8, "yoy": 8.9},
                            {"label": "PAT", "current": 1641, "previous": 1530, "year_ago": 1505, "qoq": 7.3, "yoy": 9.0}],
                        "margin": 22.4, "flags": [], "check": {"source": "screener", "value": 11842, "match": True}}
            elif kind == "people":
                card = {"kind": "people", "people": [
                    {"name": "Ananya Rao", "role": "Chief Financial Officer", "change": "appointed", "effective": "1 Dec 2026",
                     "profile": "Chartered accountant; 18 years in power-sector finance; previously CFO of a listed state utility and treasury head at a private IPP."},
                    {"name": "Vikram Sethi", "role": "Chief Financial Officer", "change": "resigned", "effective": "30 Nov 2026",
                     "reason": "To pursue opportunities outside the company"}]}
            filed = (NOW - timedelta(hours=hrs, minutes=random.randint(0, 50))).strftime("%Y-%m-%d %H:%M:%S")
            c.execute("insert into filings (id, symbol, filed_at, nse_category, subject, attachment, category, subtype, "
                      "score, tier, summary, card, enriched) values (?,?,?,?,?,?,?,?,?,?,?,?,1)",
                      (f"s{i}", sym, filed, desc, subj, "", cat, sub, s, score.tier(s), summary,
                       json.dumps(card) if card else None))

    from finn.push import alerts
    alerts.evaluate()
    with db.session() as c:
        for r in c.execute("select id, symbol, filed_at, category, summary from filings where tier = 'act'").fetchall():
            if r["category"] in watched:
                c.execute("insert or ignore into alerts (id, symbol, date, kind, value, message) values (?,?,?,?,?,?)",
                          (f"filing:{r['id']}", r["symbol"], r["filed_at"][:10], "filing", 0,
                           f"{r['symbol']} · {r['category'].replace('_', ' ')}: {r['summary']}"))

    db.kv_set("research:KESTREL", sample_research())
    db.kv_set("corpus:KESTREL", [])
    print("seeded", len(items), "filings for", len(BOOK), "fictional companies")


def sample_research():
    q = ["Sep 2024", "Dec 2024", "Mar 2025", "Jun 2025", "Sep 2025", "Dec 2025", "Mar 2026", "Jun 2026", "Sep 2026"]
    qs = [9100, 9420, 9800, 9950, 10388, 10690, 11020, 11210, 11842]
    qn = [1320, 1360, 1410, 1390, 1505, 1520, 1580, 1530, 1641]
    yo = lambda v, i: round((v[i] - v[i - 4]) / v[i - 4] * 100, 1) if i >= 4 else None  # noqa: E731
    years = ["Mar 2021", "Mar 2022", "Mar 2023", "Mar 2024", "Mar 2025", "Mar 2026"]
    return {
        "symbol": "KESTREL", "name": "Kestrel Infotech (fictional)", "about": "Fictional IT services company.",
        "generated_at": NOW.isoformat(timespec="minutes"), "llm": True,
        "snapshot": {"market_cap": 182400, "price": 4310, "pe": 28.4, "roce": 34.1, "roe": 27.9, "basis": "consolidated"},
        "trajectory": {
            "annual": {"sales": list(zip(years, [22100, 26300, 31900, 36200, 39400, 43900])),
                       "np": list(zip(years, [3300, 3900, 4600, 5100, 5500, 6100])),
                       "opm": list(zip(years, [24, 25, 23, 22, 22, 22]))},
            "quarterly": {"sales": [(q[i], qs[i], yo(qs, i)) for i in range(1, 9)],
                          "np": [(q[i], qn[i], yo(qn, i)) for i in range(1, 9)],
                          "opm": [(p, 22) for p in q[1:]]},
            "sales_cagr_3y": 11.2, "sales_cagr_5y": 14.7, "np_cagr_3y": 9.9, "np_cagr_5y": 13.1, "margin_vs_3y_avg_pp": -0.3},
        "balance_sheet": {"borrowings": list(zip(years, [900, 850, 1200, 1100, 980, 940])),
                          "net_worth": [], "debt_to_equity": list(zip(years, [0.06, 0.05, 0.06, 0.05, 0.04, 0.04])),
                          "cwip": [], "deposits": [],
                          "working_capital": {"debtor_days": list(zip(years, [68, 70, 74, 77, 79, 82])),
                                              "ccc": list(zip(years, [52, 55, 58, 61, 63, 66])),
                                              "wc_days": list(zip(years, [41, 44, 47, 49, 52, 55]))},
                          "roce": []},
        "cash": {"years": [{"period": y, "cfo": c, "pat": p, "cfi": -i, "conversion": round(c / p, 2), "after_investing": c - i}
                           for y, c, p, i in zip(years, [3500, 3800, 4100, 4300, 4400, 4600], [3300, 3900, 4600, 5100, 5500, 6100],
                                                 [900, 1100, 1600, 1500, 1300, 1400])],
                 "conversion_5y": 0.8},
        "guidance": {
            "tally": {"delivered": 3, "partly": 2, "missed": 2, "pending": 1},
            "credibility": "Revenue guidance has been reliable, landing inside the band in three of four quarters. Margin promises are the weak spot: the 23% target has slipped twice and is now framed as an exit rate.",
            "watch": "Whether Q3 margins clear 22.5% without a currency tailwind.",
            "calls": [{"period": p, "url": "#", "promises": 2, "dropped_unverified": d, "pushback": []}
                      for p, d in (("Q2 FY27", 1), ("Q1 FY27", 0), ("Q4 FY26", 0), ("Q3 FY26", 1))],
            "items": [
                {"made_in": "Q3 FY26", "promise": "FY26 revenue growth of 12-14% in constant currency", "target": "12-14%", "horizon": "FY26",
                 "verdict": "delivered", "evidence": "FY26 revenue grew 11.4% reported; Q4 call claimed 12.6% cc, inside the band.",
                 "quote": "we remain confident of delivering twelve to fourteen percent constant currency growth for the year", "speaker": "CEO", "source_url": "#"},
                {"made_in": "Q3 FY26", "promise": "EBITDA margin back to 23% by Q4 FY26", "target": "23%", "horizon": "Q4 FY26",
                 "verdict": "missed", "evidence": "Operating margin was 22% in Mar 2026 and has stayed at 22% since.",
                 "quote": "we should exit the year at around twenty three percent on EBITDA", "speaker": "CFO", "source_url": "#"},
                {"made_in": "Q4 FY26", "promise": "Double-digit revenue growth in FY27", "target": ">10%", "horizon": "FY27",
                 "verdict": "pending", "evidence": "H1 FY27 revenue up ~11% YoY; on track so far.",
                 "quote": "we are guiding to double digit growth for FY27", "speaker": "CEO", "source_url": "#"},
                {"made_in": "Q4 FY26", "promise": "Receivable days to come down to ~70", "target": "~70 days", "horizon": "FY27",
                 "verdict": "missed", "evidence": "Debtor days rose from 79 to 82 over FY26.",
                 "quote": "we expect DSO to normalise to around seventy days", "speaker": "CFO", "source_url": "#"},
                {"made_in": "Q1 FY27", "promise": "Large-deal TCV above $1bn for the year", "target": "$1bn+", "horizon": "FY27",
                 "verdict": "partly", "evidence": "Q2 call cites $640m TCV in H1, behind the run-rate needed.",
                 "quote": "large deal TCV should comfortably cross a billion dollars this year", "speaker": "CEO", "source_url": "#"},
                {"made_in": "Q1 FY27", "promise": "Sequential growth every quarter in FY27", "target": "QoQ > 0", "horizon": "FY27",
                 "verdict": "delivered", "evidence": "Revenue 11,020 → 11,210 → 11,842 cr across the last three quarters.",
                 "quote": "we see sequential growth in each quarter of this year", "speaker": "CEO", "source_url": "#"},
                {"made_in": "Q2 FY27", "promise": "Margins expand 50-70 bps in H2", "target": "+50-70 bps", "horizon": "H2 FY27",
                 "verdict": "partly", "evidence": "Q2 margin 22.4%, up ~40 bps on Q1; H2 not yet reported.",
                 "quote": "we expect fifty to seventy basis points of margin expansion in the second half", "speaker": "CFO", "source_url": "#"},
                {"made_in": "Q2 FY27", "promise": "Headcount additions of 4,000 in H2", "target": "4,000", "horizon": "H2 FY27",
                 "verdict": "delivered", "evidence": "Q2 call reports 2,300 net adds in the quarter alone.",
                 "quote": "we will add about four thousand people in the second half", "speaker": "CHRO", "source_url": "#"}]},
        "thesis": {
            "business": {"one_liner": "Fictional mid-tier IT services firm selling engineering and cloud services to US and European enterprises.",
                         "segments": [{"name": "BFSI", "share": "34%", "note": "Largest vertical; US regional banks"},
                                      {"name": "Manufacturing", "share": "27%", "note": "Engineering R&D services"},
                                      {"name": "Retail & CPG", "share": "21%", "note": ""}, {"name": "Others", "share": "18%", "note": ""}],
                         "moat": "Sticky engineering relationships; top-10 clients average 11-year tenure [AR p.42]"},
            "narrative_vs_numbers": [
                {"claim": "Management says margins are 'structurally stable'", "numbers_say": "Operating margin slid from 25% (FY22) to 22% and has not recovered.", "agrees": False, "cite": "[AR p.38]"},
                {"claim": "Cash generation remains strong", "numbers_say": "5-yr CFO/PAT is 0.80x and receivable days rose for 5 straight years.", "agrees": False, "cite": "[Q2 FY27 call]"},
                {"claim": "Growth is broad-based across verticals", "numbers_say": "Revenue CAGR 14.7% over 5 years with sequential growth in each of the last 8 quarters.", "agrees": True, "cite": "[AR p.40]"}],
            "bull": ["Deal pipeline up 30% YoY; if TCV crosses $1bn, FY28 growth can re-accelerate to mid-teens.",
                     "Near-zero debt and 34% ROCE give room for bolt-on acquisitions in Europe.",
                     "Engineering services (27% of revenue) grow faster than the core and carry higher margins."],
            "bear": ["Margin target missed twice; another miss would reset the 23% narrative to 21-22%.",
                     "Receivables up from 68 to 82 days over 5 years; cash conversion at 0.8x lags peers.",
                     "34% BFSI exposure concentrated in US regional banks, a pressured client base."]},
        "sources": {"annual_report": {"title": "Annual Report FY26 (fictional)", "url": "#"},
                    "calls": [{"period": p, "url": "#"} for p in ("Q2 FY27", "Q1 FY27", "Q4 FY26", "Q3 FY26")]},
    }


if __name__ == "__main__":
    main()
