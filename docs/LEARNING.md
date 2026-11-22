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

### Saved sample files (test fixtures)
A test of a file reader needs a file. `tests/samples/` holds small trimmed copies of what the sources really sent on
2026-11-20: the Bank of England's Excel workbook, the MNB's old-format `.xls` BUBOR file, ÁKK's JSON and a slice of the
Budapest exchange's page. The tests feed them to the same parsers a real download goes through, so if a source changes
its format, a fresh sample shows exactly what broke. Example: in the BUBOR file the column names switched from
Hungarian (`3hónap`) to English (`3months`) in 2023, and the sample includes one sheet of each.

### Excel files: .xlsx and .xls
`.xlsx` (Excel since 2007) is a zip of XML files, read with `openpyxl`. `.xls` is the older binary format, read with
`xlrd`. Excel stores dates as a **day number** counted from 30 Dec 1899: in the BUBOR file `46027` means 5 Jan 2026.

### Price history file (`history/prices.csv`)
One row per instrument per day: `2026-11-20,otp,38690.0,yahoo:OTP.BD`. The first run fills about two years from each
source (a **backfill**); after that, the end-of-day run adds each day's close. The averages are worked out from this file,
so a five-minute run only has to fetch today's prices. BUX, PX and WIG20 have no free history, so their averages fill in
as our own closes build up (the 50-day average after 50 trading days, about ten weeks).

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
a German 10-year going from 3.38% to 3.32% is "down 6 bp" (2026-11-20). Everything marked `kind = "rate"` (yields,
spreads, BUBOR) has its changes and distances in bp; everything else in %. `latest.json` says which in `change_unit`.

### Benchmark and spot yields
A **benchmark** yield is the yield of one chosen, actively traded bond for each maturity (ÁKK's 10-year is the 2037/A bond).
The Bank of England publishes a **spot (zero-coupon) curve** instead: a smooth line fitted through all gilts, read off at
2 and 10 years (4.73% and 5.30% on 2026-11-19). Both are standard; they can differ by a few bp.
ÁKK has no 2-year benchmark, so the 3-year (5.48%) stands in.

### The 2s10s spread (yield curve slope)
10-year yield minus 2-year yield. Normally positive (lending longer pays more). When it goes **negative** ("inverted")
markets expect rate cuts, often because of a coming slowdown. FRED's `T10Y2Y` was +0.28 points on 2026-11-19.

**Hungary's curve is measured as 3s10s, not 2s10s**: ÁKK has no 2-year benchmark, so the slope is the 10-year minus
the **3-year**. On 2026-11-20 that was 5.50% − 5.48% = +0.02 points: almost flat. It is calculated only from two yields
of the same day, and must always be labelled 3s10s, because a 2s10s and a 3s10s are not directly comparable.

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

## Indicators (phase 2)

All of these are in `pipeline/indicators.py` and are tested with numbers worked out by hand in `tests/test_indicators.py`.

### Daily change
Today's value against the **previous close** (the last day's final value). For prices in %, for rates in bp.
Example, 2026-11-20 at 16:25 UTC: S&P 500 −1.47%; German 10-year −6 bp. `prev_close_date` says which day it is compared with.

### Simple moving average (SMA), 50-day and 200-day
The average of the last 50 (or 200) daily closes. It smooths out the noise and shows the trend. Traders watch whether the
price is **above** its 200-day average (a long-term uptrend) or **below** it. On 2026-11-20 the S&P 500 (7,071) was 7.3%
below its 50-day average (7,628) and 3.8% below its 200-day one. When the price **crosses** an average between two runs,
`crossed_sma50` or `crossed_sma200` says `"above"` or `"below"`: a common signal that a trend may be turning.

### 52-week high and low
The highest and lowest close of the past year. EUR/HUF at 373.73 was 5.3% below its 52-week high (394.71), so the forint
was weaker than a few weeks earlier but stronger than at its worst point of the year. It is only shown once there is a
full year of history: a "52-week high" from two weeks of data would look real but is not.

### Realised volatility (20-day, annualised)
How much the price actually moved over the last 20 trading days: the standard deviation of the daily moves (log returns
for prices, bp changes for rates), times √252 to turn it into a yearly figure. The S&P 500's was 23.9% on 2026-11-20,
nervous for an index that is usually around 12–18%. Compare it with **implied** volatility (phase 3), which is what option
prices expect for the future: the VIX (30.2) is the S&P 500's implied volatility.

### Market state
For each instrument: `open`, `closed`, `pre-market` or `after-hours`, from the trading hours in `config/instruments.toml`
and the exchange's own time zone (so summer time is handled). Pre-market and after-hours exist only in New York.
Futures and FX trade almost around the clock from Sunday evening to Friday. Figures published once a day (FRED, the BoE,
ÁKK, BUBOR) are always `closed`: they are final numbers for their date. The timetables have no public holidays, so a
market the timetable calls open whose latest price is more than 30 minutes old is marked `closed (holiday?)`: on US
Thanksgiving (26 Nov 2026) at 10:30 New York, the S&P 500's last price is Wednesday's close, so it shows `closed (holiday?)`.
The question mark is honest: a price can also stop updating because the source is late. For the first 45 minutes of a
session the check is skipped and the state is `just opened`: some prices are delayed 15 minutes, so at 09:35 New York the
latest one can still be yesterday's close on a perfectly normal day. The options block uses the S&P 500's checked state,
so on Thanksgiving it keeps Wednesday's options data instead of fetching a holiday chain with no live prices. BUX
has no timestamp of its own (the BSE page doesn't give one), so it takes OTP's checked state: same exchange, same
holidays. On 23 October, a Hungarian national holiday, OTP's last price is the day before's close, so both show
`closed (holiday?)`.

### Sanity checks (`suspect`)
Before a number is published, it is compared with the **last value that was not suspect**. A price of zero or below, or
a move bigger than a set limit (20% for an index or commodity, 10% for an FX pair, 100% for VIX/VSTOXX, 100 bp for a yield
or spread), marks it `suspect` with the reason. A suspect value is shown with a warning, is never saved into the price
history, and the digest treats it as unavailable.

A glitch and a real crash look the same at first, so the next run decides:
- **Glitch:** the DAX shows 31,330 (+30%), then 24,120 on the next run. The second value is compared with the last good one
  (24,100), so it is fine, and 31,330 never reaches the history.
- **Real move:** the DAX shows 31,330, then 31,400 on the next run. Two runs in a row agree (within 1% for prices, 5 bp for
  rates), so it is accepted as real (`confirmed_jump` says so) and goes into the history as normal.

## Options (phase 3)

All of these are in `pipeline/options.py`, tested in `tests/test_options.py`. Data: Yahoo Finance, delayed about 15
minutes, so the `time` field is the newest trade in the chain, not the run time. Examples from 2026-11-20 at 16:43 UTC.

### Calls and puts
An **option** is a contract giving the right, not the duty, to trade something at a set price (the **strike**) up to a
set date (the **expiry**). A **call** is the right to buy: it pays off if the price rises above the strike. A **put** is
the right to sell: it pays off if the price falls below it, so puts work like insurance. SPY (an ETF tracking the S&P 500)
was at 702.82; a December 800 call only pays if SPY gains more than 13% by 18 December.

### Expiries: monthly and quarterly
Most options trade around the **monthly expiry**, the third Friday of the month (the Thursday before if that Friday is a
market holiday: 17 June 2027, because 18 June is Juneteenth). March, June, September and December expiries are
**quarterly** and the biggest, because futures and index options expire together ("quad witching"), which can make
markets jumpy that day. We use the nearest monthly expiry *after* today: on expiry day an option has only hours left and
its numbers are noise. On 2026-11-20 (itself an expiry day) that was 2026-12-18, 28 days away.

### Open interest
How many contracts are open (bought and not yet closed) at a strike. It is updated once a day, overnight. Strikes with very
large open interest show where traders hold big positions: SPY's largest put open interest was at 480 (315,443
contracts), far below the price, which is mostly long-term crash insurance held by funds.

### Put/call ratio
Puts divided by calls, by **volume** (contracts traded today) or by **open interest** (contracts outstanding). Above 1
means more puts than calls: more hedging, more fear. SPY: 1.21 by volume, 1.84 by open interest. QQQ (the Nasdaq 100
ETF): 0.86 and 0.97. SPY's ratio is usually above 1 anyway, because big funds hedge stock portfolios with SPY puts, so
compare it with its own past, not with 1.

### Implied vs realised volatility
**Implied volatility (IV)** is the size of swings that option prices expect until expiry, as a yearly %. It is worked
backwards from the option's price: dearer options mean bigger expected swings. **Realised volatility** (phase 2) is how
much the price actually moved. We take IV **at the money** (the strike nearest the price, where options are traded most)
and average the call and the put, because Yahoo's figures for the two differ by a few points. SPY's at-the-money IV was
25.7% against a realised 20-day volatility of 24.2% for the S&P 500: traders were paying for slightly more turbulence
than had just happened. When implied is well above realised, insurance is expensive; when below, it is cheap.
If there is no live bid and ask at the money (often after hours), `atm_iv` is left empty with a reason, not guessed.

## Automation (phase 4)

The pipeline now runs by itself in GitHub's cloud. Four **workflows** (files in `.github/workflows/`) say what to run and when.

### GitHub Actions and a workflow
A workflow is a list of steps that GitHub runs on a fresh, temporary Linux computer (a **runner**), started by a
**trigger**: a schedule, or the "Run workflow" button (`workflow_dispatch`). Ours: `intraday` (every 5 minutes on
weekdays), `pre-digest` (14:35 London), `end-of-day` (22:04 UTC) and `keep-alive` (monthly). Each run starts from nothing:
it downloads the code and the data repo, installs Python packages, runs `python -m pipeline.run`, and the computer is
thrown away. A full run takes about 6 seconds of fetching, plus about a minute of setup.

### Cron schedule
A cron line is five fields: minute, hour, day of month, month, day of week. `2-59/5 7-20 * * 1-5` means minute 2, 7, 12,
... 57, of hours 07 to 20, any day of the month, any month, Monday (1) to Friday (5): 07:02 to 20:57 UTC. Times are UTC
in UTC. `pre-digest` first used GitHub's `timezone: Europe/London` key, but its runs on 21 and 22 Nov 2026 started at
20:39 and 20:49 UTC: 14:35 in US Central time, six hours late. So it now runs at both 13:35 and 14:35 UTC, and a
first "gate" job (`pipeline/schedule_gate.py`) lets through only the one that is 14:35 in London that day (13:35 UTC
in summer, 14:35 UTC in winter). It decides from the cron that fired, not the clock, so a run that starts late still
goes ahead. As a backup, an intraday run between 14:30 and 14:40 London commits the data itself if the pre-digest
run has not. Lesson: test a scheduling feature with a real run before relying on it.
Runs that start exactly on the hour are the most often delayed (everyone picks :00), so ours are a few minutes off it.
GitHub schedules are best-effort: at busy times a run can start late or be skipped.

### Secrets and access tokens
An access token is a password for a program, limited to certain actions. `DATA_REPO_TOKEN` can only read and write the
contents of `markets-digest-data`, and expires on 2027-09-01 (renew it before then, or the runs will fail). It is
stored as an Actions **secret**: workflows can use it, GitHub hides it in logs, and nobody can read it back, not even the owner.

### Least privilege (`permissions:`)
Each workflow also gets an automatic token for its own repo. `permissions: contents: read` means it can only read this
repo, so even a broken step cannot change the code. Only `keep-alive` has `contents: write`, because its job is a commit here.

### Pinning actions to a commit SHA
Steps like `actions/checkout` are other people's code. A tag such as `v7` can be moved to new code by whoever controls
it; a commit SHA (`3d3c42e5...`) can't, so our workflows always run exactly the version that was checked. The version
is kept in a comment, and Dependabot proposes updates.

### Cache, and why intraday runs commit nothing
About 170 intraday runs a day would make 170 commits a day: a bloated, unreadable history. Instead each run saves its
`latest.json` (and a failure count) in the **Actions cache**, a small store GitHub keeps for the repo for 7 days. The next
run restores it, so "crossed its 50-day average since the previous run", the suspect checks and the options block carry
on from 5 minutes ago. Only `pre-digest` and `end-of-day` commit to the data repo. The cache is not public: only
workflows running in this repo can read it.

### Concurrency
`concurrency: group: intraday, cancel-in-progress: true` means that if a run is still going when the next one starts,
the old one is stopped, so runs never pile up. `pre-digest` and `end-of-day` share the group `data-repo` without
cancelling, so they wait for each other and never push to the data repo at the same time.

### Exit code: failing visibly
A program ends with a number: 0 for success, anything else for failure. If fewer than half the instruments could be
fetched, `pipeline.run` still writes its files, then exits with 1, so the run shows as failed and GitHub emails the owner.
`pre-digest` and `end-of-day` fail loudly at once. One failed intraday run is not worth an email, so `intraday` counts
failures in a row and fails loudly only at the 3rd, then every 12th. After any failure it also **backs off** and skips
every other run (every 10 minutes), in case the cause is Yahoo limiting our requests (HTTP 429, "too many requests").

### Options every 30 minutes
Option chains change slowly and are heavier to fetch, so a run reuses the last options block while it is under 30 minutes
old (`fetched_at` in each block says when it was taken). While the US market is shut, a block taken while it was open is
kept: at 22:04 UTC, and all weekend, `latest.json` shows Friday's last open-market options data, with its time, rather than
an after-hours chain with no live prices.

### Keep-alive
GitHub pauses schedules in a public repo after 60 days with no activity. Our daily commits go to the private repo, so on
the 1st of each month `keep-alive` writes the date into `status/last_run.txt` here and commits it.

## Private dashboard (phase 5)

The dashboard at `markets-digest.pages.dev` is a **static site**: plain HTML, CSS and JavaScript files, with no server
code and no database. The browser downloads them and draws the page itself from two data files.

### Static site and direct upload
`python -m pipeline.site_data` builds the folder `_site/`: the page from `site/`, plus `latest.json` and `history.json`
(a year of daily closes per instrument, with the 50- and 200-day averages at each day, for the charts). The intraday
workflow then uploads `_site/` to **Cloudflare Pages** with Cloudflare's `wrangler` tool ("direct upload"). Cloudflare
never sees the GitHub repo, and `_site/` is in `.gitignore`, so the data never enters the public repo. `end-of-day` deploys
once more after the US close (21:00 UTC), so evenings and weekends show closing prices.

### Cloudflare Access and the one-time PIN
Access is a gate in front of the whole site, every file included. A visitor first goes to a Cloudflare login page, types
an email address, and gets a 6-digit code only if that address is on the "Readers" list. After that a cookie keeps them
signed in for a month. We tested from outside: `/`, `/latest.json` and preview addresses like
`preview.markets-digest.pages.dev` all answer `302` (a redirect to the login page) instead of the content.

### Preview deployments
Each upload to Cloudflare Pages also gets its own address (`<id>.markets-digest.pages.dev`), and uploads to a branch other
than `main` become "previews" at `<branch>.markets-digest.pages.dev`. Old data stays reachable at those addresses, so the
Access application covers `*.markets-digest.pages.dev` as well as the main address.

### Content Security Policy (CSP)
A header the server sends with the page, listing where the page may load things from. Ours (`site/_headers`) allows
scripts, styles and data only from our own site, and frames only from TradingView. If anything tried to inject a script
(say, a hostile instrument name in the data), the browser would refuse to run it. As a second guard, `app.js` only ever
inserts text with `textContent`, which shows `<script>` as plain characters instead of running it.

### Why the charting library lives in the repo
`site/vendor/uPlot.iife.min.js` is uPlot 1.6.32, downloaded once from npm and checked against npm's published checksum
(`sha512-KIMVnG68…`). Loading it from a CDN instead would mean trusting that server on every page view; a copy in the repo
can only change through a commit we can see.

### Moving averages on the chart
Each chart line is a series of averages: on every day, the mean of the last 50 (or 200) closes up to that day. The averages
use closes from before the chart's first day too, so the lines start at the left edge. Example from the data: on
2026-11-20 the S&P 500 closed at 7,054, below its 50-day average (7,628, −7.5%) and its 200-day average (7,349, −4.0%).
For yields, the distance from an average is in basis points, not %: the US 10-year at 4.94% sat 13.4 bp below its 50-day
average.

### Explain terms
A switch at the top shows or hides the plain-English notes. The reader's choice is saved in their own browser
(`localStorage`), so it is remembered on that device only and never sent anywhere. If the browser blocks storage (e.g. a
private window), the switch still works and simply starts "on" next time.

### CFDs in the TradingView widgets
A **CFD** (contract for difference) is a contract a broker offers on an asset's price: you gain or lose the change in
price without owning the asset. TradingView's free widgets are not allowed to show many official index and futures
prices (they say "Permission denied"), but they can show brokers' CFDs, which follow the market closely. So the S&P 500
row's live widget shows `FOREXCOM:SPXUSD`, a CFD, and the page says so: it tracks the index, not the official value. A few widgets (WIG20, PX, Shanghai) only have end-of-day data, marked E by TradingView, and the page labels those too. Our
own numbers, from the official sources, stay the ones the digest uses. Every symbol in `config/instruments.toml` was
checked in a real browser; yields and the VIX have no widget, as none was allowed.

## Daily digest and email (phase 6)

The digest is written every day at 14:45 UK by a scheduled Claude task in the Claude app. It follows
`prompts/daily_digest.md`, fills in `templates/email.html`, and pastes number tables that the
pipeline has already rendered (`pipeline/email_tables.py`). So code makes every number and the task
writes only the words.

### Why the pipeline renders the tables
A language model retyping ~200 numbers can slip (a sign, a decimal, % for bp). So the pre-digest run
writes `data/email_tables.html` and `.txt` from `latest.json`, and the task pastes them unchanged.
Each file starts with `run_at:`, and the task checks it equals `latest.json`'s, so stale tables are
caught. This is a general rule: let code do the exact work and leave the writing to the model.

### Data surprise and consensus
Before a release (say US CPI), economists' forecasts are collected; their median is the **consensus**.
A **surprise** is the actual figure minus the consensus. Markets move on the surprise, not on the
level: inflation of 3.1% moves bond yields if 2.9% was expected, but barely if 3.1% was. The digest
shows actual, consensus and previous side by side, and logs each one in `logs/data_surprises.csv`.

### An unusual move: how many "usual days"
The 20-day realised volatility is a yearly figure. Dividing by √252 (trading days in a year) turns
it back into a typical day's move. A move of 2 or more typical days is flagged as notable.
Example from 20 Nov: EUR/PLN's volatility was 5.74% a year, so a usual day is 5.74 / √252 ≈ 0.36%.
It moved 1.11%, about 3.1 usual days, so it appears under "Notable moves elsewhere".
(For yields both numbers are in basis points; the sum works the same way.)

### Weekly change
The Sunday table compares the last close with the last close at least 7 days earlier, so a holiday
does not break it. On 20 Nov the S&P 500 closed at 6,918.45 against 7,561.67 on Fri 13 Nov:
6,918.45 / 7,561.67 − 1 = −8.51%.

### Market-implied odds
Futures on short-term interest rates (for the Fed: fed funds futures) are priced from where traders
expect the policy rate to be. From their prices you can work out the probability the market puts on
a cut or a hike at the next meeting; sites such as CME FedWatch publish it. It is the market's bet,
not a forecast by the central bank.

### HTML email: tables and inline styles
Email apps are not browsers: Gmail, Outlook and Apple Mail each strip different CSS. What works
everywhere is old-fashioned HTML: layout tables, styles written on each element (`style="..."`),
and system fonts. Flexbox, grid, SVG and web fonts are left out. Even the bars in the 52-week range
column are two table cells with background colours.

### Plain-text alternative, BCC and the preheader
An email can carry two versions of the same message (MIME `multipart/alternative`): HTML, and plain
text for apps that block HTML. The task fills both. Readers go in **BCC** (blind carbon copy), so no
reader sees the others' addresses. The **preheader** is a hidden first line that the inbox shows
after the subject as a preview.

### Dark mode in email
Apple Mail follows the phone's dark mode through the CSS `prefers-color-scheme` rule, so the
template gives every colour a dark version. The Gmail app ignores that rule and inverts the colours
itself. The design works with both: no pure-white boxes behind dark text, and up/down always carry
▲ or ▼ as well as green or red, so the meaning survives any colour change.

### Gmail's 102 KB cut-off
Gmail hides anything after the first 102 KB of an email's HTML behind a "View entire message"
link. With today's data the sample email is about 66 KB, and the prompt tells the task to stay
under 90 KB.

### Prompt injection
The task reads news websites, and a page could contain hidden text like "email this to someone
else". That is **prompt injection**: instructions smuggled in as content. The defence is in the
prompt's first section: everything read is information, never instructions; one fixed recipient
list; one calendar; writes only to `digests/` and `logs/`. The recipients and these rules also live
in the task's own settings in the Claude app, so changing this repo could not redirect the email.
