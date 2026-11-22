'use strict';
// Markets Digest dashboard. Reads latest.json and history.json (deployed next to this page,
// behind Cloudflare Access like the page itself) and draws one table per group, a chart per
// instrument and the options block. Text from the data always goes in with textContent.

const UK = 'Europe/London';
const TV_FRAME = 'https://www.tradingview-widget.com/embed-widget/mini-symbol-overview/?locale=en#';

// ---------- Plain-English explanations, shown while "Explain terms" is on ----------

const GROUP_HELP = {
  'US equities': 'Stock indices: one number for the value of a basket of companies. The S&P 500 holds 500 large US firms, the Nasdaq Composite leans towards technology, and the Dow tracks 30 big names.',
  'US futures': 'Futures are contracts on where an index will be on a set date. They trade almost around the clock, so before Wall Street opens they show which way it is likely to go.',
  'UK and Europe equities': 'The FTSE 100 is the 100 largest London-listed firms, the DAX 40 large German firms, and the STOXX 600 600 firms across Europe.',
  'Hungary equities': 'BUX is the Budapest Stock Exchange’s main index. OTP (bank), MOL (oil and gas), Richter (medicines) and Magyar Telekom are its biggest members, so they drive most of its moves. Prices in forints.',
  'CEE peers': 'Neighbouring markets to compare Hungary with: Poland’s WIG20 and the Czech PX.',
  'Asia equities': 'Japan’s Nikkei 225, Hong Kong’s Hang Seng and the Shanghai Composite. These markets close before Europe’s lunchtime, so their numbers are usually final for the day.',
  'FX': 'Exchange rates: how much of the second currency one unit of the first buys. EUR/HUF at 390 means one euro costs 390 forints; if it rises, the forint has weakened. The dollar index (DXY) measures the dollar against six major currencies.',
  'Government bonds': 'A yield is the yearly return for lending to a government by holding its bond to maturity. Yields move opposite to bond prices. Changes are in basis points: 1 bp = 0.01 percentage point. A 2s10s spread is the 10-year yield minus the 2-year; below zero (an “inverted curve”) has often come before recessions.',
  'Money markets': 'BUBOR is the rate at which Hungarian banks lend each other forints. The 3-month rate follows where markets expect the MNB’s base rate to go.',
  'Credit and risk': 'A credit spread is the extra yield companies pay over government bonds. Investment-grade firms are the safest borrowers, high-yield (“junk”) the riskiest. Wider spreads mean investors want more pay for taking risk.',
  'Energy and metals': 'Commodity prices, mostly futures: Brent (the global oil benchmark) and WTI (US oil) in dollars a barrel, European gas (TTF) in euros per megawatt-hour, gold, silver and copper (a gauge of industrial demand).',
  'Agriculture': 'Wheat and corn futures, in US cents per bushel. Grain prices matter for food inflation, and Hungary is a big grain exporter.',
  'Volatility': 'The VIX is how much the options market expects the S&P 500 to swing over the next 30 days, as a yearly %. VSTOXX is the same for the euro area’s Euro Stoxx 50. Around 12–15 is calm; above 30 is stress.',
  'Optional': 'Bitcoin, in US dollars. It trades every day, around the clock.',
};

const HELP = {
  last: 'The most recent value and the time it is from. Some exchanges delay free prices by about 15 minutes.',
  prev: 'The last close before today: the base for the daily change.',
  change: 'Change since the previous close. For yields and spreads it is in basis points (bp): 1 bp = 0.01 percentage point.',
  sma50: 'The average close of the last 50 trading days (about 10 weeks). A price above it suggests a recent uptrend; below it, a downtrend.',
  sma200: 'The same over 200 trading days (about 10 months): the long-term trend. Crossing it is often read as a change of trend.',
  high: 'The highest close of the past 52 weeks, and how far below it the value is now.',
  low: 'The lowest close of the past 52 weeks, and how far above it the value is now.',
  vol: 'How much the price actually swung over the last 20 trading days, scaled to a year. 20% means typical moves of about ±20% a year.',
  state: 'Whether the market is trading right now. A closed market shows its last close.',
};

const OPTIONS_HELP = {
  intro: 'An option is the right, but not the duty, to buy (a call) or sell (a put) at a set price, the strike, until a set date, the expiry. SPY and QQQ are funds that track the S&P 500 and the Nasdaq 100. These figures are for the nearest monthly expiry.',
  underlying: 'The fund’s own price, which the strikes are compared with.',
  expiry: 'The expiry date these figures use, and the days left until it.',
  iv: 'Implied volatility of the option closest to today’s price: the yearly swing the options market is pricing in. Compare it with realised volatility in the tables above: implied above realised means traders are paying up for protection.',
  pcv: 'Puts traded today per call traded. Above 1 means more bets on, or protection against, a fall.',
  pcoi: 'The same for all contracts still open (open interest), not just today’s trades.',
  calls: 'The call strikes with the most open contracts (the number in brackets): levels many traders have bets above.',
  puts: 'The put strikes with the most open contracts: levels many traders are protected below.',
  monthly: 'Monthly options expire on the third Friday of the month.',
  quarterly: 'Quarterly expiries fall in March, June, September and December, and are usually the largest.',
};

// ---------- Small helpers ----------

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}
const isNum = (v) => typeof v === 'number' && Number.isFinite(v);
const fmt = (v, dp) => v.toLocaleString('en-GB', { minimumFractionDigits: dp, maximumFractionDigits: dp });
const decimals = (v, kind) => (kind === 'rate' || Math.abs(v) >= 10 ? 2 : 4);
const level = (v, kind) => fmt(v, decimals(v, kind)) + (kind === 'rate' ? '%' : '');
const explain = (text, tag = 'p') => el(tag, 'explain', text);
const slug = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, '-');

const ukDay = new Intl.DateTimeFormat('en-CA', { timeZone: UK, year: 'numeric', month: '2-digit', day: '2-digit' });
const ukTime = new Intl.DateTimeFormat('en-GB', { timeZone: UK, hour: '2-digit', minute: '2-digit' });
const ukDate = new Intl.DateTimeFormat('en-GB', { timeZone: UK, weekday: 'short', day: 'numeric', month: 'short' });
const plainDate = new Intl.DateTimeFormat('en-GB', { timeZone: 'UTC', weekday: 'short', day: 'numeric', month: 'short' });

// "14:35" for today (UK time), "Thu 19 Nov 16:30" before; date-only figures as "Thu 19 Nov".
function when(iso) {
  if (!iso) return '';
  if (!iso.includes('T')) return plainDate.format(new Date(iso + 'T12:00:00Z'));
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return ukDay.format(d) === ukDay.format(new Date()) ? ukTime.format(d) : `${ukDate.format(d)} ${ukTime.format(d)}`;
}

function ago(iso) {
  const min = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (!isNum(min) || min < 1) return 'just now';
  if (min < 90) return `${min} min ago`;
  const h = Math.round(min / 60);
  return h < 36 ? `${h} hours ago` : `${Math.round(h / 24)} days ago`;
}

const STATE_CLASS = { 'open': 'open', 'just opened': 'open', 'pre-market': 'ext', 'after-hours': 'ext' };

function stateLabel(r) {
  const s = el('span', 'state state-' + (STATE_CLASS[r.market_state] || 'closed'));
  s.append(el('span', 'state-dot'), r.market_state || 'no data');
  const t = when(r.time);
  if (t) s.append(el('span', 'state-time', ' · ' + t));
  return s;
}

function change(v, unit) {
  if (!isNum(v)) return el('span', 'muted', '–');
  const dir = v > 0 ? 'up' : v < 0 ? 'down' : 'flat';
  const s = el('span', 'chg chg-' + dir);
  if (dir !== 'flat') {
    s.append(el('span', 'sr-only', dir + ' '));
    const arrow = el('span', 'arrow', dir === 'up' ? '▲' : '▼');
    arrow.setAttribute('aria-hidden', 'true');
    s.append(arrow);
  }
  s.append(fmt(Math.abs(v), unit === 'bp' ? 1 : 2) + (unit === 'bp' ? ' bp' : '%'));
  return s;
}

function versus(r, n) {
  const d = r['dist_sma' + n];
  if (!isNum(d)) return el('span', 'muted', '–');
  const s = el('span', 'ma ma-' + (d >= 0 ? 'above' : 'below'));
  // Distances are in % for prices and in basis points for yields and spreads, like the change.
  s.append(el('span', 'ma-word', d >= 0 ? 'above' : 'below'), ' ' + fmt(Math.abs(d), 1) + (r.change_unit === 'bp' ? ' bp' : '%'));
  const crossed = r['crossed_sma' + n];
  if (crossed) s.append(el('span', 'tag tag-accent', 'crossed ' + crossed));
  return s;
}

function range(r) {
  const { high_52w: hi, low_52w: lo, value: v } = r;
  if (!isNum(hi) || !isNum(lo) || !isNum(v) || hi <= lo) return el('span', 'muted', '–');
  const p = Math.min(1, Math.max(0, (v - lo) / (hi - lo)));
  const bar = el('span', 'range');
  bar.setAttribute('role', 'img');
  bar.setAttribute('aria-label', `52-week range ${level(lo, r.kind)} to ${level(hi, r.kind)}; now ${Math.round(p * 100)}% of the way up`);
  const mark = el('span', 'range-mark');
  mark.style.left = (p * 100).toFixed(1) + '%';
  bar.append(mark);
  return bar;
}

// ---------- Explain switch: on by default, remembered in this browser only ----------

const explainBtn = document.getElementById('explain');
let explainOn = true;
try { explainOn = localStorage.getItem('explain') !== 'off'; } catch (e) { /* storage blocked: keep the default */ }
function showExplain(on) {
  document.documentElement.classList.toggle('explain-off', !on);
  explainBtn.setAttribute('aria-checked', String(on));
}
showExplain(explainOn);
explainBtn.addEventListener('click', () => {
  explainOn = !explainOn;
  showExplain(explainOn);
  try { localStorage.setItem('explain', explainOn ? 'on' : 'off'); } catch (e) { /* not remembered, still works */ }
});

// ---------- Data ----------

async function getJSON(path) {
  const res = await fetch(path, { cache: 'no-store', credentials: 'same-origin' });
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`);
  return res.json();
}
let historyP;
// One download, shared by every chart; forgotten after a failure so the next chart retries.
const history = () => (historyP ||= getJSON('history.json').catch((e) => { historyP = null; throw e; }));

// ---------- Tables ----------

function instrumentRows(r, chartNo) {
  const tr = el('tr', 'inst' + (r.suspect ? ' is-suspect' : ''));
  const nameCell = el('th', 'col-name');
  nameCell.scope = 'row';
  const btn = el('button', 'inst-open');
  btn.type = 'button';
  btn.setAttribute('aria-expanded', 'false');
  btn.append(el('span', 'inst-name', r.name), stateLabel(r));
  nameCell.append(btn);
  tr.append(nameCell);

  if (!isNum(r.value)) {
    const td = el('td', 'col-missing');
    td.colSpan = 5;
    td.append(el('span', 'tag tag-quiet', 'unavailable'), ' ' + (r.missing_reason || 'No value in this update.'));
    tr.append(td);
  } else {
    const last = el('td', 'num col-last', level(r.value, r.kind));
    if (r.suspect) last.append(el('span', 'tag tag-warn', 'check'));
    tr.append(last,
      el('td', 'num col-chg'), el('td', 'num col-ma'), el('td', 'num col-ma'), el('td', 'col-range'));
    tr.children[2].append(change(r.change, r.change_unit));
    tr.children[3].append(versus(r, 50));
    tr.children[4].append(versus(r, 200));
    tr.children[5].append(range(r));
  }

  const detail = el('tr', 'detail-row');
  detail.hidden = true;
  const td = el('td');
  td.colSpan = 6;
  detail.append(td);
  const id = 'detail-' + r.id;
  td.id = id;
  btn.setAttribute('aria-controls', id);
  btn.addEventListener('click', () => {
    const open = btn.getAttribute('aria-expanded') !== 'true';
    btn.setAttribute('aria-expanded', String(open));
    tr.classList.toggle('is-open', open);
    detail.hidden = !open;
    if (open && !td.firstChild) fillDetail(td, r, chartNo);
  });
  return [tr, detail];
}

function groupTable(group, rows, tableNo, chartStart) {
  const section = el('section', 'group');
  section.id = slug(group);
  const h = el('h2', 'caption');
  h.id = section.id + '-title';
  h.append(el('span', 'caption-no', `Table ${tableNo}`), group);
  section.append(h);
  if (GROUP_HELP[group]) section.append(explain(GROUP_HELP[group], 'p'));
  section.lastChild.classList.add('group-help');

  const wrap = el('div', 'table-wrap');
  const table = el('table', 'stats');
  table.setAttribute('aria-labelledby', h.id);
  const head = el('tr');
  [['Instrument', 'col-name'], ['Last', 'num col-last'], ['Change', 'num col-chg'],
    ['vs 50-day', 'num col-ma'], ['vs 200-day', 'num col-ma'], ['52-week range', 'col-range']]
    .forEach(([t, c]) => { const th = el('th', c, t); th.scope = 'col'; head.append(th); });
  const thead = el('thead');
  thead.append(head);
  const tbody = el('tbody');
  rows.forEach((r, k) => tbody.append(...instrumentRows(r, chartStart + k)));
  table.append(thead, tbody);
  wrap.append(table);
  section.append(wrap);

  const sources = [...new Set(rows.map((r) => r.source).filter(Boolean))];
  section.append(el('p', 'source', `Source: ${sources.join(', ') || 'none this update'}. Averages, ranges and changes: own calculations.`));
  return section;
}

// ---------- Detail: chart, indicators, live widget ----------

function fillDetail(td, r, chartNo) {
  const box = el('div', 'detail');
  const fig = el('figure', 'chart-fig');
  const cap = el('figcaption', 'caption caption-small');
  cap.append(el('span', 'caption-no', `Chart ${chartNo}`), `${r.name}: last 12 months, with 50- and 200-day moving averages`);
  const plot = el('div', 'chart');
  plot.append(el('p', 'muted chart-msg', 'Loading chart…'));
  const legend = el('p', 'legend');
  [['close', r.kind === 'rate' ? 'Yield' : 'Close'], ['m50', '50-day average'], ['m200', '200-day average']]
    .forEach(([k, t]) => { const s = el('span', 'key key-' + k); s.append(el('span', 'key-line'), t); legend.append(s); });
  const src = el('p', 'source');
  src.append(`Source: ${r.source || '–'}; averages: own calculations. `);
  if (r.chart) {
    const a = el('a', null, 'Official page or full chart');
    a.href = r.chart; a.rel = 'noopener noreferrer'; a.target = '_blank';
    src.append(a);
  }
  fig.append(cap, plot, legend, src);
  box.append(fig, indicators(r));
  if (r.tradingview) box.append(liveWidget(r.tradingview));
  td.append(box);

  history().then((h) => drawChart(plot, h[r.id], r.kind)).catch(() => {
    plot.replaceChildren(el('p', 'muted chart-msg', 'The chart data did not load. Reload the page to try again.'));
  });
}

function indicators(r) {
  const dl = el('dl', 'indicators');
  const item = (label, value, help) => {
    const div = el('div', 'ind');
    const dd = el('dd');
    dd.append(value);
    div.append(el('dt', null, label), dd);
    if (help) div.append(explain(help));
    dl.append(div);
  };
  const lv = (v) => (isNum(v) ? level(v, r.kind) : '–');
  const dist = (d) => (isNum(d) ? ` (${d >= 0 ? '+' : '−'}${fmt(Math.abs(d), 1)}${r.change_unit === 'bp' ? ' bp' : '%'})` : '');
  if (isNum(r.value)) item('Last', `${lv(r.value)} · ${when(r.time)}`, HELP.last);
  if (isNum(r.prev_close)) item('Previous close', `${lv(r.prev_close)} · ${when(r.prev_close_date)}`, HELP.prev);
  if (isNum(r.change)) item('Daily change', change(r.change, r.change_unit), HELP.change);
  item('50-day average', lv(r.sma50) + dist(r.dist_sma50), HELP.sma50);
  item('200-day average', lv(r.sma200) + dist(r.dist_sma200), HELP.sma200);
  item('52-week high', lv(r.high_52w) + dist(r.dist_high_52w), HELP.high);
  item('52-week low', lv(r.low_52w) + dist(r.dist_low_52w), HELP.low);
  item('Realised volatility, 20-day', isNum(r.vol_20d) ? fmt(r.vol_20d, 1) + '% a year' : '–', HELP.vol);
  item('Market', stateLabel(r), HELP.state);

  const notes = el('div', 'notes');
  if (r.suspect) notes.append(el('p', 'notice notice-warn', `Check this value: ${r.suspect_reason || 'it failed a sanity check'}. The digest treats it as unavailable.`));
  if (r.missing_reason && !isNum(r.value)) notes.append(el('p', 'notice', r.missing_reason));
  (r.indicator_gaps || []).forEach((g) => notes.append(el('p', 'note', 'Not yet: ' + g)));
  if (r.note) notes.append(el('p', 'note', r.note));
  const wrap = el('div', 'detail-side');
  wrap.append(dl);
  if (notes.firstChild) wrap.append(notes);
  return wrap;
}

function liveWidget(symbol) {
  const box = el('div', 'live');
  box.append(el('p', 'live-title', 'Live price from TradingView'));
  box.append(explain('A second, independent live quote. It can differ slightly from ours (a different feed or contract); our numbers above are the ones the digest uses.'));
  const dark = matchMedia('(prefers-color-scheme: dark)').matches;
  const cfg = { symbol, width: '100%', height: '100%', locale: 'en', dateRange: '1D', colorTheme: dark ? 'dark' : 'light', isTransparent: true, autosize: true };
  const f = el('iframe', 'live-frame');
  f.src = TV_FRAME + encodeURIComponent(JSON.stringify(cfg));
  f.title = `Live ${symbol} price from TradingView`;
  f.loading = 'lazy';
  f.referrerPolicy = 'strict-origin-when-cross-origin';
  f.setAttribute('sandbox', 'allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox');
  const credit = el('p', 'source');
  const a = el('a', null, `${symbol} on TradingView`);
  a.href = 'https://www.tradingview.com/symbols/' + symbol.replace(':', '-') + '/';
  a.rel = 'noopener noreferrer'; a.target = '_blank';
  credit.append(a);
  box.append(f, credit);
  return box;
}

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function drawChart(plot, s, kind) {
  if (!s || s.d.length < 2 || typeof uPlot === 'undefined') {
    plot.replaceChildren(el('p', 'muted chart-msg', 'Not enough daily closes yet to draw a chart.'));
    plot.nextElementSibling.hidden = true;  // no lines, so no legend
    return;
  }
  const xs = s.d.map((d) => Date.parse(d + 'T00:00:00Z') / 1000);
  const ink = cssVar('--ink'), muted = cssVar('--muted'), rule = cssVar('--rule'), accent = cssVar('--accent'), grey = cssVar('--line-200');
  const dp = s.c.length ? decimals(s.c[s.c.length - 1], kind) : 2;
  const val = (u, v) => (v == null ? '–' : fmt(v, dp) + (kind === 'rate' ? '%' : ''));
  const axis = { stroke: muted, grid: { stroke: rule, width: 1 }, ticks: { stroke: rule, width: 1 }, font: '12px system-ui, sans-serif' };
  const opts = {
    width: plot.clientWidth, height: plot.clientWidth < 500 ? 200 : 260,
    legend: { show: false },
    cursor: { y: false, points: { size: 6 } },
    scales: { x: { time: true } },
    axes: [{ ...axis, space: 70 }, { ...axis, size: 64, values: (u, ticks) => ticks.map((t) => fmt(t, kind === 'rate' || Math.abs(t) < 10 ? 2 : 0)) }],
    series: [
      { value: (u, v) => (v == null ? '' : plainDate.format(new Date(v * 1000))) },
      { label: 'Close', stroke: ink, width: 1.75, value: val },
      { label: '50-day', stroke: accent, width: 1.5, value: val },
      { label: '200-day', stroke: grey, width: 1.5, dash: [6, 4], value: val },
    ],
  };
  plot.replaceChildren();
  const u = new uPlot(opts, [xs, s.c, s.m50, s.m200], plot);
  new ResizeObserver(() => { if (plot.clientWidth) u.setSize({ width: plot.clientWidth, height: plot.clientWidth < 500 ? 200 : 260 }); }).observe(plot);
}

// ---------- Options ----------

function optionsTable(opts, tableNo) {
  const syms = Object.keys(opts || {});
  const section = el('section', 'group');
  section.id = 'options';
  const h = el('h2', 'caption');
  h.id = 'options-title';
  h.append(el('span', 'caption-no', `Table ${tableNo}`), `Options: ${syms.join(' and ') || 'none'}`);
  section.append(h, explain(OPTIONS_HELP.intro));
  section.lastChild.classList.add('group-help');
  if (!syms.length) { section.append(el('p', 'muted', 'No options data in this update.')); return section; }

  // Lists come back as arrays: one line each, so a strike never splits from its contract count.
  const strikes = (list) => (list || []).map((x) => `${fmt(x.strike, 0)} (${x.open_interest.toLocaleString('en-GB')})`);
  const dates = (list) => (list || []).map((d) => plainDate.format(new Date(d + 'T12:00:00Z')));
  const n2 = (v) => (isNum(v) ? fmt(v, 2) : '–');
  const rowsDef = [
    ['Fund price', 'underlying', (o) => (isNum(o.underlying_price) ? `${fmt(o.underlying_price, 2)} · ${when(o.underlying_time)}` : '–')],
    ['Expiry used', 'expiry', (o) => (o.expiry ? `${dates([o.expiry])[0]} (${o.days_to_expiry} days)` : '–')],
    ['At-the-money implied volatility', 'iv', (o) => (isNum(o.atm_iv) ? `${fmt(o.atm_iv, 1)}% a year (strike ${fmt(o.atm_strike, 0)})` : '–')],
    ['Put/call ratio, volume', 'pcv', (o) => n2(o.put_call_volume)],
    ['Put/call ratio, open interest', 'pcoi', (o) => n2(o.put_call_oi)],
    ['Largest call open interest', 'calls', (o) => strikes(o.top_call_oi)],
    ['Largest put open interest', 'puts', (o) => strikes(o.top_put_oi)],
    ['Next monthly expiries', 'monthly', (o) => dates(o.upcoming_monthly)],
    ['Next quarterly expiries', 'quarterly', (o) => dates(o.upcoming_quarterly)],
  ];
  const wrap = el('div', 'table-wrap');
  const table = el('table', 'stats options');
  table.setAttribute('aria-labelledby', 'options-title');
  const head = el('tr');
  head.append(el('th', 'col-name', ''));
  syms.forEach((s) => { const th = el('th', 'num', s); th.scope = 'col'; head.append(th); });
  const thead = el('thead');
  thead.append(head);
  const tbody = el('tbody');
  rowsDef.forEach(([label, key, f]) => {
    const tr = el('tr');
    const th = el('th', 'col-name');
    th.scope = 'row';
    th.append(el('span', 'opt-label', label), explain(OPTIONS_HELP[key], 'span'));
    tr.append(th);
    syms.forEach((s) => {
      const v = f(opts[s] || {});
      const td = el('td', 'num');
      if (Array.isArray(v)) v.length ? v.forEach((line) => td.append(el('span', 'line', line))) : td.append('–');
      else td.append(v);
      tr.append(td);
    });
    tbody.append(tr);
  });
  table.append(thead, tbody);
  wrap.append(table);
  section.append(wrap);
  const times = syms.map((s) => `${s} ${when(opts[s].time)}`).join(', ');
  section.append(el('p', 'source', `Source: Yahoo Finance option chains, delayed (${times}). Ratios and strikes: own calculations.`));
  return section;
}

// ---------- Page ----------

function notices(rows) {
  const box = el('div', 'notices');
  const suspect = rows.filter((r) => r.suspect);
  const crossed = rows.filter((r) => r.crossed_sma50 || r.crossed_sma200);
  if (suspect.length) box.append(el('p', 'notice notice-warn', `Check before using: ${suspect.map((r) => r.name).join(', ')}. These failed a sanity check and are marked “check”.`));
  if (crossed.length) {
    const txt = crossed.map((r) => [50, 200].filter((n) => r['crossed_sma' + n]).map((n) => `${r.name} crossed ${r['crossed_sma' + n]} its ${n}-day average`).join('; ')).join('; ');
    box.append(el('p', 'notice notice-accent', `Since the last update: ${txt}.`));
  }
  return box.firstChild ? box : null;
}

async function main() {
  const updated = document.getElementById('updated');
  const tables = document.getElementById('tables');
  let latest;
  try {
    latest = await getJSON('latest.json');
  } catch (e) {
    updated.textContent = 'Data did not load';
    tables.replaceChildren(el('p', 'notice notice-warn', 'The market data could not be loaded. Reload the page; if your login has expired, reloading asks for a new email code.'));
    return;
  }
  updated.textContent = `Updated ${when(latest.run_at)} UK time · ${ago(latest.run_at)}`;
  updated.title = latest.run_at;

  const rows = Object.values(latest.instruments || {});
  const groups = [];
  rows.forEach((r) => {
    let g = groups.find((x) => x.name === r.group);
    if (!g) groups.push((g = { name: r.group, rows: [] }));
    g.rows.push(r);
  });

  const nav = document.getElementById('contents');
  const frag = document.createDocumentFragment();
  const n = notices(rows);
  if (n) frag.append(n);
  let chartNo = 1;
  groups.forEach((g, k) => {
    frag.append(groupTable(g.name, g.rows, k + 1, chartNo));
    chartNo += g.rows.length;
    const a = el('a', null, g.name);
    a.href = '#' + slug(g.name);
    nav.append(a);
  });
  frag.append(optionsTable(latest.options, groups.length + 1));
  const a = el('a', null, 'Options');
  a.href = '#options';
  nav.append(a);
  tables.replaceChildren(frag);
}

main();
