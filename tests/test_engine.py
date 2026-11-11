import os
import tempfile

os.environ["FINN_DATA_DIR"] = tempfile.mkdtemp()

import pytest  # noqa: E402

from finn.pull import documents, financials, guidance  # noqa: E402
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
    # Real NSE strings, week of 3-10 Nov 2026.
    ("Analysts/Institutional Investor Meet/Con. Call Updates", "Muthoot Capital Services Limited has informed the Exchange about Transcript of the Conference Call held to discuss the unaudited Financial Results of the Company for the quarter and half-year ended September 30, 2026", "earnings_call", "transcript"),
    ("Analysts/Institutional Investor Meet/Con. Call Updates", "Intimation of Conference Call for Q2 Financial Results (F.Y. 2026-27)", "earnings_call", "notice"),
    ("Analysts/Institutional Investor Meet/Con. Call Updates", "Titan Company Limited has informed the Exchange about Analyst Call Recording", "earnings_call", "recording"),
    ("Analysts/Institutional Investor Meet/Con. Call Updates", "Fujiyama Power Systems Limited has informed the Exchange about Link of Recording of the Earnings Call for Q2 FY2026-27.", "earnings_call", "recording"),
    ("Outcome of Board Meeting", "Bharti Airtel Limited has submitted to the Exchange, the financial results for the period ended September 30, 2026.", "results", "filing"),
    ("Press Release", 'Bharti Airtel Limited has informed the Exchange regarding a press release dated November 05, 2026, titled "Bharti Airtel Limited has informed the Exchange regarding a press release dated November 5, 2026, titled financial results for second quarter (Q2) and six months ended September 30, 2026.".', "results", "press"),
    ("Updates", "Bharti Airtel Limited has informed the Exchange regarding 'Bharti Airtel Limited has informed the Exchange regarding Quarterly Report w.r.t. Financial Results second quarter (Q2) and six months ended September 30, 2026.'.", "results", "deck"),
    ("General Updates", "Maruti Suzuki India Limited has informed the Exchange about Reference to the Financial Results issued by Suzuki Motor Corporation", "press_release", "news"),
    ("Capacity addition", "Interarch Building Solutions Limited has informed the Exchange about Capacity addition", "capex", "capex"),
    ("Demise", "Genus Paper & Boards Limited has informed the Exchange regarding Demise of Mr Ishwar Chand Agarwal, Chairman of the company on November 04, 2026.", "management_change", "senior"),
    ("Open Offer", "ICICI Securities Limited has submitted to the Exchange a copy of the Open Offer from IIFL Capital Services Limited.", "M&A", "deal"),
    ("Monitoring Agency Report", "Laxmi Organic Industries Limited has submitted Monitoring Agency Report issued by India Ratings & Research Private Limited (Monitoring Agent) for the quarter ended September 30, 2026", "unclassified", "routine"),
    ("Credit Rating- Revision", "HBL Engineering Limited has informed the Exchange about Credit Rating- Revision", "credit_rating", "revision"),
    ("Credit Rating", "Reliance Industries Limited has informed the Exchange about Credit Rating", "credit_rating", "rating"),
    ("Credit Rating- Others", "Hindalco Industries Limited has informed the Exchange about ESG Rating.", "unclassified", "routine"),
    ("Resignation of Statutory Auditor", "D. P. Abhushan Limited has informed the Exchange about Resignation of Statutory Auditor", "management_change", "auditor"),
    ("Change in Company Secretary/Compliance Officer", "BLS Polymers Limited has informed the Exchange about Change in Company Secretary/Compliance Officer", "management_change", "minor"),
    ("Cessation", "Chennai Petroleum Corporation Limited has informed the Exchange regarding Cessation of Mr Inderjeet as Non- Executive Director of the company w.e.f. November 06, 2026.", "management_change", "change"),
    ("Cessation", "Veegaland Developers Limited has informed the Exchange regarding Cessation of Mr. Kurian Thomas as Executive Director of the company w.e.f. November 09, 2026.", "management_change", "senior"),
    ("General Updates", "Titan Company Limited has informed the Exchange about Redemption of Commercial Paper", "unclassified", "routine"),
    ("General Updates", "Titan Company Limited has informed the Exchange about Certificate pursuant to SEBI Circular no. SEBI/HO/DDHS/P/CIR/2021/613 dated August 10, 2021", "unclassified", "routine"),
    ("Updates", "Dixon Technologies (India) Limited has informed the Exchange regarding 'Change in Corporate Office Address of RTA with effect from 01st December 2026'.","unclassified", "routine"),
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


def test_results_card_strips_non_operating_income():
    # Titan Q2 FY27 consolidated, as printed (TITAN_05112026165028_SEoutcomeQ227.pdf, p.10). Total income
    # includes a 671 cr fair value gain on a put option that is neither revenue nor other income.
    raw = {
        "basis": "consolidated", "format": "standard", "unit": "crores",
        "periods": {"current": "30-09-2026", "previous": "30-06-2026", "year_ago": "30-09-2025"},
        "revenue": {"current": 20614, "previous": 21356, "year_ago": 18725},
        "other_income": {"current": 145, "previous": 146, "year_ago": 112},
        "total_income": {"current": 21430, "previous": 21502, "year_ago": 18837},
        "finance_costs": {"current": 536, "previous": 353, "year_ago": 277},
        "depreciation": {"current": 263, "previous": 256, "year_ago": 189},
        "exceptional_items": {"current": None, "previous": None, "year_ago": None},
        "pbt": {"current": 3000, "previous": 2429, "year_ago": 1522},
        "pat": {"current": 2393, "previous": 1777, "year_ago": 1120},
    }
    card = enrich.build_results_card(raw)
    m = {x["label"]: x for x in card["metrics"]}
    assert m["EBITDA"]["current"] == 2983          # 3000 + 536 + 263 - 145 - 671
    assert m["EBITDA"]["year_ago"] == 1876         # no gap that quarter
    assert card["margin"] == 14.5
    assert m["PBT"]["current"] == 3000             # reported figures stay as printed
    assert any("671" in f for f in card["flags"])


def test_reconcile_catches_shifted_bank_columns():
    # SBI Q2 FY27 standalone (SBIN_03112026134649_FR_DSC.pdf). The text layer has no exceptional item for
    # Q1, so the first extraction shifted 4,593.22 into Q1 and 7,288.47 into the year-ago column.
    def raw(exceptional):
        return {
            "format": "bank",
            "operating_profit_before_provisions": {"current": 26917.24, "previous": 33529.18, "year_ago": 27310.92},
            "provisions": {"current": 4216.86, "previous": 5046.77, "year_ago": 5400.12},
            "exceptional_items": exceptional,
            "pbt": {"current": 30008.85, "previous": 28482.41, "year_ago": 26504.02},
        }
    shifted = raw({"current": 7288.47, "previous": 4593.22, "year_ago": 7288.47})
    assert enrich.reconcile(shifted) == (["current", "previous", "year_ago"], [])
    assert shifted["exceptional_items"] == {"current": 7288.47, "previous": None, "year_ago": 4593.22}
    # Nothing printed to realign with: say so rather than invent the number.
    missing = raw({"current": None, "previous": None, "year_ago": None})
    assert enrich.reconcile(missing) == (["current", "previous", "year_ago"], ["current", "year_ago"])


def test_reconcile_fixes_exceptional_printed_as_expense():
    # Titan FY26 consolidated: "X. Profit before tax (VIII - IX)" with IX printed as a positive 101.
    raw = {"format": "standard",
           "total_income": {"current": 88136}, "total_expenses": {"current": 81235},
           "exceptional_items": {"current": 101}, "pbt": {"current": 6801}}
    assert enrich.reconcile(raw) == (["current"], [])
    assert raw["exceptional_items"]["current"] == -101


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


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _fixture(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
        return f.read()


def test_screener_real_page_trent():
    # Saved 10 Nov 2026. Trent's concall entries carry no transcript links on screener.
    co = screener.parse_company(_fixture("screener_trent.html"))
    co["symbol"] = "TRENT"
    assert co["name"] == "Trent Ltd"
    q = co["tables"]["quarters"]
    assert q["periods"][-1] == "Sep 2026" and len(q["periods"]) == 13
    assert q["rows"]["Sales"][-1] == 5873 and q["rows"]["Net Profit"][-1] == 468
    assert "Raw PDF" not in q["rows"]
    assert "CFO/EBITDA" in co["tables"]["cash-flow"]["rows"]
    assert co["documents"]["annual_reports"][0]["title"] == "Annual Report 2026"
    assert co["documents"]["concalls"] == []
    assert financials.snapshot(co)["market_cap"] == 166326
    assert financials.trajectory(co)["annual"]["sales"][-1][0] == "Mar 2026"


def test_screener_real_page_concalls():
    co = screener.parse_company(_fixture("screener_persistent.html"))
    calls = co["documents"]["concalls"]
    assert len(calls) == 34
    assert calls[0]["period"] == "Oct 2026"
    assert calls[0]["transcript"].startswith("https://www.bseindia.com/")


def test_mdna_start_skips_contents_and_cross_references():
    # Pattern from Persistent's 500-page FY26 report: a contents entry on p.4, passing mentions on p.88 and
    # p.99, then the MD&A from p.262 with its running header at the end of each page's text.
    pages = ["cover"] * 300
    pages[3] = "Business Responsibility and Sustainability Report 261\nManagement Discussion \nand Analysis Report 342"
    pages[87] = "functions are given in the Management Discussion and Analysis Report forming part"
    pages[98] = "integral part of this Annual Report.\nManagement Discussion and Analysis"
    for i in range(261, 280):
        pages[i] = "Revenue grew 18.2% ... \nManagement Discussion and Analysis\nPersistent Systems Limited"
    assert documents.mdna_start(pages) == 261
    assert documents.mdna_start(["no", "mention", "here"]) is None

    # Trent FY26: no running header; the section opens with a heading on p.109 and is cited later in prose.
    trent = ["body text"] * 262
    trent[5] = "including the \nBoard's Report\nManagement Discussion & \nAnalysis (MD&A)\nCorporate Governance"
    trent[108] = "Trent LimitedIntegrated Annual Report 2025-26\nManagement Discussion and Analysis Report\nThe Management"
    trent[168] = ("x" * 400) + "the information included in the Management Discussion \nand Analysis and Board's Report"
    assert documents.mdna_start(trent) == 108


def test_llm_falls_back_when_model_busy(monkeypatch):
    from finn import llm

    tried = []

    class Reply:
        text, usage_metadata = '{"ok": 1}', None

    class Models:
        def generate_content(self, model, contents, config):
            tried.append(model)
            if model == llm.MODEL_SMART:
                raise RuntimeError("503 UNAVAILABLE. This model is currently experiencing high demand.")
            return Reply()

    class Client:
        models = Models()

    monkeypatch.setattr(llm, "_get_client", lambda: Client())
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    assert llm.call("judge these promises", smart=True, as_json=True) == {"ok": 1}
    assert tried == [llm.MODEL_SMART] * 4 + [llm.MODEL_FAST]


def test_quote_verification():
    transcript = guidance._norm("""Moderator: thank you. Rajesh Kumar: So for FY27 we are guiding to
    revenue growth of 14% to 16%, and we expect EBITDA margins to be in the 21-22% band by the fourth quarter.""")
    assert guidance.quote_in("we are guiding to revenue growth of 14% to 16%", transcript)
    assert guidance.quote_in("We expect EBITDA margins to be in the 21–22% band by the fourth quarter", transcript)
    assert not guidance.quote_in("we expect margins to expand to 25% next year", transcript)
