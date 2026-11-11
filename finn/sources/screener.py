import logging
import re

import requests
from bs4 import BeautifulSoup

from .. import db
from ..config import USER_AGENT

log = logging.getLogger(__name__)

BASE = "https://www.screener.in"
SECTIONS = ["quarters", "profit-loss", "balance-sheet", "cash-flow", "ratios"]


def _num(text):
    t = text.replace(",", "").replace("%", "").strip()
    if t in ("", "-", "--"):
        return None
    try:
        return float(t)
    except ValueError:
        return None


def _clean_label(text):
    return re.sub(r"\s*\+\s*$", "", " ".join(text.split())).strip()


def parse_table(section):
    table = section.find("table", class_="data-table") if section else None
    if not table:
        return None
    head = [th.get_text(strip=True) for th in table.select("thead th")][1:]
    rows = {}
    for tr in table.select("tbody tr"):
        cells = tr.find_all("td")
        if len(cells) < 2:
            continue
        for tip in cells[0].select(".has-tooltip"):
            tip.decompose()
        label = _clean_label(cells[0].get_text(" "))
        values = [_num(td.get_text()) for td in cells[1:]]
        # Skips link-only rows such as "Raw PDF".
        if label and any(v is not None for v in values):
            rows[label] = values
    return {"periods": head, "rows": rows}


def parse_documents(soup):
    docs = {"annual_reports": [], "concalls": []}
    for a in soup.select(".annual-reports a"):
        href = a.get("href")
        if href:
            docs["annual_reports"].append({
                "title": " ".join(a.get_text(" ").split()),
                "url": href if href.startswith("http") else BASE + href,
            })
    for li in soup.select(".concalls li"):
        when = li.find("div")
        entry = {"period": " ".join(when.get_text(" ").split()) if when else ""}
        for a in li.find_all("a"):
            kind = a.get_text(strip=True).lower()
            if a.get("href") and kind in ("transcript", "ppt", "rec", "notes"):
                entry[kind] = a["href"]
        if "transcript" in entry:
            docs["concalls"].append(entry)
    return docs


def parse_company(html):
    soup = BeautifulSoup(html, "html.parser")
    name = soup.select_one("h1")
    about = soup.select_one(".company-profile .about") or soup.select_one(".about")
    ratios = {}
    for li in soup.select("#top-ratios li"):
        k, v = li.select_one(".name"), li.select_one(".number")
        if k and v:
            ratios[k.get_text(strip=True)] = _num(v.get_text())
    tables = {s: parse_table(soup.find("section", id=s)) for s in SECTIONS}
    return {
        "name": name.get_text(strip=True) if name else None,
        "about": " ".join(about.get_text(" ").split()) if about else "",
        "ratios": ratios,
        "tables": tables,
        "documents": parse_documents(soup),
    }


def _has_data(parsed):
    q = parsed["tables"].get("quarters")
    return bool(q and q["rows"])


def company(symbol, refresh=False):
    key = f"screener:{symbol}"
    cached = db.kv_get(key)
    if cached and not refresh:
        return cached

    headers = {"User-Agent": USER_AGENT}
    parsed = None
    for path in (f"/company/{symbol}/consolidated/", f"/company/{symbol}/"):
        r = requests.get(BASE + path, headers=headers, timeout=30)
        if r.status_code == 404:
            continue
        r.raise_for_status()
        parsed = parse_company(r.text)
        parsed["basis"] = "consolidated" if "consolidated" in path else "standalone"
        if _has_data(parsed):
            break
    if not parsed or not _has_data(parsed):
        raise LookupError(f"screener has no financials for {symbol}")
    parsed["symbol"] = symbol
    db.kv_set(key, parsed)
    return parsed
