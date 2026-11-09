"""Thin Gemini wrapper. Every call is cached by content hash and logged with its token count,
so re-running a refresh costs nothing and the app can show what it has spent."""

import hashlib
import json
import logging
import re
import time

from . import db
from .config import GEMINI_API_KEY, MODEL_FAST, MODEL_SMART, PRICES

log = logging.getLogger(__name__)
_client = None


class LLMUnavailable(RuntimeError):
    pass


def _get_client():
    global _client
    if not GEMINI_API_KEY:
        raise LLMUnavailable("GEMINI_API_KEY not set")
    if _client is None:
        from google import genai
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


def _record(model, task, i, o, cached):
    with db.session() as c:
        c.execute("insert into llm_usage (model, task, in_tokens, out_tokens, cached) values (?,?,?,?,?)",
                  (model, task, i, o, int(cached)))


def _parse_json(text):
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1)
    return json.loads(text)


def call(prompt, *, smart=False, task="misc", as_json=False, schema=None, pdf=None,
         temperature=0.1, max_retries=4):
    model = MODEL_SMART if smart else MODEL_FAST
    h = hashlib.sha256()
    h.update(f"{model}|{as_json}|{json.dumps(schema, sort_keys=True) if schema else ''}|".encode())
    h.update(prompt.encode())
    if pdf:
        h.update(hashlib.sha256(pdf).digest())
    key = h.hexdigest()

    with db.session() as c:
        hit = c.execute("select response from llm_cache where key = ?", (key,)).fetchone()
    if hit:
        _record(model, task, 0, 0, True)
        return _parse_json(hit["response"]) if as_json else hit["response"]

    from google.genai import types

    client = _get_client()
    parts = [prompt]
    if pdf:
        parts.insert(0, types.Part.from_bytes(data=pdf, mime_type="application/pdf"))
    cfg = {"temperature": temperature}
    if as_json:
        cfg["response_mime_type"] = "application/json"
        if schema:
            cfg["response_schema"] = schema

    for attempt in range(max_retries):
        try:
            resp = client.models.generate_content(
                model=model, contents=parts, config=types.GenerateContentConfig(**cfg))
            break
        except Exception as e:
            msg = str(e)
            if ("429" in msg or "RESOURCE_EXHAUSTED" in msg or "503" in msg) and attempt < max_retries - 1:
                wait = 8 * (attempt + 1)
                log.info("rate limited on %s, sleeping %ss", model, wait)
                time.sleep(wait)
                continue
            raise

    text = resp.text or ""
    usage = resp.usage_metadata
    i = getattr(usage, "prompt_token_count", 0) or 0
    o = getattr(usage, "candidates_token_count", 0) or 0
    with db.session() as c:
        c.execute("insert or replace into llm_cache (key, model, response, in_tokens, out_tokens) "
                  "values (?,?,?,?,?)", (key, model, text, i, o))
    _record(model, task, i, o, False)
    return _parse_json(text) if as_json else text


def web_bio(prompt):
    """Background on a person via Gemini + Google Search grounding. Returns (text, sources) or None.
    Grounding isn't on every free tier, so failure here is expected and silent."""
    key = "bio:" + hashlib.sha256(prompt.encode()).hexdigest()
    cached = db.kv_get(key)
    if cached is not None:
        _record(MODEL_FAST, "people_bio", 0, 0, True)
        return tuple(cached) if cached else None
    try:
        from google.genai import types
        resp = _get_client().models.generate_content(
            model=MODEL_FAST, contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0, tools=[types.Tool(google_search=types.GoogleSearch())]))
    except Exception as e:
        log.info("web bio unavailable: %s", e)
        return None
    text = (resp.text or "").strip()
    sources = []
    try:
        for ch in resp.candidates[0].grounding_metadata.grounding_chunks or []:
            if ch.web:
                sources.append({"title": ch.web.title, "url": ch.web.uri})
    except (AttributeError, IndexError, TypeError):
        pass
    u = resp.usage_metadata
    _record(MODEL_FAST, "people_bio", getattr(u, "prompt_token_count", 0) or 0,
            getattr(u, "candidates_token_count", 0) or 0, False)
    result = None if not text or text.startswith("UNKNOWN") else (text, sources[:3])
    db.kv_set(key, list(result) if result else [])
    return result


def usage_summary():
    with db.session() as c:
        rows = c.execute(
            "select model, task, sum(in_tokens) i, sum(out_tokens) o, "
            "sum(case when cached = 0 then 1 else 0 end) calls, sum(cached) hits "
            "from llm_usage group by model, task order by i desc").fetchall()
    out, total = [], 0.0
    for r in rows:
        pin, pout = PRICES.get(r["model"], (0.3, 2.5))
        cost = (r["i"] or 0) / 1e6 * pin + (r["o"] or 0) / 1e6 * pout
        total += cost
        out.append({**dict(r), "usd": round(cost, 4)})
    return {"rows": out, "usd_total": round(total, 4)}


def available():
    return bool(GEMINI_API_KEY)
