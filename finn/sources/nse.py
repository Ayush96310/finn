import hashlib
import logging
import time
from datetime import datetime, timedelta

import requests

from ..config import USER_AGENT

log = logging.getLogger(__name__)

BASE = "https://www.nseindia.com"
API = BASE + "/api/corporate-announcements"
ARCHIVE = "https://nsearchives.nseindia.com/corporate/"

_session = None


def _get_session():
    # NSE hands out the cookies its API wants only after a normal page visit.
    global _session
    if _session is None:
        s = requests.Session()
        s.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": BASE + "/companies-listing/corporate-filings-announcements",
        })
        s.get(BASE, timeout=15)
        s.get(BASE + "/companies-listing/corporate-filings-announcements", timeout=15)
        _session = s
    return _session


def _fetch(params, retries=3):
    global _session
    for attempt in range(retries):
        try:
            r = _get_session().get(API, params=params, timeout=30)
            if r.status_code == 401 or r.status_code == 403:
                _session = None
                time.sleep(1 + attempt)
                continue
            r.raise_for_status()
            data = r.json()
            return data if isinstance(data, list) else data.get("data", [])
        except (requests.RequestException, ValueError) as e:
            log.warning("NSE fetch failed (%s), attempt %d", e, attempt + 1)
            _session = None
            time.sleep(1 + attempt)
    return []


def _parse_time(item):
    for key, fmt in (("sort_date", "%Y-%m-%d %H:%M:%S"), ("an_dt", "%d-%b-%Y %H:%M:%S")):
        v = item.get(key)
        if v:
            try:
                return datetime.strptime(v, fmt)
            except ValueError:
                pass
    return None


def normalise(item):
    filed = _parse_time(item)
    attachment = item.get("attchmntFile") or ""
    if attachment and not attachment.startswith("http"):
        attachment = ARCHIVE + attachment.lstrip("/")
    raw_id = item.get("seq_id") or f"{item.get('symbol')}|{item.get('an_dt')}|{item.get('attchmntText')}"
    return {
        "id": hashlib.sha1(str(raw_id).encode()).hexdigest()[:16],
        "symbol": (item.get("symbol") or "").upper(),
        "filed_at": filed.strftime("%Y-%m-%d %H:%M:%S") if filed else None,
        "nse_category": (item.get("desc") or "").strip(),
        "subject": " ".join((item.get("attchmntText") or "").split()),
        "attachment": attachment,
    }


def announcements(symbols, days=7):
    end = datetime.now()
    start = end - timedelta(days=days)
    params = {"index": "equities", "from_date": start.strftime("%d-%m-%Y"),
              "to_date": end.strftime("%d-%m-%Y")}
    wanted = set(symbols)

    # One market-wide call is cheaper than 18 per-symbol calls; fall back if NSE truncates it.
    items = [normalise(i) for i in _fetch(params)]
    found = {i["symbol"] for i in items if i["symbol"] in wanted}
    out = [i for i in items if i["symbol"] in wanted]
    for sym in wanted - found:
        time.sleep(0.4)
        out += [normalise(i) for i in _fetch({**params, "symbol": sym})]
    return [i for i in out if i["filed_at"]]
