# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Static HTML, CSS and plain JavaScript in `site/`, no build step, no frameworks. One small charting library stored in the repo at a pinned version (no CDNs). Deployed by GitHub Actions to Cloudflare Pages (direct upload), behind Cloudflare Access. All scripts in our own files (no inline scripts), to fit the Content Security Policy.

## Users

The builder (a university economics student) plus about four friends: mostly university students, some studying economics. Interested in markets, not professionals. Some know what a moving average or a put/call ratio is, some don't. Design for a curious non-expert by default.

## Product Purpose

A private live markets dashboard that goes with a daily 14:45 UK email digest. It shows where US, UK/European, Hungarian, CEE and Asian markets, FX, bonds, commodities and volatility stand right now, how they compare with their own recent trend, and what options markets are pricing for SPY and QQQ. Success: a reader can see in under a minute what moved and whether anything is flagged, and can learn what each number means.

## Positioning

A personal, Hungary-aware view of world markets (forint, BUX and its main stocks, Hungarian bonds, CEE peers beside the US and Europe) that explains itself to a learner, built from our own pipeline with every number's source and time shown.

## Operating Context

- Readers mostly arrive from the link in the daily email; they use both phones and laptops (inferred from the project brief).
- Data refreshes every 5 minutes on weekdays, 07:00–21:00 UTC, best-effort; some prices are delayed ~15 minutes by the exchange. Weekends show the end-of-day data.
- Sign-in is Cloudflare Access (email one-time PIN); the page itself has no login code.

## Capabilities and Constraints

- Groups follow the instrument table in `config/instruments.toml`, in that order (inferred from the brief).
- Per instrument: last value with its own time, market state (closed / pre-market / open / after-hours), daily change (% or bp for yields and spreads), 50/200-day moving averages and distance, crossings, 52-week high/low and distance, 20-day realised volatility, source, chart link, `suspect` flag, missing reason.
- A price chart per instrument with the 50- and 200-day moving averages; an options block for SPY and QQQ.
- TradingView iframe widgets for live prices beside our own charts; our numbers stay the source of truth.
- Missing data is shown as missing with its reason; `suspect` values carry a warning. Never estimated.
- An "Explain terms" on/off switch at the top, on by default, showing a short plain-English explanation under each section and on each indicator; each reader's choice is remembered in their own browser (localStorage, wrapped in try/catch).

## Evidence on Hand

Real data in the private data repo: `data/latest.json` and `data/history/prices.csv`. No testimonials or users beyond the five readers; nothing public.

## Product Principles

1. Truth over polish: every number shows its source and time; gaps and suspect values are visible, never hidden or filled.
2. Explain, don't assume: plain-English help is one switch away and on by default.
3. Glanceable first, deep second: what moved and what is flagged must read in seconds on a phone.
4. Private by construction: nothing on the page exists outside Cloudflare Access.

## Accessibility & Inclusion

Up/down never relies on colour alone (arrows or signs too), for colour-blind readers.
