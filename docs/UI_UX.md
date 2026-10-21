# UI / UX — AURA-HFT

This document defines the style, ergonomics and visual guidelines for the AURA-HFT supervision interface.

---

## General style

* **Look and feel:** Dense, technical and highly legible, inspired by institutional trading workstations (**Bloomberg Terminal**, **Refinitiv Eikon**) and hardware observability tools.
* **Theme:** **Dark mode only** (dark background to reduce eye strain during long analysis sessions).
* **Information density:** High (compact layout, thin 1px borders, no wasted space, numeric data emphasized).
* **Animations:** Minimal and targeted: only order book changes (a brief green/red flash on a trade or BBO change) and the OUCH order trigger pulse get a micro-animation.

---

## Colors

The palette is tuned for contrast, financial clarity and ergonomics:

| Role | Hex | Usage |
| :--- | :--- | :--- |
| **Main background** | `#0B0E14` (deep slate black) | Application background |
| **Panel background** | `#151922` (bluish anthracite grey) | Cards, containers and frames |
| **Borders / separators**| `#262C3A` | Thin 1px separators |
| **Primary text** | `#E6EDF3` (high-legibility off-white) | Numeric data, prices, active labels |
| **Secondary text** | `#8B949E` (neutral grey) | Metadata, units, timestamps |
| **Bid (buy) / positive** | `#00D084` (financial neon green) | Book bid column, positive OBI, buyer trades |
| **Ask (sell) / negative** | `#FF4D4D` (bright red) | Book ask column, negative OBI, seller trades |
| **Accent / hardware** | `#3B82F6` (cobalt blue) | FPGA metrics, clock cycles, primary buttons |
| **Risk alert / kill** | `#F59E0B` (amber) / `#EF4444` (blood red) | Pre-trade risk rejections, kill switch indicator |

---

## Typography

* **Data font:** `JetBrains Mono`, `Fira Code` or `Roboto Mono` (tabular figures `tnum` required so numbers do not jump on refresh).
* **UI font:** `Inter` or the system sans-serif (`-apple-system, BlinkMacSystemFont, "Segoe UI"`).
* **Type scale:**
  * Section titles: $14\text{px}$, uppercase, wide tracking, bold.
  * BBO price & spread: $24\text{px}$ to $28\text{px}$, mono, semi-bold.
  * Order book levels: $12\text{px}$, mono, regular.
  * Telemetry & logs: $11\text{px}$, mono.

---

## Key components

### 1. The Dual-Sided Price Ladder (L2 order book)
* Two symmetric columns: Bid (buy) on the left in green, Ask (sell) on the right in red.
* Horizontal background bars proportional to the volume available at each price level (*depth bars*).
* Central middle line showing the **instantaneous spread** and the **micro-price computed in hardware**.

### 2. OBI Oscilloscope & Signal Gauge
* Real-time chart of the book imbalance:
  $$OBI \in [-1.0, +1.0]$$
* The entry threshold is drawn as two dashed lines (e.g. $+0.6$ and $-0.6$).
* An instant marker each time a tick crosses the line and triggers the RTL pulse.

### 3. Queue Depletion Gauge (queue tracker)
* Progress bar representing the tested virtual order.
* Volume of orders ahead of us (in shares).
* Instant visual decrement on every cancel (`'X'`) or execution (`'E'`) message.

### 4. Trade & Risk Blotter
* Chronological table of the orders emitted by the FPGA.
* Columns: `Timestamp (ns)`, `Type`, `Symbol`, `Price`, `Shares`, `Latency (cycles / ns)`, `Status (EXECUTED / REJECTED)`, `Risk reason`.

### 5. Latency Distribution Panel
* Interactive histogram of the FPGA core reaction times ($T_{\text{tick-to-trade}}$).
* Statistics shown: $p_{50}$, $p_{90}$, $p_{99}$ and maximum jitter.

---

## Visual references

* **Inspiration:** Institutional trading terminal interfaces (Bookmap, CQG Desktop, TradingView Pro).
* **Display philosophy:** No decoration; focus on numeric accuracy, deterministic latency and verifiable RTL behavior.
