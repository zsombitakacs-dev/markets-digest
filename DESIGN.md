---
name: Markets Digest
description: A private markets dashboard that reads like a central bank's statistical report.
colors:
  report-paper: "#ffffff"
  table-band: "#f3f5f8"
  navy-ink: "#1b2f4e"
  body-text: "#1d2430"
  muted-text: "#586273"
  hairline: "#d9dee6"
  ochre: "#a65f00"
  ochre-ink: "#7f4a00"
  ochre-wash: "#fbf1e2"
  average-grey: "#7c8696"
  rise-green: "#17773a"
  fall-red: "#b8322a"
  warn-ink: "#7a4300"
  warn-wash: "#fff3d6"
  focus-blue: "#2f6fd6"
typography:
  wordmark:
    fontFamily: "-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica Neue, Arial, sans-serif"
    fontSize: "20px"
    fontWeight: 700
    lineHeight: 1.3
    letterSpacing: "-0.01em"
  table-title:
    fontFamily: "-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica Neue, Arial, sans-serif"
    fontSize: "18px"
    fontWeight: 650
    lineHeight: 1.3
  body:
    fontFamily: "-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica Neue, Arial, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.5
  table:
    fontFamily: "-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica Neue, Arial, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica Neue, Arial, sans-serif"
    fontSize: "12.5px"
    fontWeight: 600
    lineHeight: 1.4
rounded:
  tag: "3px"
  panel: "4px"
spacing:
  cell: "8px 10px"
  gutter: "16px"
  section: "40px"
components:
  explain-switch-on:
    backgroundColor: "{colors.navy-ink}"
    height: "20px"
    width: "36px"
  explain-note:
    backgroundColor: "{colors.table-band}"
    textColor: "{colors.muted-text}"
    rounded: "{rounded.panel}"
    padding: "10px 12px"
  tag-warn:
    backgroundColor: "{colors.warn-wash}"
    textColor: "{colors.warn-ink}"
    rounded: "{rounded.tag}"
    padding: "0 6px"
  tag-accent:
    backgroundColor: "{colors.ochre-wash}"
    textColor: "{colors.ochre-ink}"
    rounded: "{rounded.tag}"
    padding: "0 6px"
---

# Design System: Markets Digest

## Overview

The dashboard reads like a central bank's Inflation Report on screen: white report paper, navy ink, and statistical tables that are numbered ("Table 4", "Chart 9") and cited ("Source: …") so any figure can be quoted and trusted. It is an Operate surface for about five student readers on phones and laptops: calm, dense, and self-explaining, with an "Explain terms" switch that shows plain-English notes under every section and indicator. It refuses the dark trading terminal and the card-grid fintech app.

## Colors

### Primary
- **Navy ink** (`#1b2f4e`): headings, instrument names, table rules (2px top and bottom, 1px under the header), the price line on charts, the switch when on.

### Secondary
- **Ochre** (`#a65f00`): the 50-day average line only; its darker **ochre ink** on **ochre wash** marks "crossed" tags and crossing notices.

### Neutral
- **Report paper** `#ffffff`, **table band** `#f3f5f8` (hover, open rows, explanation panels), **hairline** `#d9dee6` (row separators, chart grid), **muted text** `#586273` (labels, sources, explanations, 6:1 on paper), **average grey** `#7c8696` (the dashed 200-day line).
- Dark mode redefines every token (paper `#10151d`, ink `#c3d3ee`, ochre `#e0a24a`) under `prefers-color-scheme: dark` and `[data-theme="dark"]`.

### Named Rules
**The Never-Colour-Alone Rule.** Up and down are green `#17773a` and red `#b8322a` and always carry ▲ or ▼ plus a screen-reader word. Market state is a dot whose form carries meaning: filled = open, half = pre-market or after-hours, hollow = closed.
**The Flags-Are-Amber Rule.** Only data problems (suspect values, failed loads) use warn ink on warn wash.

## Typography

One system sans for everything, with tabular figures on the whole page so numbers align in columns.

### Hierarchy
- **Wordmark** 20px / 700, navy.
- **Table title** 18px / 650, navy, preceded by the table number at 13px / 600 muted ("Table 1").
- **Body** 15px / 1.5. **Tables** 14px. **Labels and sources** 12.5px.
- **Explanations** 13.5px muted, max 72ch.

## Layout

A single 1080px column with a 16px side gutter. Each group is a section 40px below the last: table number and title, explanation panel, full-width table, source line. Rows open in place into a detail panel (chart full width, then indicators in an auto-fill grid of 230px+ columns). Under 720px the "vs 50-day", "vs 200-day" and range columns hide (the detail panel still has them), and the contents strip becomes one swipeable line.

## Elevation & Depth

Flat. Depth comes from rules and the table band, never from shadows. The only shadow is the switch thumb's 1px lift.

## Shapes

Square tables; 4px radius on explanation panels and notices; 3px on tags; pill only for the switch track.

## Components

### Navigation
The contents strip: group names as quiet muted links that turn navy and underline on hover.

### Explain switch
A real `role="switch"` button with its label beside it; track navy when on. The choice is saved per browser.

### Statistical table (signature component)
Report-style rules (2px navy top and bottom, 1px navy under the header, hairlines between rows), right-aligned numbers, the instrument name as a button with a leading chevron and the market state beneath it, a 120px 52-week range track with a navy marker, and a "Source:" line under every table. Missing values span the row with an "unavailable" tag and the reason.

### Chart
uPlot, 200–260px tall: navy close, ochre 50-day, grey dashed 200-day, with a legend of line samples and a source line. Numbered "Chart N" with a descriptive caption.

## Do's and Don'ts

### Do:
- Number every table and chart, and put a source line under each.
- Show each value's own time and market state.
- Say why a value is missing; never fill it.

### Don't:
- Use colour as the only signal for direction or state.
- Add cards, shadows or gradients: rules and the band carry the structure.
- Use the ochre for anything except the 50-day average and crossings.
