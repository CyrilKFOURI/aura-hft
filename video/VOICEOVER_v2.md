# AURA-HFT promo v2 — English voiceover

Voice: Windows SAPI `Microsoft Zira Desktop` (en-US), rate 1, generated offline by
`video/scripts/make_voice.ps1` (one WAV per line, placed at the start time below).

Every number comes from `docs/CLAIMS.md` / `reports/` on `feat/p4-obi-notional-top`:
27 cycles is the tick-to-trade latency of the synthetic scenario in cycle-accurate
simulation (C1, 🟡; division-free OBI + 2-stage risk, commit 6bc0c36), 156.25 MHz is the reference clock, 215,674 real messages / 0 divergence
is the P4 real-data co-simulation. Nothing is presented as measured on silicon.

The reference top (`rtl/top/aura_hft_top.sv`) is single-clock, so the v1 "CDC" chapter is
replaced by the MoldUDP64 unpacking stage that the reference pipeline actually contains.

| # | Start (s) | Shot | Line |
|:--|--:|:--|:--|
| 01 | 0.8 | S1 Hook | Markets move in nanoseconds. |
| 02 | 3.4 | S1 Hook | This is AURA-HFT: tick-to-trade, built in hardware. |
| 03 | 8.0 | S2 Board | On an AMD Kria FPGA: market data in on ten-gigabit Ethernet, orders out. No CPU in the loop. |
| 04 | 16.0 | S3 Dive | Let's follow one NASDAQ message, into the silicon. |
| 05 | 21.0 | S4 Ingress | Ingress. Serial lanes become sixty-four-bit words, and every frame's checksum is verified. |
| 06 | 28.8 | S5 Unpack | MoldUDP64: sequence checked, time-stamped, unpacked. |
| 07 | 34.8 | S6 Parser | The ITCH parser splits each message into fields, in parallel lanes. |
| 08 | 41.0 | S7 Order store | Orders live in a hash table in block RAM: two banks, four ways, a small stash. Constant-time lookups. |
| 09 | 50.0 | S8 Depth book | The depth book: one slot per price tick. A three-level bitmap finds the top five levels on every update. |
| 10 | 58.0 | S9 Signal | The signal: order-book imbalance, on DSP slices. Multiply, compare, no divider. |
| 11 | 66.0 | S10 Risk | Pre-trade risk. Multiply price by size, then compare against every limit. |
| 12 | 72.2 | S11 Egress | The OUCH encoder streams the order back onto the wire. |
| 13 | 78.0 | S12 End | Twenty-seven clock cycles: about 173 nanoseconds, tick to trade, in cycle-accurate simulation. |
| 14 | 85.4 | S12 End | And the order book matches real NASDAQ data, message for message. |

On-screen end card: `27 CYCLES` · `172.8 ns` · `cycle-accurate simulation · 156.25 MHz` ·
`0 divergence · 215,674 real NASDAQ ITCH messages (AAPL · MSFT · TSLA, 01/30/2019)`.

If CLAIMS changes the cycle count, edit `CYCLES` in `video/scripts/build_scene_v2.py`,
line 13 here, and re-run `make_voice.ps1` + the build.
