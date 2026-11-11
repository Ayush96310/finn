import logging
from datetime import datetime, timedelta, timezone

from .. import db

log = logging.getLogger(__name__)
IST = timezone(timedelta(hours=5, minutes=30))


def last_complete_session(now=None):
    """Yahoo serves today's bar while the market is still open; a half-day's volume would read as a
    collapse against the 20-day average. NSE closes at 15:30 IST, so count today only after 15:45."""
    now = now or datetime.now(IST)
    return now.date() if (now.hour, now.minute) >= (15, 45) else now.date() - timedelta(days=1)


def refresh(symbols, period="6mo"):
    import yfinance as yf

    tickers = [f"{s}.NS" for s in symbols]
    frame = yf.download(tickers, period=period, interval="1d", group_by="ticker",
                        auto_adjust=False, progress=False, threads=True)
    rows = []
    cutoff = last_complete_session().isoformat()
    for sym, tk in zip(symbols, tickers):
        try:
            df = frame[tk] if len(tickers) > 1 else frame
        except KeyError:
            log.warning("no price data for %s", tk)
            continue
        df = df.dropna(subset=["Close"])
        for date, r in df.iterrows():
            if date.strftime("%Y-%m-%d") > cutoff:
                continue
            rows.append((sym, date.strftime("%Y-%m-%d"), float(r["Open"]), float(r["High"]),
                         float(r["Low"]), float(r["Close"]), int(r["Volume"] or 0)))
    with db.session() as c:
        c.execute("delete from prices where date > ?", (cutoff,))  # intraday bars from an earlier run
        c.executemany("insert or replace into prices values (?,?,?,?,?,?,?)", rows)
    return len(rows)


def history(symbol, days=90):
    with db.session() as c:
        rows = c.execute(
            "select date, close, volume from prices where symbol = ? order by date desc limit ?",
            (symbol, days),
        ).fetchall()
    return [dict(r) for r in reversed(rows)]


def day_stats(symbol, lookback=20):
    """Latest session vs the trailing window. None if we don't have enough history."""
    h = history(symbol, lookback + 1)
    if len(h) < 6:
        return None
    last, prev, window = h[-1], h[-2], h[:-1]
    vols = [d["volume"] for d in window if d["volume"]]
    avg_vol = sum(vols) / len(vols) if vols else 0
    return {
        "date": last["date"],
        "close": last["close"],
        "change_pct": (last["close"] / prev["close"] - 1) * 100 if prev["close"] else 0,
        "volume": last["volume"],
        "vol_ratio": last["volume"] / avg_vol if avg_vol else 0,
        "spark": [d["close"] for d in h],
    }


def move_on(symbol, date):
    """Price reaction on a given session; used to tag filings the market actually cared about."""
    with db.session() as c:
        rows = c.execute(
            "select date, close, volume from prices where symbol = ? and date <= ? "
            "order by date desc limit 21", (symbol, date)).fetchall()
    if len(rows) < 6 or rows[0]["date"] != date:
        return None
    vols = [r["volume"] for r in rows[1:] if r["volume"]]
    avg = sum(vols) / len(vols) if vols else 0
    return {
        "change_pct": (rows[0]["close"] / rows[1]["close"] - 1) * 100,
        "vol_ratio": rows[0]["volume"] / avg if avg else 0,
    }
