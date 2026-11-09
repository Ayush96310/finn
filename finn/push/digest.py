import json
from collections import defaultdict
from datetime import datetime, timedelta

from .. import db, portfolio
from ..sources import prices


def as_of():
    """The digest clock. Pinned to the last refresh so a deployed snapshot still reads sensibly."""
    v = db.kv_get("last_refresh")
    return datetime.fromisoformat(v) if v else datetime.now()


def reaction_for(filing):
    # Filings after 15:30 IST are priced in the next session.
    t = datetime.fromisoformat(filing["filed_at"])
    day = t.date() if t.hour * 60 + t.minute < 15 * 60 + 30 else t.date() + timedelta(days=1)
    for _ in range(4):
        r = prices.move_on(filing["symbol"], day.isoformat())
        if r:
            return {**r, "date": day.isoformat()}
        day += timedelta(days=1)
    return None


def build(hours=24):
    end = as_of()
    start = end - timedelta(hours=hours)
    with db.session() as c:
        rows = c.execute(
            "select * from filings where filed_at > ? and filed_at <= ? order by score desc, filed_at desc",
            (start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S"))).fetchall()

    tiers = {"act": [], "glance": [], "routine": []}
    routine_groups = defaultdict(list)
    for r in rows:
        f = dict(r)
        f["card"] = json.loads(f["card"]) if f["card"] else None
        f["name"] = portfolio.name_of(f["symbol"])
        f["reaction"] = reaction_for(f)
        tier = f["tier"] or "routine"
        tiers[tier].append(f)
        if tier == "routine":
            routine_groups[f["category"]].append(f)

    return {
        "as_of": end.isoformat(timespec="minutes"),
        "hours": hours,
        "counts": {k: len(v) for k, v in tiers.items()},
        "act": tiers["act"],
        "glance": tiers["glance"],
        "routine": [{"category": k, "count": len(v), "items": v}
                    for k, v in sorted(routine_groups.items(), key=lambda kv: -len(kv[1]))],
        "movers": movers(),
    }


def movers():
    out = []
    for p in portfolio.get_portfolio():
        st = prices.day_stats(p["symbol"])
        if st:
            out.append({"symbol": p["symbol"], "name": p["name"], "weight": p["weight"], **st})
    out.sort(key=lambda m: -abs(m["change_pct"]))
    return out
