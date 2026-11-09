import logging

import requests

from .. import db, portfolio, settings
from ..config import NTFY_TOPIC
from ..sources import prices

log = logging.getLogger(__name__)


def evaluate():
    """Check the latest EOD session for every holding against the user's thresholds."""
    cfg = settings.get()
    new = []
    for sym in portfolio.symbols():
        st = prices.day_stats(sym)
        if not st:
            continue
        found = []
        if abs(st["change_pct"]) >= cfg["price_pct"]:
            word = "up" if st["change_pct"] > 0 else "down"
            found.append(("price", st["change_pct"], f"{sym} {word} {abs(st['change_pct']):.1f}% to ₹{st['close']:,.1f}"))
        if st["vol_ratio"] >= cfg["vol_mult"]:
            found.append(("volume", st["vol_ratio"], f"{sym} traded {st['vol_ratio']:.1f}× its 20-day volume"))
        for kind, value, msg in found:
            aid = f"{sym}:{st['date']}:{kind}"
            with db.session() as c:
                cur = c.execute("insert or ignore into alerts (id, symbol, date, kind, value, message) "
                                "values (?,?,?,?,?,?)", (aid, sym, st["date"], kind, value, msg))
                if cur.rowcount:
                    new.append(aid)
    return new


def filing_alerts():
    """High-priority filings in watched categories become alerts too."""
    cfg = settings.get()
    marks = ",".join("?" * len(cfg["watch"])) or "''"
    with db.session() as c:
        rows = c.execute(
            f"select id, symbol, filed_at, category, subject, summary from filings "
            f"where tier = 'act' and category in ({marks}) and filed_at >= datetime('now', '-3 days')",
            cfg["watch"]).fetchall()
        new = []
        for r in rows:
            msg = f"{r['symbol']} · {r['category'].replace('_', ' ')}: {r['summary'] or r['subject']}"
            cur = c.execute("insert or ignore into alerts (id, symbol, date, kind, value, message) "
                            "values (?,?,?,?,?,?)",
                            (f"filing:{r['id']}", r["symbol"], r["filed_at"][:10], "filing", 0, msg[:240]))
            if cur.rowcount:
                new.append(f"filing:{r['id']}")
    return new


def push_pending():
    if not NTFY_TOPIC:
        return 0
    with db.session() as c:
        rows = c.execute("select id, symbol, message from alerts where pushed = 0").fetchall()
        sent = 0
        for r in rows:
            try:
                requests.post(f"https://ntfy.sh/{NTFY_TOPIC}", data=r["message"].encode(),
                              headers={"Title": f"FINN · {r['symbol']}", "Tags": "chart_with_upwards_trend"},
                              timeout=10)
                c.execute("update alerts set pushed = 1 where id = ?", (r["id"],))
                sent += 1
            except requests.RequestException as e:
                log.warning("ntfy push failed: %s", e)
    return sent


def recent(days=7):
    anchor = db.kv_get("last_refresh") or "now"
    with db.session() as c:
        rows = c.execute("select * from alerts where date >= date(?, ?) order by date desc, created_at desc",
                         (anchor, f"-{days} days")).fetchall()
    return [dict(r) for r in rows]
