# Learning notes

Plain-English notes on every coding and finance idea used in this project, with examples from it.

## Coding and tools

### Git and a commit
Git records the history of a folder. A **commit** is a saved snapshot with a message saying what changed and why.
Example: this repo's first commit, "Set up project layout", holds the empty folder structure and this file.
Reading `git log` should tell the story of the build, one working step at a time.

### GitHub, public and private repos
A **repo** (repository) is a folder tracked by Git. GitHub hosts repos online.
This project uses two: `markets-digest` is **public** (the code, which anyone can read, good for a CV) and
`markets-digest-data` is **private** (the prices, digests and logs, visible only to the owner).
Rule of the project: the code is public, the content is private.

### Two-factor authentication (2FA)
Logging in needs a password **and** a one-time code from your phone. A stolen password alone is then useless.
It matters here because whoever controls the GitHub account controls the page, the data and the secrets.

### The noreply commit email
Every commit stores an author email, and in a public repo anyone can read it.
GitHub gives each user a private stand-in address like `12345+username@users.noreply.github.com`,
so commits are still linked to your profile without exposing your real email.

### Virtual environment (venv)
A private copy of Python for one project, in the `.venv/` folder, so this project's libraries
(e.g. `yfinance`) don't clash with other projects. Activate it with `source .venv/bin/activate`.
It is never committed: anyone can recreate it from `requirements.txt`.

### .gitignore
A list of files Git must never track. Here: the venv, Python caches, `.env` (secrets) and the
data folder, so private content can't be committed to the public repo by accident.

### Dependabot
A GitHub robot that checks weekly whether the libraries and actions we pin have updates (often security fixes)
and suggests the change. Config: `.github/dependabot.yml`.

### Repo security settings (applied in phase 0)
- **Outside contributors need approval:** a stranger's proposed change can't run our workflows (which hold secrets) until we approve it.
- **Read-only workflow token:** each workflow gets a temporary GitHub token; by default it may only read, and a workflow must ask for more explicitly.
- **Branch rule on `main`:** blocks force-pushes (rewriting history) and deleting the branch, so the history can't be quietly erased.
- **Secret scanning and push protection:** GitHub refuses a push that contains something that looks like a key or token.
- **Actions switched off in the data repo:** it only stores content, so there is nothing there that should ever run.

### TOML config file
A plain-text settings format that Python 3.11+ reads with the built-in `tomllib`. Every instrument lives in
`config/instruments.toml`, so adding a market means adding a block of text, not changing code.
Example: the S&P 500 is `source = "yahoo"`, `symbol = "^GSPC"`.

### APIs, CSV, JSON and scraping
An **API** is a web address built for programs rather than people. Here they answer in **CSV** (a table as text,
e.g. FRED's `2026-11-18,5.07`), **JSON** (nested labelled data, e.g. ÁKK's `{"tenor": "10Y", "yield": 5.5}`)
or XML (the MNB). **Scraping** means reading a number out of a page made for people (we do this for BUX and PX).
It breaks when the site is redesigned, so the parser raises a clear error ("layout changed?") instead of guessing.

### User agent
Every web request says what program sent it. Sites filter on this: on 2026-11-20 FRED stalled requests that
pretended to be a browser, and the Bank of England refused Python's default (403 Forbidden). The pipeline sends one
honest name, `markets-digest/0.1`, which every source accepts.

### Fallback sources and "never estimate"
If the main source fails, a second one is tried, and the output records which one gave the number
(`source = "mnb:EUR"`) and why the first failed. If both fail, the value is `missing` with the reason. A gap is
shown as a gap: a wrong number in a digest is worse than no number.

### Batched requests
Asking Yahoo for 41 symbols in one call takes about 10 seconds; one call per symbol would take minutes and risks being
rate-limited (blocked for asking too often). `fetch_yahoo` sends them all at once.

### UTC and time zones
Every time is stored in **UTC** (London winter time, no daylight saving), so times from Tokyo, Budapest and New York
compare directly. Example: the Prague exchange shows `16:35:00` local time; that is stored as `15:35:00+00:00`.
Daily-only sources (FRED, the BoE, the ECB) store just a date, e.g. `2026-11-18`: they publish one number per day.

### Unit tests and mocks
A **test** runs a function on a known input and checks the answer (`python -m unittest`). A **mock** swaps a real
web call for a fake one, so the fallback logic can be tested offline: we pretend Yahoo failed and check the MNB
rate is used instead.

## Finance

### Stock index
One number tracking a basket of shares, e.g. the BUX tracks the largest Budapest-listed companies (OTP, MOL, Richter,
Magyar Telekom carry most of the weight). On 2026-11-20 the BUX was at 137,270, down about 4% on the day.

### Futures
A contract to buy or sell something at a fixed price on a future date. S&P 500 futures (`ES=F`) trade almost 24 hours,
so they show where US shares are heading before New York opens. Oil, gas, metals and grains are tracked through their
**front-month** future (the one expiring soonest), e.g. Brent `BZ=F` at $88.53.

### Exchange rate quotes
EUR/HUF = 373.30 means 1 euro costs 373.30 forints. A **rise** means a **weaker forint**. The **DXY** (dollar index)
measures the dollar against six major currencies (mostly the euro); 103.64 on 2026-11-20.
The MNB and the ECB publish one official **reference rate** a day; Yahoo's is a live market rate.

### Government bond yield
The yearly return you get for lending to a government at today's bond price. Prices and yields move in opposite
directions. On 2026-11-20: Germany 10-year 3.32%, Hungary 10-year 5.50%. The gap is extra pay investors demand for
lending to Hungary (higher inflation, a weaker currency, higher risk).

### Basis points
One **basis point (bp)** is 0.01 percentage point. Yields are compared in bp because the moves are small:
a German 10-year going from 3.32% to 3.35% is "up 3 bp". Instruments marked `kind = "rate"` will get bp changes in phase 2.

### Benchmark and spot yields
A **benchmark** yield is the yield of one chosen, actively traded bond for each maturity (ÁKK's 10-year is the 2037/A bond).
The Bank of England publishes a **spot (zero-coupon) curve** instead: a smooth line fitted through all gilts, read off at
2 and 10 years (4.73% and 5.30% on 2026-11-19). Both are standard; they can differ by a few bp.
ÁKK has no 2-year benchmark, so the 3-year (5.48%) stands in.

### The 2s10s spread (yield curve slope)
10-year yield minus 2-year yield. Normally positive (lending longer pays more). When it goes **negative** ("inverted")
markets expect rate cuts, often because of a coming slowdown. FRED's `T10Y2Y` was +0.28 points on 2026-11-19.

### BUBOR
The Budapest interbank offered rate: what banks say they would charge each other for forint loans. The 3-month BUBOR
(5.50% on 2026-11-20) sits close to the MNB's policy rate and feeds into Hungarian variable-rate loans.

### Credit spread
How much more yield a company bond pays than a government bond of similar maturity, as payment for the risk the company
defaults. On 2026-11-19: investment-grade (safer companies) 0.94 points, high-yield ("junk") 3.52 points.
Spreads widen when investors get nervous.

### CDS (credit default swap)
Insurance against a borrower defaulting; its price is a market measure of credit risk. Hungary's 5-year CDS is
watched closely, but no free source exists, so it is listed as unavailable.

### VIX and VSTOXX
"Fear gauges": the volatility (size of swings) that option prices imply for the next 30 days, for the S&P 500 (VIX) and
the EURO STOXX 50 (VSTOXX). Around 12–20 is calm; 29.9 (VIX on 2026-11-20) signals a nervous market.
