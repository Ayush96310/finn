"""Numbers lenses. No LLM in here on purpose: ratios and growth rates are arithmetic,
and an analyst should be able to trace every figure back to a table cell."""

ALIASES = {
    "sales": ["Sales", "Revenue"],
    "op": ["Operating Profit", "Financing Profit"],
    "opm": ["OPM %", "Financing Margin %"],
    "other_income": ["Other Income"],
    "interest": ["Interest"],
    "dep": ["Depreciation"],
    "pbt": ["Profit before tax"],
    "np": ["Net Profit"],
    "eps": ["EPS in Rs"],
    "equity": ["Equity Capital"],
    "reserves": ["Reserves"],
    "borrowings": ["Borrowings", "Borrowing"],
    "deposits": ["Deposits"],
    "total_liab": ["Total Liabilities"],
    "fixed": ["Fixed Assets"],
    "cwip": ["CWIP"],
    "investments": ["Investments"],
    "cfo": ["Cash from Operating Activity"],
    "cfi": ["Cash from Investing Activity"],
    "cff": ["Cash from Financing Activity"],
    "debtor_days": ["Debtor Days"],
    "inventory_days": ["Inventory Days"],
    "payable_days": ["Days Payable"],
    "ccc": ["Cash Conversion Cycle"],
    "wc_days": ["Working Capital Days"],
    "roce": ["ROCE %"],
    "roe": ["ROE %"],
}


def row(table, key):
    if not table:
        return None
    for name in ALIASES.get(key, [key]):
        if name in table["rows"]:
            return table["rows"][name]
    return None


def series(table, key, n=None, drop_ttm=True):
    vals = row(table, key)
    if not vals:
        return []
    periods = table["periods"][:len(vals)]
    pairs = list(zip(periods, vals))
    if drop_ttm:
        pairs = [p for p in pairs if p[0].upper() != "TTM"]
    return pairs[-n:] if n else pairs


def cagr(pairs, years):
    vals = [v for _, v in pairs if v is not None]
    if len(vals) <= years or vals[-1 - years] in (None, 0) or vals[-1 - years] < 0 or vals[-1] <= 0:
        return None
    return round(((vals[-1] / vals[-1 - years]) ** (1 / years) - 1) * 100, 1)


def yoy_quarterly(pairs):
    out = []
    for i, (p, v) in enumerate(pairs):
        prev = pairs[i - 4][1] if i >= 4 else None
        out.append((p, v, round((v - prev) / abs(prev) * 100, 1) if v is not None and prev else None))
    return out


def _last(pairs):
    return pairs[-1][1] if pairs else None


def snapshot(co):
    t = co["tables"]
    pl = t.get("profit-loss")
    ttm_sales = row(pl, "sales")
    ttm_np = row(pl, "np")
    has_ttm = pl and pl["periods"] and pl["periods"][-1].upper() == "TTM"
    r = co.get("ratios", {})
    return {
        "market_cap": r.get("Market Cap"),
        "price": r.get("Current Price"),
        "pe": r.get("Stock P/E"),
        "roce": r.get("ROCE"),
        "roe": r.get("ROE"),
        "div_yield": r.get("Dividend Yield"),
        "book_value": r.get("Book Value"),
        "sales_ttm": ttm_sales[-1] if has_ttm and ttm_sales else _last(series(pl, "sales")),
        "np_ttm": ttm_np[-1] if has_ttm and ttm_np else _last(series(pl, "np")),
        "opm_last": _last(series(pl, "opm")),
        "basis": co.get("basis"),
    }


def trajectory(co):
    pl, q = co["tables"].get("profit-loss"), co["tables"].get("quarters")
    sales, np_, opm = series(pl, "sales", 8), series(pl, "np", 8), series(pl, "opm", 8)
    q_sales = yoy_quarterly(series(q, "sales", 12))[-8:]
    q_np = yoy_quarterly(series(q, "np", 12))[-8:]
    q_opm = series(q, "opm", 8)

    opm_vals = [v for _, v in opm if v is not None]
    margin_trend = None
    if len(opm_vals) >= 4:
        recent, base = opm_vals[-1], sum(opm_vals[-4:-1]) / 3
        margin_trend = round(recent - base, 1)

    return {
        "annual": {"sales": sales, "np": np_, "opm": opm},
        "quarterly": {"sales": q_sales, "np": q_np, "opm": q_opm},
        "sales_cagr_3y": cagr(sales, 3), "sales_cagr_5y": cagr(sales, 5),
        "np_cagr_3y": cagr(np_, 3), "np_cagr_5y": cagr(np_, 5),
        "margin_vs_3y_avg_pp": margin_trend,
    }


def balance_sheet(co):
    bs, ratios = co["tables"].get("balance-sheet"), co["tables"].get("ratios")
    eq, res, debt = series(bs, "equity"), series(bs, "reserves"), series(bs, "borrowings")
    de = []
    for (p, e), (_, rv), (_, d) in zip(eq, res, debt):
        if e is not None and rv is not None and d is not None and (e + rv) > 0:
            de.append((p, round(d / (e + rv), 2)))
    return {
        "borrowings": debt[-6:],
        "net_worth": [(p, (e or 0) + (r or 0)) for (p, e), (_, r) in zip(eq, res)][-6:],
        "debt_to_equity": de[-6:],
        "cwip": series(bs, "cwip", 6),
        "deposits": series(bs, "deposits", 6),
        "working_capital": {k: series(ratios, k, 6) for k in
                            ("debtor_days", "inventory_days", "payable_days", "ccc", "wc_days")},
        "roce": series(ratios, "roce", 6),
    }


def cash_quality(co):
    cf, pl = co["tables"].get("cash-flow"), co["tables"].get("profit-loss")
    cfo, cfi = dict(series(cf, "cfo")), dict(series(cf, "cfi"))
    np_ = dict(series(pl, "np"))
    years = [p for p in cfo if p in np_][-6:]
    rows = []
    for y in years:
        c, n, i = cfo.get(y), np_.get(y), cfi.get(y)
        rows.append({"period": y, "cfo": c, "pat": n, "cfi": i,
                     "conversion": round(c / n, 2) if c is not None and n and n > 0 else None,
                     "after_investing": round(c + i, 1) if c is not None and i is not None else None})
    tot_c = sum(r["cfo"] or 0 for r in rows[-5:])
    tot_n = sum(r["pat"] or 0 for r in rows[-5:])
    return {"years": rows, "conversion_5y": round(tot_c / tot_n, 2) if tot_n > 0 else None}


def quarterly_table_for_prompt(co, n=8):
    """Compact actuals block handed to the guidance reasoner, so it never has to do arithmetic."""
    q = co["tables"].get("quarters")
    s = yoy_quarterly(series(q, "sales", n + 4))[-n:]
    p = yoy_quarterly(series(q, "np", n + 4))[-n:]
    m = dict(series(q, "opm", n + 4))
    lines = ["quarter | revenue (₹cr) | revenue YoY % | operating margin % | net profit (₹cr) | net profit YoY %"]
    for (per, sv, sg), (_, pv, pg) in zip(s, p):
        lines.append(f"{per} | {sv} | {sg} | {m.get(per)} | {pv} | {pg}")
    pl = co["tables"].get("profit-loss")
    a = series(pl, "sales", 4)
    if a:
        lines.append("\nannual revenue: " + ", ".join(f"{per}: {v}" for per, v in a))
    lines += annual_actuals(co)
    return "\n".join(lines)


def annual_actuals(co, years=3):
    """Year-end figures that promises about cash, working capital and capex can be judged against."""
    t = co["tables"]
    fy = lambda pairs: [(p, v) for p, v in pairs if p.startswith("Mar")]  # noqa: E731
    out = []
    for label, table, key in (("operating cash flow (₹cr)", "cash-flow", "cfo"),
                              ("working capital days", "ratios", "wc_days"),
                              ("debtor days", "ratios", "debtor_days"),
                              ("inventory days", "ratios", "inventory_days"),
                              ("borrowings (₹cr)", "balance-sheet", "borrowings")):
        pairs = fy(series(t.get(table), key))[-years:]
        if pairs:
            out.append(f"{label}: " + ", ".join(f"{p}: {v}" for p, v in pairs))
    # Capex isn't reported directly: change in net fixed assets and CWIP, plus the year's depreciation.
    # Acquisitions and reclassifications distort it, so negative years are dropped and the label says so.
    assets = {p: (f or 0) + (c or 0) for (p, f), (_, c) in zip(fy(series(t.get("balance-sheet"), "fixed")),
                                                                fy(series(t.get("balance-sheet"), "cwip")))}
    dep = dict(series(t.get("profit-loss"), "dep"))
    periods = sorted(assets, key=lambda p: int(p.split()[-1]))
    capex = [(p, round(assets[p] - assets[q] + (dep.get(p) or 0)))
             for q, p in zip(periods, periods[1:]) if dep.get(p) is not None]
    capex = [(p, v) for p, v in capex[-years:] if v >= 0]
    if capex:
        out.append("capex, rough estimate from the balance sheet, includes acquisitions (₹cr): " +
                   ", ".join(f"{p}: {v}" for p, v in capex))
    return ["\nyear-end figures:", *out] if out else []
