from . import db

DEFAULTS = {
    "window_hours": 24,
    "price_pct": 4.0,       # alert when |daily move| crosses this
    "vol_mult": 2.0,        # alert when volume > N x 20-day average
    "watch": ["results", "M&A", "management_change", "litigation", "credit_rating",
              "fund_raise", "pledging"],
}


def get():
    return {**DEFAULTS, **(db.kv_get("settings") or {})}


def update(patch):
    allowed = {k: v for k, v in patch.items() if k in DEFAULTS}
    s = {**get(), **allowed}
    s["price_pct"] = max(0.5, float(s["price_pct"]))
    s["vol_mult"] = max(1.1, float(s["vol_mult"]))
    s["window_hours"] = max(1, int(s["window_hours"]))
    db.kv_set("settings", s)
    return s
