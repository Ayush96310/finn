import os
from pathlib import Path

from fastapi import Body, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import db, llm, portfolio, settings
from .push import alerts, digest
from .pull import research

app = FastAPI(title="FINN")
WEB = Path(__file__).resolve().parent.parent / "web"


@app.get("/api/meta")
def meta():
    return {"as_of": digest.as_of().isoformat(timespec="minutes"), "llm": llm.available(),
            "sample": bool(db.kv_get("sample_data")), "settings": settings.get()}


@app.get("/api/digest")
def get_digest(hours: int | None = None):
    return digest.build(hours or settings.get()["window_hours"])


@app.get("/api/alerts")
def get_alerts(days: int = 7):
    return alerts.recent(days)


@app.get("/api/portfolio")
def get_portfolio():
    return {"holdings": portfolio.get_portfolio(), "research_demo": portfolio.RESEARCH_DEMO}


@app.get("/api/settings")
def get_settings():
    return settings.get()


@app.put("/api/settings")
def put_settings(patch: dict = Body(...)):
    s = settings.update(patch)
    # Thresholds changed: re-run the price checks so the alert list reflects them immediately.
    alerts.evaluate()
    return s


@app.post("/api/research/{symbol}")
def start_research(symbol: str, refresh: bool = False):
    try:
        return research.start(symbol, refresh)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/research/{symbol}")
def get_research(symbol: str):
    symbol = symbol.upper()
    return {"status": research.status(symbol), "data": research.cached(symbol)}


@app.post("/api/research/{symbol}/ask")
def ask(symbol: str, body: dict = Body(...)):
    q = (body.get("q") or "").strip()
    if not q or len(q) > 500:
        raise HTTPException(400, "question required")
    if not llm.available():
        raise HTTPException(503, "LLM not configured on this deployment")
    return research.question(symbol.upper(), q)


@app.get("/api/usage")
def usage():
    return llm.usage_summary()


@app.post("/api/refresh")
def refresh(days: int = 2, x_finn_token: str = Header(default="")):
    token = os.getenv("FINN_ADMIN_TOKEN")
    if not token or x_finn_token != token:
        raise HTTPException(403, "refresh is disabled on this deployment")
    from .push import pipeline
    return pipeline.refresh(days)


app.mount("/static", StaticFiles(directory=WEB), name="static")


@app.get("/")
@app.get("/r/{rest:path}")
def index(rest: str = ""):
    return FileResponse(WEB / "index.html")


@app.get("/manifest.webmanifest")
def manifest():
    return FileResponse(WEB / "manifest.webmanifest", media_type="application/manifest+json")


@app.get("/sw.js")
def sw():
    return FileResponse(WEB / "sw.js", media_type="text/javascript")
