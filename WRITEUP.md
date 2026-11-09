# FINN: covering note (draft)

**What I built.** FINN treats an investor's day as triage, not a feed. *Today* opens with one sentence ("3 things need you"), then gives full cards for material filings, one-liners for things worth a glance, and folds the routine paperwork away by category. You clear cards as you deal with them, until you reach inbox zero. Each card arrives pre-digested: results show Revenue/EBITDA/PBT/PAT QoQ and YoY, a management change shows who the new person is, and any filing the market reacted to shows the move and the volume multiple. Alerts fire on thresholds the user sets for price and volume, and on material filings in the categories they watch. They can reach a phone through ntfy.

On the pull side I went deep on one thing: **promised vs delivered**. FINN reads the last five concall transcripts, extracts each concrete commitment management made, verifies every quote verbatim against the transcript, and scores each promise as kept / partly / missed / pending against the reported numbers. The output is a credibility verdict and the one thing to check on the next call. The other lenses (trajectory, balance sheet, cash conversion) are computed straight from the reported tables. Business snapshot, narrative vs numbers and bull/bear are grounded only in the annual report's MD&A and the latest call. It works on any NSE ticker that screener covers.

**Key decisions.**
- *The model goes only where judgement is needed.* Classification, ranking and every financial ratio are deterministic code. Routine filings never reach an LLM. Flash-Lite does bulk extraction, and Flash is used only for the two reasoning steps (judging promises, writing the thesis).
- *Models copy, code computes.* The results card has the model copy raw line items; EBITDA, growth and margins are computed in Python and revenue is cross-checked against screener.
- *Distrust the model's quotes.* Guidance items whose quote can't be found in the source are dropped, and the UI says how many were dropped.
- *Cache everything.* Every call is keyed by content hash, so a second refresh costs ₹0. Spend is visible in the app.
- *Ingestion is separate from serving.* NSE blocks cloud IPs, so ingestion runs locally and the deployed app serves the snapshot. Research on new tickers still runs live on the server.

**Left out deliberately.** BSE announcements (NSE covers the portfolio), real web push (ntfy gives real phone notifications in ten lines), LinkedIn scraping (the filing's mandated profile plus grounded search covers it), a vector DB, and user accounts.

**Next.** Guidance tracking across years, with a running credibility score per management team; an evening "what changed in your thesis" brief that diffs new filings against the last research view; results-day alerts at release time rather than end of day; and a portfolio-level view of where the book is most exposed to a missed promise.
