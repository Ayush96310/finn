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
        from google.genai import types
        _client = genai.Client(api_key=GEMINI_API_KEY, http_options=types.HttpOptions(timeout=120_000))
    return _client


def _record(model, task, i, o, cached):
    with db.session() as c:
        c.execute("insert into llm_usage (model, task, in_tokens, out_tokens, cached) values (?,?,?,?,?)",
                  (model, task, i, o, int(cached)))


def _parse_json(text):
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1).strip()
    # A complete object followed by stray text is still a usable answer.
    return json.JSONDecoder().raw_decode(text)[0]


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
        try:
            out = _parse_json(hit["response"]) if as_json else hit["response"]
            _record(model, task, 0, 0, True)
            return out
        except ValueError:
            pass  # a malformed reply cached by an older version; ask again

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

    config = types.GenerateContentConfig(**cfg)
    for attempt in range(2):
        try:
            resp = _generate(client, model, parts, config, max_retries)
        except _Busy:
            # A demo shouldn't die because one model is overloaded; the other tier usually isn't.
            other = MODEL_FAST if smart else MODEL_SMART
            log.warning("%s still busy after retries, falling back to %s", model, other)
            model = other
            resp = _generate(client, model, parts, config, 2)

        text = resp.text or ""
        usage = resp.usage_metadata
        _record(model, task, getattr(usage, "prompt_token_count", 0) or 0,
                getattr(usage, "candidates_token_count", 0) or 0, False)
        try:
            out = _parse_json(text) if as_json else text
        except ValueError:
            # Long JSON replies occasionally come back malformed; one more try usually fixes it.
            log.warning("%s returned malformed JSON for %s (attempt %d)", model, task, attempt + 1)
            if attempt:
                raise
            continue
        with db.session() as c:
            c.execute("insert or replace into llm_cache (key, model, response, in_tokens, out_tokens) "
                      "values (?,?,?,?,?)", (key, model, text, getattr(usage, "prompt_token_count", 0) or 0,
                                             getattr(usage, "candidates_token_count", 0) or 0))
        return out


class _Busy(RuntimeError):
    pass


def _generate(client, model, parts, config, retries):
    for attempt in range(retries):
        try:
            return client.models.generate_content(model=model, contents=parts, config=config)
        except Exception as e:
            msg = str(e)
            if not any(s in msg for s in ("429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE", "504",
                                          "DEADLINE_EXCEEDED")):
                raise
            if attempt == retries - 1:
                raise _Busy(msg) from e
            wait = 8 * (attempt + 1)
            log.info("%s busy, sleeping %ss", model, wait)
            time.sleep(wait)


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
    out, total, unpriced = [], 0.0, 0
    for r in rows:
        price = PRICES.get(r["model"])
        cost = None
        if price:
            cost = round((r["i"] or 0) / 1e6 * price[0] + (r["o"] or 0) / 1e6 * price[1], 4)
            total += cost
        elif r["calls"]:
            unpriced += r["calls"]
        out.append({**dict(r), "usd": cost})
    return {"rows": out, "usd_total": round(total, 4), "unpriced_calls": unpriced}


def available():
    return bool(GEMINI_API_KEY)
