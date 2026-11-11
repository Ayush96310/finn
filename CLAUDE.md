# FINN: handoff notes for Claude Code

## The assignment
ENAM Holdings "AI Engineer Build Challenge" (IIT Delhi – AI Engineer – 2027). **Deadline: 15 Nov 2026.**
Build FINN, a mobile-first financial investment agent for a mock portfolio of 15–20 NSE stocks.
- **Push**: a windowed digest of corporate filings, prioritised with routine items collapsed, plus triggered alerts (material filing types, price move beyond ±X%, volume above N× average, thresholds configurable). Must-haves: results filings shown as Revenue/EBITDA/PBT/PAT QoQ and YoY; management changes shown with the incoming person's background.
- **Pull**: on-demand research on ANY NSE ticker, grounded only in primary sources (annual reports, concall transcripts). No news, broker notes or model outside knowledge. The brief values "promised vs delivered over the last 4 quarters" most.
- Graded on: product sense, judgement, architecture, creativity, cost efficiency (cheap models for bulk work, caching). "Thin-but-working beats broad-but-broken. A demo that doesn't run is the worst outcome."
- Submission: deployed mobile-friendly link, GitHub repo, AI build history (chat exports), and a short covering note (draft in WRITEUP.md).

## Decisions already made (don't relitigate without reason)
- Stack: Python 3.10+ / FastAPI backend, vanilla JS PWA in `web/` (no build step), SQLite store.
- LLM: Gemini free tier via `google-genai`. FAST model (`gemini-3.5-flash-lite`) for extraction, SMART model (`gemini-3.5-flash`) only for judging guidance and writing the thesis (the 2.5 models the build started with are closed to new API keys as of Nov 2026). If one model is overloaded after retries, `llm.call` falls back to the other tier. Both can be overridden with `FINN_MODEL_FAST` / `FINN_MODEL_SMART`.
- Depth: the push digest plus promised-vs-delivered. Other research lenses are lighter.
- Ingestion runs locally (NSE blocks cloud IPs); the deployed app (Render, `render.yaml`) serves the committed `data/finn.db`. Research on new tickers can run live on the server.

## Current state
Built and committed, one commit. 21 tests pass (`pytest -q`). The UI has been verified at 390px width against a FICTIONAL sample DB (`scripts/seed_sample.py`, which writes to `data-sample/` and shows a sample-data banner).

**NOT yet run against live data.** The original build environment had no network access to NSE, Yahoo, screener.in or Gemini. Every fetcher and prompt was written from known formats and has never been executed for real. Your first job is to make the live path work.

### Map
- `finn/sources/prices.py`: yfinance EOD (`SYMBOL.NS`); `day_stats`, `move_on` (market reaction to a filing).
- `finn/sources/nse.py`: NSE `/api/corporate-announcements`. Gets cookies via a homepage visit, makes one market-wide call per window, falls back to per-symbol calls. Field names assumed: `symbol, desc, attchmntText, attchmntFile, an_dt, sort_date, seq_id`.
- `finn/sources/screener.py`: parses `/company/SYM/consolidated/`, falling back to standalone. Reads `section#quarters|profit-loss|balance-sheet|cash-flow|ratios table.data-table`, `#top-ratios`, `.annual-reports a`, `.concalls li` (Transcript links). Cached in kv.
- `finn/sources/pdfs.py`: downloads and caches PDFs under `data/pdf/`; pypdf text with `[p.N]` markers; `is_scanned` check.
- `finn/llm.py`: `call()` with a content-hash cache (`llm_cache`), token ledger (`llm_usage`), 429 retry, JSON/schema mode and PDF bytes input. `web_bio()` uses Google Search grounding and fails silently if the tier lacks it.
- `finn/push/classify.py`: regex rules mapping to the 17 categories from the reference PDF plus subtypes (senior vs minor management change, rating up/down/reaffirm, results filing/notice/ad/deck).
- `finn/push/score.py`: deterministic 0–100 score (category base, alarm words, position weight, watched categories, market reaction, LLM materiality vote) mapped to tiers act ≥65, glance ≥35, routine.
- `finn/push/enrich.py`: results card (the LLM copies raw line items; code computes EBITDA = PBT + finance + D&A − other income − exceptional; banks use PPOP; units converted to ₹ crore; revenue cross-checked against screener), people card (from the filing, plus a web bio), batched one-liners (8 per call).
- `finn/push/pipeline.py`: `refresh()` = prices → ingest/classify/score → rescore with reactions → enrich → `last_refresh` → alerts → ntfy push.
- `finn/push/digest.py`: window anchored to `last_refresh` (so a deployed snapshot still makes sense); tiers, routine grouped by category, movers.
- `finn/push/alerts.py`: price/volume thresholds and watched-category filing alerts; ntfy via `FINN_NTFY_TOPIC`.
- `finn/pull/financials.py`: snapshot, trajectory (CAGRs, quarterly YoY), balance sheet (D/E, working-capital days), cash quality (CFO/PAT). Pure arithmetic, no LLM.
- `finn/pull/documents.py`: latest 5 transcripts; annual report MD&A pages only (~28 pages); text chunking.
- `finn/pull/guidance.py`: map (FAST, per transcript: guidance + claims + analyst pushback) → verbatim quote check (`quote_in`, unverifiable items dropped) → reduce (SMART judges each promise against a computed actuals table).
- `finn/pull/thesis.py`: business snapshot, narrative vs numbers, bull/bear (SMART, AR MD&A + latest call only).
- `finn/pull/ask.py`: TF-IDF retrieval over the company corpus, then FAST answer with citations.
- `finn/pull/research.py`: background thread job with step-by-step progress; results cached in kv `research:SYM` and `corpus:SYM`.
- `finn/api.py`: REST routes plus static files. `finn/__main__.py`: `python -m finn refresh|research|serve|usage`.
- `web/app.js`: hash router with Today (triage inbox, cards cleared via "Done", stored in localStorage), Alerts, Research (lens nav, promised-vs-delivered scorecard, charts as inline SVG, ask bar) and a settings sheet (sliders, watched categories, model spend).

## Next tasks, in priority order
1. **Make the live data path work** (Windows laptop, Python env). Set `GEMINI_API_KEY`, then:
   - `python -m finn refresh --days 7`. Debug the NSE fetch (cookies, headers, field names, attachment URL prefix `nsearchives.nseindia.com/corporate/`). Print a few raw items and check the classifier on real `desc`/subject strings. Tune `RULES` in `classify.py` and add the real strings as test cases.
   - `python -m finn research TRENT`. Check the screener parsing on the real HTML (row labels, period headers, documents section). Save one real page as a test fixture.
   - Run the results extraction on a real results PDF and check the numbers by hand against the filing. Check bank format (HDFCBANK) and a lakh-denominated filing.
   - Check the Gemini model names exist on the free tier, and check JSON schema mode with the installed `google-genai` version (nullable fields, enums).
2. Run the full pipeline end to end, look at the Today screen with real data, and tune score weights and tiers so the "Needs you" list is short and right.
3. Pre-build research for the demo set (`TRENT PERSISTENT CDSL KAYNES` plus a few holdings), commit `data/finn.db` (`data/pdf/` stays gitignored), deploy to Render, and test on a phone.
4. Polish only after it all runs: empty and error states with real data, loading speed, the lens order on research.
5. Update README.md and WRITEUP.md with anything that changed. Keep the writeup honest about what's untested or left out.

## Conventions
- Code should read like a careful human wrote it: concise, few comments (only where the *why* isn't obvious), no banner comments, no emoji, natural names. Don't add boilerplate docstrings.
- Keep the LLM out of anything arithmetic or rule-based. Every model call goes through `llm.call` (cache plus ledger).
- Never fabricate data for real tickers. The sample seeder uses fictional companies only and must stay that way.
- Explain the plan in plain words before running large changes. Admit mistakes plainly.
- Run `pytest -q` after changes and add tests for any parser or rule you fix with real data.
