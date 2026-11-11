# FINN: covering note

**Live app:** https://finn-l0d0.onrender.com (best on a phone; "Add to Home Screen" installs it)
**Code:** https://github.com/Ayush96310/finn

**Looking at it in a minute.** The free host sleeps when idle, so the first load can take ~50 seconds.
- *Today*: tap **Week**. Five filings need you, each pre-digested: Titan's results card (with a ₹671 cr non-operating gain flagged and kept out of EBITDA), Asian Paints' incoming chairman with his background from the original appointment filing, Bajaj Finance's ₹5,800 cr promoter warrants. Everything routine is folded away by category.
- *Research*: open **Kaynes** for promised vs delivered: what management promised on each call, graded against what was reported (FY26 operating cash flow of −₹600 cr against "significantly positive", working capital at 133 days against 70–85). Type any NSE symbol to research a new company live; it takes a few minutes the first time.
- *Alerts*: price and volume moves past thresholds you set (the sliders in settings), plus material filings.

**What I built.** FINN treats an investor's day as triage, not a feed. *Today* opens with one sentence ("5 things need you"), then full cards for material filings, one-liners for the next tier, and routine paperwork folded away. Results show Revenue/EBITDA/PBT/PAT QoQ and YoY; a management change shows who the incoming person is; a filing the market reacted to shows the move. On the pull side I went deep on **promised vs delivered**: FINN reads the last five concall transcripts, keeps each dated commitment whose quote it can find verbatim, and grades it against reported numbers, ending in a credibility verdict and the one thing to check on the next call. The other lenses (trajectory, balance sheet, cash quality) are computed from reported tables; the business snapshot and bull/bear come only from the annual report's MD&A and the latest call. No news, broker notes or model memory.

**Key decisions.**
- *The model only where judgement is needed.* Classifying and ranking filings and every ratio are deterministic code; routine filings never reach a model. Gemini Flash-Lite does bulk extraction; a stronger Flash model only judges promises and writes the thesis.
- *Models copy, code computes, code checks the copy.* The results card has the model copy raw line items; Python computes EBITDA, growth and margins, reconciles each quarter against the statement's own arithmetic, and cross-checks revenue against screener.
- *Distrust the model.* Promises whose quote isn't in the transcript are dropped, and so are undated goals ("long term"), which can never be kept or missed; the app says how many. A promise repeated on later calls is shown once, where it was first made, with the repeats listed.
- *Cheap by construction.* Every call is cached by content hash, so a re-run costs nothing; spend is visible in settings. Everything built so far, eight companies' research and a week of filings, cost about $0.37 at paid-tier list prices for the Flash-Lite calls (free on the free tier); 29 calls to the stronger model aren't in that figure because Google lists no price for it.
- *Ingestion apart from serving.* NSE blocks cloud IPs, so filings are ingested on a laptop and the app serves that snapshot; research on new tickers runs live on the server.

**What running it on real data changed.** The first version was written without network access, so the first live week was the real test, and most of what it found looked fine on screen:
- *Titan's EBITDA read +95% YoY.* The copied numbers were right; the formula missed a fair-value gain inside total income. Corrected: +59%, with the gain flagged.
- *SBI's scanned results shifted columns,* even when the model read the PDF image. Each quarter is now reconciled; a failure triggers one re-read, a shift is repaired only when the printed numbers prove it, and anything still inconsistent is flagged, not shown as fact.
- *"Needs you" held seven items,* one of them a vice-chairman's routine retirement that had borrowed the results-day price move. Crediting a reaction only to its likely cause, treating a deal's completion as a follow-up, and letting the model's "paperwork" vote count left five, each a reason to act.
- *Smaller things:* the annual-report reader was reading a CEO letter, intraday prices were being stored as closes, screener listed one transcript twice, a model timeout took down a whole research view, and two Gemini models became unusable mid-build (closed to new keys; free quota exhausted).

**Honest gaps.** Web search isn't on the free Gemini tier, so backgrounds come from exchange filings only (when the filing at hand has no profile, FINN finds the original appointment filing, which SEBI requires to carry one). Trent has no transcripts on screener, so it has no promises to grade. Results cards were checked by hand for Titan, Bharti, SBI and a lakh-denominated small cap, not market-wide. Prices are end-of-day, so price alerts lag by a session.

**Left out deliberately.** BSE announcements (NSE covers the book), web push (ntfy gives real phone notifications), LinkedIn scraping, a vector DB, user accounts.

**Next.** A running credibility score per management team across years; an evening "what changed in your thesis" brief; results-day alerts at release time; a portfolio view of where the book is most exposed to a missed promise.
