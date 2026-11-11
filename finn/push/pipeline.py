import logging
from datetime import datetime

from .. import db, llm, portfolio, settings
from ..sources import nse, prices, screener
from . import alerts, classify, digest, enrich, score

log = logging.getLogger(__name__)

SUMMARY_BATCH = 8
# Categories where a second filing of the same kind is usually the same event moving on. Catch-alls like
# press_release/news are excluded: two of those are rarely related.
EVENT_CATEGORIES = {"M&A", "fund_raise", "litigation", "credit_rating", "capex", "pledging", "insider_trading"}


def ingest(days):
    items = nse.announcements(portfolio.symbols(), days=days)
    cfg = settings.get()
    added = 0
    with db.session() as c:
        for it in items:
            cat, sub = classify.classify(it["nse_category"], it["subject"])
            s = score.score(cat, sub, it["subject"], portfolio.weight_of(it["symbol"]), cfg["watch"])
            cur = c.execute(
                "insert or ignore into filings (id, symbol, filed_at, nse_category, subject, attachment, "
                "category, subtype, score, tier) values (?,?,?,?,?,?,?,?,?,?)",
                (it["id"], it["symbol"], it["filed_at"], it["nse_category"], it["subject"],
                 it["attachment"], cat, sub, s, score.tier(s)))
            added += cur.rowcount
    return added, len(items)


def context(f):
    """Judge a filing against the company's other recent filings: the market reaction is credited only to
    the most material filing priced in that session, and a repeat of the same kind of filing within ten
    days (a deal's agreement, then its completion) is a follow-up."""
    with db.session() as c:
        others = [dict(r) for r in c.execute(
            "select id, symbol, filed_at, category, subtype from filings where symbol = ? and id != ? "
            "and filed_at between datetime(?, '-10 days') and datetime(?, '+4 days')",
            (f["symbol"], f["id"], f["filed_at"], f["filed_at"]))]
    followup = f["category"] in EVENT_CATEGORIES and any(
        (o["category"], o["subtype"]) == (f["category"], f["subtype"]) and o["filed_at"] < f["filed_at"]
        for o in others)
    reaction = digest.reaction_for(f)
    if reaction:
        rank = lambda x: (score.BASE.get((x["category"], x["subtype"]), 25), x["filed_at"] < f["filed_at"])  # noqa: E731
        mine = rank(f)
        for o in others:
            theirs = rank(o)
            if theirs[0] > mine[0] or (theirs[0] == mine[0] and theirs[1]):
                r = digest.reaction_for(o)
                if r and r["date"] == reaction["date"]:
                    reaction = None
                    break
    return {"reaction": reaction, "followup": followup}


def rescore_with_reactions():
    """Second pass once prices are in: a filing the market reacted to moves up a tier."""
    cfg = settings.get()
    with db.session() as c:
        rows = [dict(r) for r in c.execute(
            "select id, symbol, filed_at, category, subtype, subject from filings where enriched = 0")]
    for f in rows:
        s = score.score(f["category"], f["subtype"], f["subject"], portfolio.weight_of(f["symbol"]),
                        cfg["watch"], **context(f))
        with db.session() as c:
            c.execute("update filings set score = ?, tier = ? where id = ?", (s, score.tier(s), f["id"]))


def enrich_pending(limit=40):
    if not llm.available():
        log.warning("no GEMINI_API_KEY: skipping enrichment, digest will show raw subjects")
        return 0
    cfg = settings.get()
    with db.session() as c:
        rows = [dict(r) for r in c.execute(
            "select * from filings where enriched = 0 and tier in ('act', 'glance') "
            "order by score desc limit ?", (limit,))]

    to_summarise = []
    for f in rows:
        cat, sub = f["category"], f["subtype"]
        try:
            if cat == "results" and sub == "filing" and f["attachment"]:
                quarters = basis = None
                try:
                    co = screener.company(f["symbol"])
                    quarters, basis = co["tables"]["quarters"], co.get("basis")
                except Exception:
                    pass
                card = enrich.results_card(f, quarters, basis)
                enrich.save_card(f["id"], card=card, summary=_results_line(card))
            elif cat == "management_change" and sub in ("senior", "change") and f["attachment"]:
                card = enrich.people_card(f, portfolio.name_of(f["symbol"]))
                enrich.save_card(f["id"], card=card)
                if sub == "change":
                    # Subjects like "Change in Director(s)" name nobody; the filing says who it is.
                    f["subtype"] = classify.seniority(" ".join(p.get("role") or "" for p in card["people"]))
                    with db.session() as c:
                        c.execute("update filings set subtype = ? where id = ?", (f["subtype"], f["id"]))
                to_summarise.append(f)
            else:
                to_summarise.append(f)
        except Exception as e:
            log.warning("enrichment failed for %s %s: %s", f["symbol"], f["id"], e)
            to_summarise.append(f)

    for i in range(0, len(to_summarise), SUMMARY_BATCH):
        batch = to_summarise[i:i + SUMMARY_BATCH]
        try:
            lines = enrich.summarise_batch(batch)
        except Exception as e:
            log.warning("summary batch failed: %s", e)
            continue
        for f in batch:
            o = lines.get(f["id"])
            if not o:
                continue
            cat, sub = f["category"], f["subtype"]
            s = score.score(cat, sub, f["subject"], portfolio.weight_of(f["symbol"]), cfg["watch"],
                            llm_materiality=o.get("materiality"), **context(f))
            enrich.save_card(f["id"], summary=o.get("line"), score=s, tier=score.tier(s))
    return len(rows)


def _results_line(card):
    m = {x["label"]: x for x in card["metrics"]}
    parts = []
    for k in ("Revenue", "PAT"):
        x = m.get(k)
        if x and x["yoy"] is not None:
            parts.append(f"{k} {x['yoy']:+.0f}% YoY")
    if card.get("margin") is not None:
        parts.append(f"{card['metrics'][1]['label']} margin {card['margin']:.1f}%")
    return " · ".join(parts) or None


def refresh(days=2):
    log.info("prices…")
    n_px = prices.refresh(portfolio.symbols())
    log.info("filings…")
    added, seen = ingest(days)
    rescore_with_reactions()
    log.info("enrichment…")
    enriched = enrich_pending()
    db.kv_set("last_refresh", datetime.now().isoformat(timespec="seconds"))
    new_alerts = alerts.evaluate() + alerts.filing_alerts()
    pushed = alerts.push_pending()
    return {"price_rows": n_px, "filings_seen": seen, "filings_new": added,
            "enriched": enriched, "alerts_new": len(new_alerts), "pushed": pushed}
