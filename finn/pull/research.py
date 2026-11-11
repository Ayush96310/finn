import logging
import re
import threading
import time
from datetime import datetime

from .. import db, llm
from ..sources import screener
from . import ask, documents, financials, guidance, thesis

log = logging.getLogger(__name__)

_jobs = {}
_lock = threading.Lock()
SYMBOL = re.compile(r"^[A-Z0-9&\-]{1,20}$")
UNFINISHED = ("The model didn't finish judging these calls (it was overloaded or timed out). "
              "Open this company again to retry; the transcripts already read are cached.")


def _set(symbol, **kw):
    with _lock:
        _jobs.setdefault(symbol, {}).update(kw)


def status(symbol):
    with _lock:
        return dict(_jobs.get(symbol, {}))


def cached(symbol):
    return db.kv_get(f"research:{symbol}")


def run(symbol, refresh=False):
    symbol = symbol.upper().strip()
    _set(symbol, state="running", step="Pulling financials from screener", started=time.time(), error=None)
    try:
        co = screener.company(symbol, refresh=refresh)
        snap = financials.snapshot(co)
        traj = financials.trajectory(co)
        bs = financials.balance_sheet(co)
        cash = financials.cash_quality(co)
        out = {"symbol": symbol, "name": co.get("name"), "about": co.get("about"),
               "snapshot": snap, "trajectory": traj, "balance_sheet": bs, "cash": cash,
               "generated_at": datetime.now().isoformat(timespec="minutes"), "llm": llm.available()}
        db.kv_set(f"research:{symbol}", out)  # numbers are useful on their own; show them early

        if llm.available():
            _set(symbol, step="Reading the last five concall transcripts")
            calls = documents.transcripts(co, n=5)
            _set(symbol, step=f"Checking {len(calls)} calls: promised vs delivered")
            # Each narrative lens stands alone: one model failure shouldn't take the others down with it.
            try:
                out["guidance"] = guidance.promised_vs_delivered(co, calls[:5]) if calls else None
            except Exception:
                log.exception("promised vs delivered failed for %s", symbol)
                out["guidance"] = {"items": [], "calls": [], "note": UNFINISHED, "unfinished": True}
            db.kv_set(f"research:{symbol}", out)

            _set(symbol, step="Reading the annual report MD&A")
            ar = documents.annual_report_mdna(co)
            _set(symbol, step="Writing business snapshot and bull/bear")
            try:
                out["thesis"] = thesis.build(co, thesis.numbers_brief(snap, traj, bs, cash), ar,
                                             calls[0] if calls else None)
            except Exception:
                log.exception("thesis failed for %s", symbol)
                out["thesis"] = None
            out["sources"] = {
                "annual_report": {"title": ar["title"], "url": ar["url"]} if ar else None,
                "calls": [{"period": c["period"], "url": c["url"]} for c in calls],
            }
            corpus = []
            if ar:
                corpus += documents.chunk(ar["text"], ar["title"])
            for c in calls[:4]:
                corpus += documents.chunk(c["text"], f"{c['period']} call")
            db.kv_set(f"corpus:{symbol}", corpus)

        db.kv_set(f"research:{symbol}", out)
        _set(symbol, state="done", step=None)
        return out
    except Exception as e:
        log.exception("research failed for %s", symbol)
        msg = str(e)
        if "ConnectionPool" in msg or "Tunnel" in msg:
            msg = "Couldn't reach screener.in from this server."
        _set(symbol, state="error", error=msg, step=None)
        raise


def start(symbol, refresh=False):
    symbol = symbol.upper().strip()
    if not SYMBOL.match(symbol):
        raise ValueError("not a valid NSE symbol")
    if status(symbol).get("state") == "running":
        return status(symbol)

    def work():
        try:
            run(symbol, refresh)
        except Exception:
            pass

    _set(symbol, state="running", step="Starting", error=None)
    threading.Thread(target=work, daemon=True).start()
    return status(symbol)


def question(symbol, q):
    corpus = db.kv_get(f"corpus:{symbol}")
    if not corpus:
        return {"answer": "Run the research view for this company first so FINN has its documents.",
                "sources": []}
    name = (cached(symbol) or {}).get("name") or symbol
    return ask.answer(name, corpus, q)
