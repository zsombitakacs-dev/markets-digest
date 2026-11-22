---
version: 1
slug: "site-index-html"
primary_target: "site/index.html"
related_targets: []
---

# Dashboard (site/index.html)

Scope: the private live dashboard. Mode: Operate. Readers: the builder plus ~4 student friends, curious non-experts; phone glance after the 14:45 email, laptop study sometimes.
Task: see what moved and what is flagged in under a minute; open any instrument for its chart, moving averages and 52-week range; read the SPY/QQQ options block; learn the terms via the "Explain terms" switch (on by default, remembered per browser).
Constraints: static files, plain JS in our own files, no inline scripts, uPlot vendored, TradingView iframes only, data from latest.json + history.json behind Cloudflare Access. Missing and suspect values visible, never filled.

## Direction contract

THESIS: The dashboard reads like a central bank's Inflation Report: every table and chart is numbered and cited, so a reader trusts and can quote any figure. Refuses the dark trading-terminal and the card-grid fintech app.
OWN-WORLD: White report paper, deep navy ink for headings, rules and the price line, one ochre accent for the 50-day average and the current marker; green/red only on changes and always with ▲/▼. Hairline-ruled statistical tables, tabular figures, system sans throughout.
STORY: The reader sees the update time and any flags, skims group tables top to bottom, taps a row to open its numbered chart and indicators, and switches explanations off once they know the terms.
FIRST VIEWPORT: Top bar: "Markets Digest" wordmark left, "Updated HH:MM UK" and the Explain-terms switch right. Below, a horizontal contents strip of group names. Then "Table 1 US equities": instrument, last, change, vs 50d/200d, 52-week range bar, state and time, with a "Source:" line under the table. Phone: name + state/time stacked, last, change.
FORM: Inflation Report (central-bank statistical report), position 1 on the ordered list (IMPECCABLE'S PICK, chosen by the user over the assigned direction 7). seed:049a38148d650198
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
