# FINN

A mobile-first investing assistant for a portfolio of NSE stocks. It does two jobs:

- **Push**: *Today* is a triage inbox for every exchange filing across the portfolio in a window you choose. Material items come first and arrive pre-digested: results arrive as a QoQ/YoY table, management changes come with the incoming person's background, and the market's reaction is attached. Routine paperwork is folded away. *Alerts* fire on price and volume moves past thresholds you set, and on material filings in categories you watch. Each alert can also go to your phone through ntfy.
- **Pull**: *Research* works on any NSE symbol. Its centrepiece is **promised vs delivered**: every concrete piece of guidance from the last five earnings calls, checked against what the company actually reported. Around it sit the business snapshot, narrative vs numbers, trajectory, balance sheet, cash quality and bull/bear, plus free-text questions answered from the company's own documents.

## Run it

```bash
pip install -r requirements.txt
export GEMINI_API_KEY=...          # free key from aistudio.google.com
python -m finn refresh --days 7    # prices + filings + enrichment + alerts
python -m finn research TRENT TCS  # optional: pre-build research views
python -m finn serve               # http://localhost:8000
```

Open it on a phone on the same Wi-Fi, or deploy it (below). "Add to Home Screen" installs it as an app.

Optional settings:
- `FINN_NTFY_TOPIC=some-private-name` sends each new alert as a push notification. Install the ntfy app and subscribe to that topic.
- `FINN_MODEL_FAST` / `FINN_MODEL_SMART` override the Gemini models (defaults: `gemini-2.5-flash-lite` / `gemini-2.5-flash`).
- `FINN_ADMIN_TOKEN` enables `POST /api/refresh` with an `X-Finn-Token` header, for cron.

To see the UI without network access, seed the fictional sample book:

```bash
FINN_DATA_DIR=data-sample python scripts/seed_sample.py
FINN_DATA_DIR=data-sample python -m finn serve
```

## Deploy

NSE blocks most datacenter IPs, so ingestion runs where it works (a laptop, or a home server on cron) and the app serves from the SQLite store it produces. To deploy: run `refresh` and `research` locally, commit `data/finn.db`, and push to Render with `render.yaml`. Research on new tickers still runs live on the server, because screener.in and the BSE transcript PDFs are reachable from cloud hosts.

## How it's built

```
finn/
  sources/   prices (yfinance), nse (announcements API), screener (tables + document links), pdfs (download + text, cached)
  push/      classify -> score -> enrich -> digest / alerts
  pull/      financials (pure arithmetic), documents, guidance, thesis, ask
  llm.py     Gemini wrapper: content-hash cache, token ledger, retry on 429
  api.py     FastAPI; serves the web app from web/
web/         vanilla JS + CSS, no build step, PWA
```

Where the model is and isn't used:

| Step | How | Why |
|---|---|---|
| Classifying filings into 17 categories | Regex over NSE's category field and the subject line | Free, instant, testable; NSE's own labels carry most of the signal |
| Prioritising | Deterministic score: category, alarm words, position size, watched categories, market reaction, and an LLM materiality vote last | So an analyst can see why each item ranked where it did |
| One-line summaries | Flash-Lite, 8 filings per call, only for items that survived triage | Routine filings never reach the model |
| Results table | Flash-Lite extracts raw line items from the filing; code computes EBITDA, QoQ/YoY and margins, then cross-checks revenue against screener | Models copy numbers well and do arithmetic badly |
| Management bios | Fact extraction from the filing (SEBI requires a brief profile), plus Gemini search grounding when it's available | Push-side enrichment from the web is allowed by the brief |
| Trajectory / balance sheet / cash | No LLM | It's arithmetic on reported tables |
| Promised vs delivered | Flash-Lite maps each transcript to guidance; every quote is verified verbatim against the transcript and dropped if it can't be found; one Flash call then judges each promise against an actuals table computed for it | Map with the cheap model, reason with the strong one, and leave no room for invented quotes |
| Bull / bear, narrative vs numbers | One Flash call over the annual report's MD&A pages and the latest call | Only the MD&A is read, not the 300-page report |
| Ask | TF-IDF retrieval over that company's chunks, then Flash-Lite | A few hundred chunks per company don't need a vector DB |

Every model call is cached by content hash, so re-running a refresh costs nothing. Spend is shown in the settings sheet.

## Tests

```bash
pytest -q
```
These cover the classifier, the scorer, the screener parser, the financial lenses, the results arithmetic (unit conversion, bank format, negative bases) and quote verification.
