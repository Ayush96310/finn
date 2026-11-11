# FINN

A mobile-first investing assistant for a portfolio of NSE stocks. It does two jobs:

- **Push**: *Today* is a triage inbox for every exchange filing across the portfolio in a window you choose. Material items come first and arrive pre-digested: results arrive as a QoQ/YoY table, management changes come with the incoming person's background, and the market's reaction is attached. Routine paperwork is folded away. *Alerts* fire on price and volume moves past thresholds you set, and on material filings in categories you watch. Each alert can also go to your phone through ntfy.
- **Pull**: *Research* works on any NSE symbol. Its centrepiece is **promised vs delivered**: every concrete piece of guidance from the last five earnings calls, checked against what the company actually reported. Around it sit the business snapshot, narrative vs numbers, trajectory, balance sheet, cash quality and bull/bear, plus free-text questions answered from the company's own documents.

## Run it

```bash
pip install -r requirements.txt
echo GEMINI_API_KEY=... > .env     # free key from aistudio.google.com; .env is gitignored
python -m finn refresh --days 7    # prices + filings + enrichment + alerts
python -m finn research TRENT TCS  # optional: pre-build research views
python -m finn serve               # http://localhost:8000
```

Open it on a phone on the same Wi-Fi, or deploy it (below). "Add to Home Screen" installs it as an app.

Optional settings:
- `FINN_NTFY_TOPIC=some-private-name` sends each new alert as a push notification. Install the ntfy app and subscribe to that topic.
- `FINN_MODEL_FAST` / `FINN_MODEL_SMART` override the Gemini models (defaults: `gemini-3.5-flash-lite` / `gemini-3.8-flash`).
- `FINN_ADMIN_TOKEN` enables `POST /api/refresh` with an `X-Finn-Token` header, for cron.

To see the UI without network access, seed the fictional sample book:

```bash
FINN_DATA_DIR=data-sample python scripts/seed_sample.py
FINN_DATA_DIR=data-sample python -m finn serve
```

## Deploy

NSE blocks most datacenter IPs, so ingestion runs where it works (a laptop, or a home server on cron) and the app serves from the SQLite store it produces. To deploy: run `refresh` and `research` locally, commit `data/finn.db`, push to GitHub, and create a Render Blueprint from `render.yaml`, setting `GEMINI_API_KEY` in Render's dashboard. Research on new tickers runs live on the server (screener.in and the exchange PDFs answer cloud hosts), but Render's free disk is wiped on restart, so only the committed research survives. Dependencies are pinned to the versions the tests ran against.

## How it's built

```
finn/
  sources/   prices (yfinance), nse (announcements API), screener (tables + document links), pdfs (download + text, cached)
  push/      classify -> score -> enrich -> digest / alerts
  pull/      financials (pure arithmetic), documents, guidance, thesis, ask
  llm.py     Gemini wrapper: content-hash cache, token ledger, retries, falls back to the other model when one is busy
  api.py     FastAPI; serves the web app from web/
web/         vanilla JS + CSS, no build step, PWA
```

Where the model is and isn't used:

| Step | How | Why |
|---|---|---|
| Classifying filings into 17 categories | Regex over NSE's category field and the subject line | Free, instant, testable; NSE's own labels carry most of the signal |
| Prioritising | Deterministic score: category, alarm words, position size, watched categories, market reaction, and an LLM materiality vote last | So an analyst can see why each item ranked where it did |
| One-line summaries | Flash-Lite, 8 filings per call, only for items that survived triage | Routine filings never reach the model |
| Results table | Flash-Lite copies raw line items; code computes EBITDA, QoQ/YoY and margins, checks each quarter against the statement's own arithmetic (PBT = total income − total expenses + exceptional; for banks, PPOP − provisions + exceptional), re-reads the PDF once if it fails, and flags any quarter that still doesn't add up. Revenue is cross-checked against screener when the basis matches | Models copy numbers well and do arithmetic badly, and scanned filings with blank cells shift columns silently |
| Management bios | Fact extraction from the filing (SEBI requires a brief profile), plus Gemini search grounding when the API tier allows it (the free tier returns 429, so on it the filing's profile is the only source) | Push-side enrichment from the web is allowed by the brief |
| Trajectory / balance sheet / cash | No LLM | It's arithmetic on reported tables |
| Promised vs delivered | Flash-Lite maps each transcript to guidance; every quote is verified verbatim against the transcript and dropped if it can't be found; one Flash call then judges each promise against an actuals table computed for it | Map with the cheap model, reason with the strong one, and leave no room for invented quotes |
| Bull / bear, narrative vs numbers | One Flash call over the annual report's MD&A pages and the latest call. The MD&A is found by its running header (or a top-of-page heading) anywhere in the report | Only ~28 MD&A pages are read, not the 300-500 page report |
| Ask | TF-IDF retrieval over that company's chunks, then Flash-Lite | A few hundred chunks per company don't need a vector DB |

Every model call is cached by content hash, so re-running a refresh costs nothing. Spend is shown in the settings sheet.

## Tests

```bash
pytest -q
```
These cover the classifier (with real NSE subjects from a week of filings), the scorer, the screener parser (two saved real pages), the financial lenses, the results arithmetic and reconciliation (Titan, SBI and United Tea figures as printed), MD&A location, price and alert windows, the model fallback, and quote verification.
