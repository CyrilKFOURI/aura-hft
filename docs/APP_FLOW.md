# APP FLOW — AURA-HFT

This document describes the screen layout, user interactions and navigation flow of the AURA-HFT web supervision application.

---

## Screens

The application is a dense, responsive single-page application (SPA) modelled on professional financial terminals. It has three main views:

| Screen | Role |
| :--- | :--- |
| **1. Run Launcher & Config (`/launch`)** | Configures the simulation parameters (ITCH feed file, ticker symbol, risk limits, OBI threshold, kill switch) and starts the Verilator run. |
| **2. Live Replay Terminal (`/replay/:run_id`)** | Main visualization screen: step-by-step or accelerated replay of a recorded run. Shows the L2 order book, live price, OBI signal, queue gauge, generated orders and latency metrics in nanoseconds. |
| **3. Benchmark & Analytics (`/analytics/:run_id`)** | Post-run statistics: detailed latency distribution (p50, p90, p99, max histogram), golden-model conformance report (divergences = 0) and a summary of risk checks. |

---

## Main flow

The nominal user flow (operator or reviewer):

```
   [1. Launcher screen]
           │
           │  1. Select the dataset (e.g. NASDAQ AAPL capture)
           │  2. Adjust risk limits & OBI threshold
           │  3. Click "Launch Hardware Simulation"
           ▼
   [Verilator run in the background]
           │
           │  - Progress shown (progress bar + logs)
           │  - Cycle-by-cycle telemetry file generated
           ▼
   [2. Replay Terminal (/replay/:id)]
           │
           │  - Replay controls: Play / Pause / Fast-forward (1x, 5x, 20x) / Time scrub
           │  - Live observation:
           │     * Animated L2 order book (book depth)
           │     * OBI signal and micro-price oscillations
           │     * Queue depletion for the tested virtual order
           │     * Instant OUCH order trigger on the blotter
           ▼
   [3. Analytics & Performance screen]
           │
           │  - Review the hardware latency distribution
           │  - Check the integrity report (100% match with the golden model)
           │  - Export the summary as PDF / Markdown
```

---

## Secondary flows

### Flow 2A: Hardware kill switch test
1. On the configuration screen, the user sets `Hard Kill Switch = ENABLED`.
2. The simulation run is launched.
3. On the Replay screen, the safety status shows a red banner: `KILL SWITCH ACTIVE: HARDWARE EMISSION LOCKED`.
4. When the OBI signal crosses the trigger threshold, the order is intercepted immediately and displayed with the status `REJECTED: RISK_KILL_SWITCH`.

### Flow 2B: Pre-trade risk rejection test (fat finger / price collar)
1. The user configures a deliberately restrictive risk rule (e.g. `Max Order Shares = 100`).
2. The algorithm computes an opportunity requiring 500 shares.
3. In the replay terminal, the trade blotter records the rejection in real time with the hardware reason `REJECTED: MAX_SHARES_EXCEEDED`, in 1 clock cycle.

### Flow 2C: Tick-by-tick inspection
1. The user pauses the replay at a moment of extreme volatility or a tight spread.
2. Using the arrow keys or the slider, the user steps **tick by tick**.
3. The exact transition is visible: incoming ITCH message $\to$ BBO update $\to$ OBI computation $\to$ OUCH emission.
