const $ = (s, el = document) => el.querySelector(s);
const view = $("#view");

const CAT = {
  results: "Results", "M&A": "M&A", fund_raise: "Fund raise", management_change: "Management",
  litigation: "Litigation", insider_trading: "Insider trade", earnings_call: "Earnings call",
  investor_meetings: "Investor meets", credit_rating: "Credit rating", dividend: "Dividend",
  bonus_split: "Bonus / split", capex: "Capex", press_release: "Press release",
  postal_ballot: "Postal ballot", agm_egm: "AGM / EGM", pledging: "Pledging", unclassified: "Routine paperwork",
};
const VERDICT = { delivered: "Kept", partly: "Partly", missed: "Missed", pending: "Pending", unclear: "Unclear" };

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const sign = (v, d = 1) => (v == null ? "–" : `${v > 0 ? "+" : ""}${v.toFixed(d)}%`);
const tone = (v) => (v == null ? "muted" : v >= 0 ? "up" : "down");

function cr(v) {
  if (v == null) return "–";
  const a = Math.abs(v);
  if (a >= 100000) return `${(v / 100000).toFixed(2)}L`;
  if (a >= 1000) return Math.round(v).toLocaleString("en-IN");
  return v.toFixed(a < 10 ? 1 : 0);
}

function ago(iso) {
  const d = new Date(iso.replace(" ", "T"));
  const ref = meta.as_of ? new Date(meta.as_of) : new Date();
  const mins = (ref - d) / 60000;
  if (mins < 60 * 20) {
    const h = Math.floor(mins / 60);
    return h < 1 ? `${Math.max(1, Math.round(mins))}m` : `${h}h`;
  }
  return d.toLocaleDateString("en-IN", { day: "numeric", month: "short" }) + " " +
    d.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false });
}

async function api(path, opts = {}) {
  const r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
  return r.json();
}

// light per-device state: which cards you've cleared, last-seen alerts
const store = {
  get(k, d) { try { return JSON.parse(localStorage.getItem("finn:" + k)) ?? d; } catch { return d; } },
  set(k, v) { try { localStorage.setItem("finn:" + k, JSON.stringify(v)); } catch {} },
};

function spark(vals, w = 88, h = 26, color) {
  const v = vals.filter((x) => x != null);
  if (v.length < 2) return "";
  const lo = Math.min(...v), hi = Math.max(...v), span = hi - lo || 1;
  const pts = v.map((x, i) => `${(i / (v.length - 1)) * w},${h - ((x - lo) / span) * (h - 2) - 1}`).join(" ");
  const c = color || (v[v.length - 1] >= v[0] ? "var(--up)" : "var(--down)");
  return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}"><polyline points="${pts}" fill="none" stroke="${c}" stroke-width="1.4" stroke-linejoin="round"/></svg>`;
}

function bars(pairs, { w = 300, h = 70, fmt = cr, color = "var(--ink-2)", last = "var(--amber)" } = {}) {
  const v = pairs.map((p) => p[1]);
  const real = v.filter((x) => x != null);
  if (!real.length) return "";
  const hi = Math.max(...real, 0), lo = Math.min(...real, 0), span = hi - lo || 1;
  const bw = w / v.length;
  const zero = h - 14 - ((0 - lo) / span) * (h - 26);
  let out = `<svg width="100%" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" style="display:block">`;
  v.forEach((x, i) => {
    if (x == null) return;
    const y = h - 14 - ((x - lo) / span) * (h - 26);
    const top = Math.min(y, zero), bh = Math.max(1, Math.abs(zero - y));
    out += `<rect x="${i * bw + bw * 0.18}" y="${top}" width="${bw * 0.64}" height="${bh}" rx="1.5" fill="${i === v.length - 1 ? last : color}" opacity="${i === v.length - 1 ? 1 : 0.55}"/>`;
    out += `<text x="${i * bw + bw / 2}" y="${h - 2}" fill="var(--ink-3)" font-size="8.5" font-family="JetBrains Mono" text-anchor="middle">${esc(shortPeriod(pairs[i][0]))}</text>`;
  });
  return out + "</svg>";
}

function shortPeriod(p) {
  const m = /([A-Za-z]{3})\s+(\d{4})/.exec(p || "");
  return m ? `${m[1]}${m[2].slice(2)}` : p;
}

/* ---------- Today ---------- */

let meta = {};

async function renderToday() {
  const hours = store.get("hours", meta.settings?.window_hours || 72);
  view.innerHTML = `<div class="hero"><h1 class="muted">Reading the tape…</h1></div>`;
  const d = await api(`/api/digest?hours=${hours}`);
  const cleared = new Set(store.get("cleared", []));
  const act = d.act.filter((f) => !cleared.has(f.id));
  const total = d.counts.act + d.counts.glance + d.counts.routine;
  const hotTh = meta.settings || { price_pct: 4, vol_mult: 2 };

  const headline = act.length === 0
    ? `Nothing needs you${d.counts.act ? " any more" : ""}.`
    : `<em>${act.length}</em> thing${act.length > 1 ? "s" : ""} need${act.length > 1 ? "" : "s"} you.`;

  view.innerHTML = `
    <div class="hero">
      <h1>${headline}</h1>
      <p>${total} filings across your book in the last ${hours < 48 ? hours + "h" : hours / 24 + " days"}. ${d.counts.routine} routine, folded away.</p>
    </div>
    <div class="chips" id="windows">
      ${[[24, "24h"], [72, "3 days"], [168, "Week"], [720, "30 days"]].map(([h, l]) =>
        `<button class="chip ${h === hours ? "on" : ""}" data-h="${h}">${l}</button>`).join("")}
    </div>

    ${d.movers.length ? `
    <div class="section-h"><h2>Your book, last close</h2><span>${d.movers[0].date}</span></div>
    <div class="movers">${d.movers.map((m) => {
      const hot = Math.abs(m.change_pct) >= hotTh.price_pct || m.vol_ratio >= hotTh.vol_mult;
      return `<a class="mover ${hot ? "hot" : ""}" href="#/r/${m.symbol}">
        <b>${m.symbol}</b><span class="chg ${tone(m.change_pct)}">${sign(m.change_pct)}</span>
        <small>${m.vol_ratio.toFixed(1)}× vol</small>${spark(m.spark)}</a>`;
    }).join("")}</div>` : ""}

    <div class="section-h"><h2>Needs you</h2><span>${act.length}</span></div>
    ${act.length ? act.map(card).join("") :
      `<div class="empty"><b>Inbox zero.</b>${d.counts.act ? "You've cleared everything material." : "No material filings in this window."}</div>`}

    ${d.glance.length ? `
    <div class="section-h"><h2>Worth a glance</h2><span>${d.glance.length}</span></div>
    <div>${d.glance.map(glanceRow).join("")}</div>` : ""}

    ${d.routine.length ? `
    <div class="section-h"><h2>Routine</h2><span>${d.counts.routine}</span></div>
    ${d.routine.map((g) => `
      <details class="fold"><summary><span>${CAT[g.category] || g.category}</span><span>${g.count}</span></summary>
      ${g.items.map(glanceRow).join("")}</details>`).join("")}` : ""}
    <div style="height:24px"></div>`;

  $("#windows").onclick = (e) => {
    const h = e.target.dataset.h;
    if (h) { store.set("hours", +h); renderToday(); }
  };
  view.querySelectorAll("[data-clear]").forEach((b) => b.onclick = () => {
    const id = b.dataset.clear;
    const set = new Set(store.get("cleared", [])); set.add(id); store.set("cleared", [...set]);
    const el = b.closest(".card"); el.classList.add("gone");
    setTimeout(renderToday, 260);
  });
}

function reactionChip(r) {
  if (!r) return "";
  const notable = Math.abs(r.change_pct) >= 2 || r.vol_ratio >= 1.8;
  if (!notable) return "";
  return `<span class="react"><span class="${tone(r.change_pct)}">${sign(r.change_pct)}</span><span class="muted">·</span><span>${r.vol_ratio.toFixed(1)}× vol</span><span class="muted">market reaction</span></span>`;
}

function card(f) {
  const c = f.card;
  let body = "";
  if (c?.kind === "results") body = resultsTable(c);
  else if (c?.kind === "people") body = c.people.map(personBlock).join("");
  const title = f.summary || f.subject || f.nse_category;
  return `<article class="card">
    <div class="card-h"><span class="dot"></span><a class="sym" href="#/r/${f.symbol}">${f.symbol}</a>
      <span class="cat">${CAT[f.category] || f.category}</span><span class="when">${ago(f.filed_at)}</span></div>
    <h3>${esc(title)}</h3>
    ${f.summary && f.subject ? `<p class="subj">${esc(f.subject.slice(0, 160))}</p>` : ""}
    ${body}
    ${reactionChip(f.reaction)}
    <div class="card-f">
      ${f.attachment ? `<a href="${esc(f.attachment)}" target="_blank" rel="noopener">Filing ↗</a>` : ""}
      <a href="#/r/${f.symbol}">Research</a>
      <button class="done" data-clear="${f.id}">Done ✓</button>
    </div></article>`;
}

function resultsTable(c) {
  const p = c.periods || {};
  return `<table class="rtable">
    <tr><th>₹ cr · ${esc(c.basis || "")}</th><th>${esc(p.current || "Qtr")}</th><th>QoQ</th><th>YoY</th></tr>
    ${c.metrics.map((m) => `<tr><td>${m.label}</td><td>${cr(m.current)}</td>
      <td class="${tone(m.qoq)}">${sign(m.qoq, 0)}</td><td class="${tone(m.yoy)}">${sign(m.yoy, 0)}</td></tr>`).join("")}
  </table>
  ${c.margin != null ? `<div class="verify">${c.metrics[1].label} margin ${c.margin}%</div>` : ""}
  ${(c.flags || []).map((x) => `<div class="flag">⚑ ${esc(x)}</div>`).join("")}
  ${c.check ? `<div class="verify">${c.check.match ? "✓ revenue matches screener" : "≠ screener shows ₹" + cr(c.check.value) + " cr: check basis"}</div>` : ""}`;
}

function personBlock(p) {
  const verb = { appointed: "joins as", resigned: "steps down as", retired: "retires as", redesignated: "now" }[p.change] || "";
  const src = (p.bio_sources || []).map((s) => `<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title || "source")}</a>`).join(" · ");
  return `<div class="person"><b>${esc(p.name)}</b> <span class="role">${verb} ${esc(p.role || "")}${p.effective ? " · " + esc(p.effective) : ""}</span>
    ${p.bio ? `<p>${esc(p.bio)}</p>` : p.profile ? `<p>${esc(p.profile)}</p>` : ""}
    ${p.reason && p.change !== "appointed" ? `<p>Reason given: ${esc(p.reason)}</p>` : ""}
    <div class="src">${p.bio ? "Background: " + (src || "web") : p.profile ? "Profile from the filing" : ""}</div></div>`;
}

function glanceRow(f) {
  return `<a class="row" href="${esc(f.attachment || "#/r/" + f.symbol)}" target="${f.attachment ? "_blank" : ""}" rel="noopener">
    <span class="sym">${f.symbol}</span>
    <span class="txt"><div>${esc(f.summary || f.subject || f.nse_category)}</div>
    <small>${CAT[f.category] || f.category} · ${ago(f.filed_at)}${f.reaction && Math.abs(f.reaction.change_pct) >= 2 ? ` · <span class="${tone(f.reaction.change_pct)}">${sign(f.reaction.change_pct)}</span>` : ""}</small></span></a>`;
}

/* ---------- Alerts ---------- */

async function renderAlerts() {
  const list = await api("/api/alerts?days=14");
  store.set("alerts_seen", list.length ? list[0].id : null);
  $("#alert-dot").textContent = "";
  const s = meta.settings;
  view.innerHTML = `
    <div class="hero"><h1>Alerts</h1>
      <p>Price moves beyond <b class="num">±${s.price_pct}%</b>, volume above <b class="num">${s.vol_mult}×</b> its 20-day average, and material filings in the categories you watch.
      <a href="#" id="tune" style="color:var(--amber)">Tune</a></p></div>
    ${list.length ? list.map((a) => `
      <a class="alert" href="#/r/${a.symbol}"><span class="k ${a.kind}">${a.kind}</span>
      <span class="m">${esc(a.message)}<small>${a.date}</small></span></a>`).join("")
      : `<div class="empty"><b>Quiet.</b>Nothing crossed your thresholds in the last two weeks.</div>`}`;
  $("#tune").onclick = (e) => { e.preventDefault(); openSettings(); };
}

/* ---------- Research ---------- */

let pollTimer;

async function renderResearchHome() {
  const p = await api("/api/portfolio");
  view.innerHTML = `
    <div class="hero"><h1>Dig into a company.</h1>
      <p>Built only from its annual report, concall transcripts and reported financials. No news, no broker notes.</p></div>
    <form class="search" id="sform"><input id="sym" placeholder="Any NSE symbol" autocomplete="off" autocapitalize="characters"><button>Go</button></form>
    <div class="section-h"><h2>Off-book ideas</h2></div>
    <div class="quick" style="padding-top:0">${p.research_demo.map((s) => `<a class="chip" href="#/r/${s}">${s}</a>`).join("")}</div>
    <div class="section-h"><h2>Your book</h2></div>
    <div class="quick" style="padding-top:0">${p.holdings.map((h) => `<a class="chip" href="#/r/${h.symbol}">${h.symbol}</a>`).join("")}</div>`;
  $("#sform").onsubmit = (e) => {
    e.preventDefault();
    const s = $("#sym").value.trim().toUpperCase().replace(/\.NS$/, "");
    if (s) location.hash = `#/r/${s}`;
  };
}

const retried = new Set();

async function renderResearch(sym) {
  clearTimeout(pollTimer);
  let { status, data } = await api(`/api/research/${sym}`);
  // Re-run once a view whose judging step didn't finish last time; finished steps come back from the cache.
  const retry = data?.guidance?.unfinished && !retried.has(sym);
  if ((!data || retry) && status.state !== "running") {
    if (retry) retried.add(sym);
    try { status = await api(`/api/research/${sym}`, { method: "POST" }); }
    catch (e) { view.innerHTML = `<div class="empty"><b>Can't research ${esc(sym)}.</b>${esc(e.message)}</div>`; return; }
  }
  if (status.state === "error" && !data) {
    view.innerHTML = `<div class="empty"><b>${esc(sym)}</b>Couldn't load it: ${esc(status.error)}</div>`;
    return;
  }
  if (data) drawResearch(sym, data, status);
  else view.innerHTML = progress(sym, status);
  if (status.state === "running") {
    pollTimer = setTimeout(() => { if (location.hash === `#/r/${sym}`) renderResearch(sym); }, 2500);
  }
}

function progress(sym, status) {
  return `<div class="r-head"><h1>${esc(sym)}</h1></div>
    <div class="progress"><div>${esc(status.step || "Starting…")}</div><div class="bar"><i></i></div>
    <small class="muted">First run reads the transcripts and annual report; after that it's cached.</small></div>`;
}

function drawResearch(sym, d, status) {
  const s = d.snapshot, t = d.trajectory, b = d.balance_sheet, c = d.cash, g = d.guidance, th = d.thesis;
  const running = status.state === "running";
  // Finished with no calls to read: keep the lens and say why, rather than let the headline feature vanish.
  const noCalls = !g && !running && d.llm && d.sources && !d.sources.calls.length;
  const lenses = [
    ["pvd", "Promised vs delivered", g || running || noCalls],
    ["biz", "Business", th || d.about],
    ["traj", "Trajectory", true],
    ["bs", "Balance sheet", true],
    ["cash", "Cash", true],
    ["case", "Bull / bear", th],
  ].filter((l) => l[2]);

  view.innerHTML = `
    <div class="r-head"><h1>${esc(d.name || sym)}</h1>
      <div class="meta"><span><b>₹${cr(s.price)}</b></span><span>Mcap <b>₹${cr(s.market_cap)} cr</b></span>
      <span>P/E <b>${s.pe ?? "–"}</b></span><span>ROCE <b>${s.roce ?? "–"}%</b></span><span>ROE <b>${s.roe ?? "–"}%</b></span></div></div>
    <nav class="lenses">${lenses.map(([id, l], i) => `<a href="#${id}" data-lens="${id}" class="${i === 0 ? "on" : ""}">${l}</a>`).join("")}</nav>
    ${running ? `<div class="progress" style="margin-top:12px"><div>${esc(status.step || "Working…")}</div><div class="bar"><i></i></div></div>` : ""}

    ${g ? pvdLens(g) : !d.llm ? `<section class="lens" id="pvd"><p>Narrative lenses need a Gemini key on this deployment; the numbers below are computed directly.</p></section>`
      : noCalls ? `<section class="lens" id="pvd"><div class="section-h"><h2>Promised vs delivered</h2></div><p>No earnings-call transcripts are published for ${esc(sym)} on screener.in, so there are no management promises to check. The business, numbers and bull/bear lenses below still come from the annual report and reported financials.</p></section>` : ""}
    ${bizLens(d, th)}
    ${trajLens(t, s)}
    ${bsLens(b)}
    ${cashLens(c)}
    ${th ? caseLens(th) : ""}
    <div id="answers"></div>
    <p class="muted" style="margin:18px var(--pad) 90px;font-size:12px">
      Sources: ${d.sources?.annual_report ? `<a href="${esc(d.sources.annual_report.url)}" target="_blank" rel="noopener">${esc(d.sources.annual_report.title)}</a>; ` : ""}
      ${(d.sources?.calls || []).map((x) => `<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.period)} call</a>`).join(", ")}
      ${d.sources ? "; " : ""}financial tables via screener.in (${esc(s.basis)}). Generated ${esc(d.generated_at)}.</p>
    ${d.llm && d.sources ? `<form class="askbar" id="ask"><input placeholder="Ask the filings… e.g. what drove margin change?" maxlength="300"><button>Ask</button></form>` : ""}`;

  view.querySelectorAll(".lenses a").forEach((a) => a.onclick = (e) => {
    e.preventDefault();
    document.getElementById(a.dataset.lens)?.scrollIntoView({ behavior: "smooth" });
  });
  const obs = new IntersectionObserver((ents) => ents.forEach((en) => {
    if (en.isIntersecting) view.querySelectorAll(".lenses a").forEach((a) => a.classList.toggle("on", a.dataset.lens === en.target.id));
  }), { rootMargin: "-120px 0px -65% 0px" });
  view.querySelectorAll(".lens").forEach((l) => obs.observe(l));

  const form = $("#ask");
  if (form) form.onsubmit = async (e) => {
    e.preventDefault();
    const input = form.querySelector("input"), q = input.value.trim();
    if (!q) return;
    input.value = "";
    const box = $("#answers");
    const el = document.createElement("div");
    el.className = "answer"; el.innerHTML = `<div class="q">${esc(q)}</div><span class="muted">Reading…</span>`;
    box.prepend(el); el.scrollIntoView({ behavior: "smooth", block: "center" });
    try {
      const r = await api(`/api/research/${sym}/ask`, { method: "POST", body: JSON.stringify({ q }) });
      el.innerHTML = `<div class="q">${esc(q)}</div>${esc(r.answer)}<div class="s">${r.sources.map((x) => `[${x.n}] ${esc(x.source)}${x.page ? " p." + x.page : ""}`).join(" · ")}</div>`;
    } catch (err) { el.innerHTML = `<div class="q">${esc(q)}</div><span class="down">${esc(err.message)}</span>`; }
  };
}

function pvdLens(g) {
  if (!g.items.length) return `<section class="lens" id="pvd"><div class="section-h"><h2>Promised vs delivered</h2></div><p>${esc(g.note || "No concrete guidance found.")}</p></section>`;
  const order = ["delivered", "partly", "missed", "pending", "unclear"];
  const tally = g.tally || {};
  const total = g.items.length;
  const dropped = g.calls.reduce((a, c) => a + (c.dropped_unverified || 0), 0);
  const byCall = {};
  g.items.forEach((it) => (byCall[it.made_in] ||= []).push(it));
  return `<section class="lens" id="pvd">
    <div class="section-h"><h2>Promised vs delivered</h2><span>${g.calls.length} calls</span></div>
    <div class="score"><div class="seg">${order.filter((k) => tally[k]).map((k) =>
      `<i class="v-${k}" style="flex:${tally[k]}"></i>`).join("")}</div>
      <div class="legend">${order.filter((k) => tally[k]).map((k) => `<span><i class="v-${k}"></i>${VERDICT[k]} ${tally[k]}</span>`).join("")}<span class="muted">of ${total}</span></div></div>
    ${g.credibility ? `<div class="cred"><p>${esc(g.credibility)}</p>${g.watch ? `<small><b>Next call, check:</b> ${esc(g.watch)}</small>` : ""}</div>` : ""}
    ${Object.entries(byCall).map(([call, items]) => `
      <div class="section-h" style="padding-top:10px"><h2>Said on the ${esc(call)} call</h2></div>
      ${items.map((it) => `<details class="promise"><summary>
        <span class="pill v-${it.verdict}">${VERDICT[it.verdict] || it.verdict}</span>
        <span class="what">${esc(it.promise)}<small>${esc([it.target, it.horizon].filter(Boolean).join(" · "))}</small></span></summary>
        <div class="body">${it.evidence ? `<p style="margin:0 0 8px">${esc(it.evidence)}</p>` : ""}
          <blockquote>“${esc(it.quote)}”${it.speaker ? ` <span class="cite">: ${esc(it.speaker)}</span>` : ""}</blockquote>
          <a href="${esc(it.source_url)}" target="_blank" rel="noopener">transcript ↗</a></div></details>`).join("")}`).join("")}
    ${dropped ? `<p class="cite" style="margin:10px var(--pad) 0">${dropped} extracted promise${dropped > 1 ? "s" : ""} dropped because the quote couldn't be found verbatim in the transcript.</p>` : ""}
  </section>`;
}

function bizLens(d, th) {
  const biz = th?.business;
  if (!biz && !d.about) return "";
  return `<section class="lens" id="biz"><div class="section-h"><h2>Business</h2></div>
    <p>${esc(biz?.one_liner || d.about)}</p>
    ${biz?.segments?.length ? `<div class="seglist">${biz.segments.map((s) => `<div><span>${esc(s.name)}<br><small>${esc(s.note || "")}</small></span><span class="num">${esc(s.share || "")}</span></div>`).join("")}</div>` : ""}
    ${biz?.moat ? `<p><span class="muted">Edge:</span> ${esc(biz.moat)}</p>` : ""}
    ${th?.narrative_vs_numbers?.length ? `<div class="section-h"><h2>Narrative vs numbers</h2></div>
      ${th.narrative_vs_numbers.map((n) => `<div class="nvn"><span class="tag ${n.agrees ? "up" : "down"}">${n.agrees ? "Agrees" : "Diverges"}</span>
        <div>${esc(n.claim)}</div><p>${esc(n.numbers_say)} <span class="cite">${esc(n.cite || "")}</span></p></div>`).join("")}` : ""}
  </section>`;
}

function trajLens(t, s) {
  const q = t.quarterly;
  const lastQ = q.sales[q.sales.length - 1];
  return `<section class="lens" id="traj"><div class="section-h"><h2>Trajectory</h2></div>
    <div class="kv">
      <div><small>Revenue CAGR 3y / 5y</small><b>${t.sales_cagr_3y ?? "–"}% <span class="muted">/ ${t.sales_cagr_5y ?? "–"}%</span></b></div>
      <div><small>Profit CAGR 3y / 5y</small><b>${t.np_cagr_3y ?? "–"}% <span class="muted">/ ${t.np_cagr_5y ?? "–"}%</span></b></div>
      <div><small>Latest qtr revenue YoY</small><b class="${tone(lastQ?.[2])}">${sign(lastQ?.[2])}</b></div>
      <div><small>Margin vs 3y avg</small><b class="${tone(t.margin_vs_3y_avg_pp)}">${t.margin_vs_3y_avg_pp == null ? "–" : (t.margin_vs_3y_avg_pp > 0 ? "+" : "") + t.margin_vs_3y_avg_pp + "pp"}</b></div>
    </div>
    <div class="chart"><h4>Annual revenue <span>₹ cr</span></h4>${bars(t.annual.sales)}</div>
    <div class="chart"><h4>Operating margin <span>%</span></h4>${bars(t.annual.opm, { fmt: (x) => x })}</div>
    <div class="chart"><h4>Quarterly revenue, YoY <span>%</span></h4>${bars(q.sales.map((x) => [x[0], x[2]]), { color: "var(--blue)" })}</div>
    <div class="chart"><h4>Quarterly net profit <span>₹ cr</span></h4>${bars(q.np.map((x) => [x[0], x[1]]))}</div>
  </section>`;
}

function bsLens(b) {
  const de = b.debt_to_equity[b.debt_to_equity.length - 1];
  const wc = b.working_capital;
  const last = (p) => (p && p.length ? p[p.length - 1][1] : null);
  const first = (p) => (p && p.length ? p[0][1] : null);
  return `<section class="lens" id="bs"><div class="section-h"><h2>Balance sheet</h2></div>
    <div class="kv">
      <div><small>Debt / equity</small><b>${de ? de[1].toFixed(2) : "–"}</b></div>
      <div><small>Borrowings</small><b>₹${cr(last(b.borrowings))} cr</b></div>
      <div><small>Cash conversion cycle</small><b>${last(wc.ccc) ?? "–"} <span class="muted">d</span></b></div>
      <div><small>Working capital days</small><b>${last(wc.wc_days) ?? "–"} <span class="muted">was ${first(wc.wc_days) ?? "–"}</span></b></div>
    </div>
    ${b.deposits?.length ? `<div class="chart"><h4>Deposits <span>₹ cr</span></h4>${bars(b.deposits)}</div>` : ""}
    <div class="chart"><h4>Borrowings <span>₹ cr</span></h4>${bars(b.borrowings, { last: "var(--down)" })}</div>
    ${wc.debtor_days?.length ? `<div class="chart"><h4>Receivable days <span>d</span></h4>${bars(wc.debtor_days)}</div>` : ""}
  </section>`;
}

function cashLens(c) {
  if (!c.years.length) return "";
  return `<section class="lens" id="cash"><div class="section-h"><h2>Cash quality</h2><span>CFO ÷ PAT</span></div>
    <div class="kv"><div><small>5-year cash conversion</small><b class="${c.conversion_5y >= 0.8 ? "up" : "down"}">${c.conversion_5y ?? "–"}×</b></div>
    <div><small>Read</small><b style="font:500 13px var(--sans)">${c.conversion_5y == null ? "n/a" : c.conversion_5y >= 1 ? "Profits are cash-backed" : c.conversion_5y >= 0.7 ? "Mostly cash-backed" : "Profits outrun cash"}</b></div></div>
    <table class="rtable" style="margin:0 var(--pad);width:calc(100% - 36px)">
      <tr><th>₹ cr</th><th>CFO</th><th>PAT</th><th>CFO/PAT</th><th>After invest.</th></tr>
      ${c.years.map((y) => `<tr><td>${esc(shortPeriod(y.period))}</td><td>${cr(y.cfo)}</td><td>${cr(y.pat)}</td>
        <td class="${y.conversion >= 0.8 ? "" : "down"}">${y.conversion ?? "–"}</td><td class="${tone(y.after_investing)}">${cr(y.after_investing)}</td></tr>`).join("")}
    </table></section>`;
}

function caseLens(th) {
  return `<section class="lens" id="case"><div class="section-h"><h2>Bull / bear</h2></div>
    <div class="case bull"><h4>Bull</h4><ul>${(th.bull || []).map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>
    <div class="case bear"><h4>Bear</h4><ul>${(th.bear || []).map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div></section>`;
}

/* ---------- Settings sheet ---------- */

async function openSettings() {
  const s = await api("/api/settings");
  const u = await api("/api/usage").catch(() => null);
  const sheet = $("#sheet");
  const watchable = Object.keys(CAT).filter((k) => k !== "unclassified");
  sheet.innerHTML = `<div class="panel">
    <h2>What counts as unusual</h2><p class="hint">FINN watches every close and every filing; you decide where the line is.</p>
    <div class="field"><label>Daily price move <span id="pv">±${s.price_pct}%</span></label>
      <input type="range" id="price" min="1" max="10" step="0.5" value="${s.price_pct}"></div>
    <div class="field"><label>Volume spike <span id="vv">${s.vol_mult}×</span></label><small>vs the 20-day average</small>
      <input type="range" id="vol" min="1.5" max="5" step="0.1" value="${s.vol_mult}"></div>
    <div class="field"><label>Default digest window <span id="wv">${s.window_hours}h</span></label>
      <input type="range" id="win" min="6" max="168" step="6" value="${s.window_hours}"></div>
    <div class="field"><label>Alert me on filings about</label>
      <div class="toggles">${watchable.map((k) => `<button class="chip ${s.watch.includes(k) ? "on" : ""}" data-w="${k}">${CAT[k]}</button>`).join("")}</div></div>
    <button class="save" id="save">Save</button>
    ${u && u.rows.length ? `<div class="usage"><div><span>Model spend so far${u.unpriced_calls ? " (priced calls only)" : ""}</span><span>$${u.usd_total.toFixed(3)}</span></div>
      ${u.rows.slice(0, 6).map((r) => `<div><span>${esc(r.task)} · ${esc(r.model.replace("gemini-", ""))}</span><span>${r.calls} calls · ${r.hits} cached</span></div>`).join("")}</div>` : ""}
  </div>`;
  sheet.hidden = false;
  const bind = (id, out, fmt) => { const el = $("#" + id); el.oninput = () => ($("#" + out).textContent = fmt(el.value)); };
  bind("price", "pv", (v) => `±${v}%`); bind("vol", "vv", (v) => `${v}×`); bind("win", "wv", (v) => `${v}h`);
  sheet.querySelectorAll("[data-w]").forEach((b) => b.onclick = () => b.classList.toggle("on"));
  sheet.onclick = (e) => { if (e.target === sheet) sheet.hidden = true; };
  $("#save").onclick = async () => {
    const watch = [...sheet.querySelectorAll("[data-w].on")].map((b) => b.dataset.w);
    meta.settings = await api("/api/settings", { method: "PUT", body: JSON.stringify({
      price_pct: +$("#price").value, vol_mult: +$("#vol").value, window_hours: +$("#win").value, watch }) });
    store.set("hours", meta.settings.window_hours);
    sheet.hidden = true;
    route();
  };
}

/* ---------- router ---------- */

async function route() {
  const h = location.hash.replace(/^#/, "") || "/";
  const tab = h.startsWith("/alerts") ? "alerts" : h.startsWith("/r") || h.startsWith("/research") ? "research" : "today";
  document.querySelectorAll(".tabs a").forEach((a) => a.classList.toggle("on", a.dataset.tab === tab));
  window.scrollTo(0, 0);
  try {
    if (h.startsWith("/alerts")) await renderAlerts();
    else if (h.startsWith("/r/")) await renderResearch(decodeURIComponent(h.slice(3)).toUpperCase());
    else if (h.startsWith("/research")) await renderResearchHome();
    else await renderToday();
  } catch (e) {
    view.innerHTML = `<div class="empty"><b>Something broke.</b>${esc(e.message)}</div>`;
  }
}

async function boot() {
  meta = await api("/api/meta").catch(() => ({ settings: { price_pct: 4, vol_mult: 2, window_hours: 72 } }));
  if (meta.as_of) $("#asof").textContent = "as of " + new Date(meta.as_of).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hour12: false });
  if (meta.sample) $("#banner").innerHTML = `<div class="banner">Sample data for UI development, not real filings. Run <code>python -m finn refresh</code> for live data.</div>`;
  api("/api/alerts?days=14").then((list) => {
    const seen = store.get("alerts_seen");
    const idx = list.findIndex((a) => a.id === seen);
    const n = idx === -1 ? list.length : idx;
    $("#alert-dot").textContent = n ? (n > 9 ? "9+" : n) : "";
  }).catch(() => {});
  $("#open-settings").onclick = openSettings;
  window.addEventListener("hashchange", route);
  route();
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
}

boot();
