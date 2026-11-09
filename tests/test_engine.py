import os
import tempfile

os.environ["FINN_DATA_DIR"] = tempfile.mkdtemp()

import pytest  # noqa: E402

from finn.pull import financials, guidance  # noqa: E402
from finn.push import enrich, score  # noqa: E402
from finn.push.classify import classify  # noqa: E402
from finn.sources import screener  # noqa: E402


@pytest.mark.parametrize("desc,subject,cat,sub", [
    ("Outcome of Board Meeting", "Board approved unaudited financial results for the quarter ended September 30, 2026", "results", "filing"),
    ("Board Meeting Intimation", "Intimation of board meeting to consider financial results", "results", "notice"),
    ("Copy of Newspaper Publication", "Newspaper publication of financial results", "results", "ad"),
    ("Change in Directors/ Key Managerial Personnel", "Resignation of Mr. X as Chief Financial Officer", "management_change", "senior"),
    ("Change in Directors/ Key Managerial Personnel", "Appointment of Ms. Y as Company Secretary and Compliance Officer", "management_change", "minor"),
    ("Analysts/Institutional Investor Meet/Con. Call Updates", "Transcript of the earnings conference call", "earnings_call", "transcript"),
    ("Analysts/Institutional Investor Meet/Con. Call Updates", "Schedule of analyst meet with Nomura", "investor_meetings", "meet"),
    ("Credit Rating", "CRISIL downgraded long-term rating to AA-", "credit_rating", "downgrade"),
    ("Credit Rating", "ICRA reaffirmed rating", "credit_rating", "reaffirm"),
    ("Acquisition", "Acquisition of 51% stake in ABC Pvt Ltd", "M&A", "deal"),
    ("Trading Window", "Closure of trading window", "unclassified", "routine"),
    ("ESOP/ESOS/ESPS", "Allotment of equity shares under ESOP 2021", "unclassified", "routine"),
    ("Disclosure under SEBI Takeover Regulations", "Disclosure of encumbrance under Regulation 31", "pledging", "pledge"),
    ("Updates", "Receipt of order worth Rs 1,200 crore from NHAI", "press_release", "news"),
    ("Action(s) initiated or orders passed", "GST demand order of Rs 45 crore", "litigation", "matter"),
])
def test_classify(desc, subject, cat, sub):
    assert classify(desc, subject) == (cat, sub)


def test_score_orders_material_above_routine():
    watched = ["results", "management_change"]
    results = score.score("results", "filing", "Q2 results", 9, watched)
    cfo = score.score("management_change", "senior", "CFO resigns", 3, watched)
    agm = score.score("agm_egm", "meeting", "Notice of AGM", 9, watched)
    junk = score.score("unclassified", "routine", "Trading window", 9, watched)
    assert results > cfo > agm > junk
    assert score.tier(results) == "act" and score.tier(junk) == "routine"


def test_market_reaction_lifts_a_filing():
    base = score.score("press_release", "news", "Order win", 5, [])
    moved = score.score("press_release", "news", "Order win", 5, [], reaction={"change_pct": -5.2, "vol_ratio": 3.0})
    assert moved - base == 12


def test_results_card_math():
    raw = {
        "basis": "consolidated", "format": "standard", "unit": "₹ in lakhs",
        "periods": {"current": "Q2 FY27", "previous": "Q1 FY27", "year_ago": "Q2 FY26"},
        "revenue": {"current": 120000, "previous": 100000, "year_ago": 96000},
        "other_income": {"current": 2000, "previous": 1500, "year_ago": 1000},
        "finance_costs": {"current": 1000, "previous": 1000, "year_ago": 1200},
        "depreciation": {"current": 3000, "previous": 2900, "year_ago": 2500},
        "exceptional_items": {"current": None, "previous": None, "year_ago": None},
        "pbt": {"current": 20000, "previous": 16000, "year_ago": 16000},
        "pat": {"current": 15000, "previous": 12000, "year_ago": -500},
    }
    card = enrich.build_results_card(raw)
    m = {x["label"]: x for x in card["metrics"]}
    assert m["Revenue"]["current"] == 1200.0          # lakh -> crore
    assert m["Revenue"]["qoq"] == 20.0 and m["Revenue"]["yoy"] == 25.0
    assert m["EBITDA"]["current"] == 220.0            # (20000 + 1000 + 3000 - 2000) / 100
    assert m["PAT"]["yoy"] == 3100.0                  # off a negative base, measured against |base|
    assert card["margin"] == round(220 / 1200 * 100, 1)


def test_bank_results_use_ppop():
    raw = {"basis": "standalone", "format": "bank", "unit": "crore", "periods": {},
           "revenue": {"current": 80000, "previous": 78000, "year_ago": 70000},
           "operating_profit_before_provisions": {"current": 25000, "previous": 24000, "year_ago": 22000},
           "pbt": {"current": 21000}, "pat": {"current": 16000}}
    card = enrich.build_results_card(raw)
    assert card["metrics"][1]["label"] == "PPOP" and card["metrics"][1]["current"] == 25000


SCREENER_HTML = """
<h1>Acme Industries Ltd</h1>
<div class="company-profile"><div class="about"><p>Acme makes widgets and gizmos.</p></div></div>
<ul id="top-ratios">
 <li><span class="name">Market Cap</span><span class="number">12,345</span></li>
 <li><span class="name">Stock P/E</span><span class="number">31.2</span></li>
</ul>
<section id="quarters"><table class="data-table">
 <thead><tr><th></th><th>Sep 2025</th><th>Dec 2025</th><th>Mar 2026</th><th>Jun 2026</th><th>Sep 2026</th></tr></thead>
 <tbody>
  <tr><td class="text">Sales&nbsp;<button>+</button></td><td>100</td><td>110</td><td>120</td><td>115</td><td>130</td></tr>
  <tr><td class="text">OPM %</td><td>18%</td><td>19%</td><td>20%</td><td>17%</td><td>21%</td></tr>
  <tr><td class="text">Net Profit +</td><td>10</td><td>12</td><td>14</td><td>11</td><td>15</td></tr>
 </tbody></table></section>
<section id="profit-loss"><table class="data-table">
 <thead><tr><th></th><th>Mar 2022</th><th>Mar 2023</th><th>Mar 2024</th><th>Mar 2025</th><th>Mar 2026</th><th>TTM</th></tr></thead>
 <tbody>
  <tr><td>Sales +</td><td>200</td><td>250</td><td>300</td><td>350</td><td>450</td><td>475</td></tr>
  <tr><td>Net Profit +</td><td>20</td><td>25</td><td>32</td><td>40</td><td>47</td><td>52</td></tr>
 </tbody></table></section>
<section id="cash-flow"><table class="data-table">
 <thead><tr><th></th><th>Mar 2025</th><th>Mar 2026</th></tr></thead>
 <tbody><tr><td>Cash from Operating Activity +</td><td>36</td><td>30</td></tr>
 <tr><td>Cash from Investing Activity +</td><td>-20</td><td>-25</td></tr></tbody></table></section>
<section id="documents">
 <div class="annual-reports"><ul><li><a href="https://www.bseindia.com/ar/2026.pdf">Financial Year 2026 from bse</a></li></ul></div>
 <div class="concalls"><ul>
  <li><div>Nov 2026</div><a class="concall-link" href="https://x/t1.pdf">Transcript</a><a href="https://x/p1.pdf">PPT</a></li>
  <li><div>Aug 2026</div><a class="concall-link" href="https://x/p0.pdf">PPT</a></li>
 </ul></div>
</section>
"""


def test_screener_parser_and_lenses():
    co = screener.parse_company(SCREENER_HTML)
    co["symbol"] = "ACME"
    assert co["name"] == "Acme Industries Ltd"
    assert co["ratios"]["Market Cap"] == 12345
    q = co["tables"]["quarters"]
    assert q["rows"]["Sales"] == [100, 110, 120, 115, 130]
    assert q["rows"]["OPM %"][-1] == 21
    assert co["documents"]["concalls"] == [{"period": "Nov 2026", "transcript": "https://x/t1.pdf", "ppt": "https://x/p1.pdf"}]
    assert co["documents"]["annual_reports"][0]["url"].endswith("2026.pdf")

    snap = financials.snapshot(co)
    assert snap["sales_ttm"] == 475 and snap["np_ttm"] == 52

    traj = financials.trajectory(co)
    assert traj["annual"]["sales"][-1] == ("Mar 2026", 450)   # TTM dropped
    assert traj["sales_cagr_3y"] == round(((450 / 250) ** (1 / 3) - 1) * 100, 1)
    assert traj["quarterly"]["sales"][-1][2] == 30.0           # Sep26 vs Sep25

    cash = financials.cash_quality(co)
    assert cash["years"][-1]["conversion"] == round(30 / 47, 2)
    assert cash["conversion_5y"] == round(66 / 87, 2)


def test_quote_verification():
    transcript = guidance._norm("""Moderator: thank you. Rajesh Kumar: So for FY27 we are guiding to
    revenue growth of 14% to 16%, and we expect EBITDA margins to be in the 21-22% band by the fourth quarter.""")
    assert guidance.quote_in("we are guiding to revenue growth of 14% to 16%", transcript)
    assert guidance.quote_in("We expect EBITDA margins to be in the 21–22% band by the fourth quarter", transcript)
    assert not guidance.quote_in("we expect margins to expand to 25% next year", transcript)
