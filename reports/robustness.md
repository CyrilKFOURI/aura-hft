# Robustness of the reference pipeline

Environment: Docker `aura-hft-ci` (Verilator 5.040, cocotb 2.0.1), image `aura-hft-formal` (= CI + yosys 0.33 on Ubuntu 24.04). Date: 2026-10-21. Everything below was actually run; nothing is extrapolated.

## 1. Fault injection: `sim/tests/test_fault_injection.py` (`itch_lob_pipeline_top`)

Each scenario replays the faulty traffic through the RTL, applies the correct interpretation to the golden model (`sim/golden_model/golden_order_book.py`) and requires RTL top 5 = golden, plus the documented telemetry.

| Scenario | Before fix | After |
| :-- | :-- | :-- |
| Unknown ITCH types (`S`, `R`, `?`) | pass | pass |
| Unknown symbols | pass | pass |
| E/X/D/U on unknown references (6 messages -> 6 `table_miss`) | pass | pass |
| 0-share orders | pass | pass |
| Sequence gap (gap = 6, wait = 11) | pass | pass |
| **MoldUDP64 duplicate** | FAIL: applied twice, bid 1,500,000 at 200 instead of 100 | pass: frame dropped |
| **Truncated frame** | FAIL: pipeline stall (3 ms simulated timeout) | pass |
| **Zero-length block** | FAIL: parser stuck for good | pass |
| ARP / IPv4 with options / TCP frames (new) | (parsed as MoldUDP64) | pass: dropped, sequence intact |
| **Back-to-back burst** (1,800 messages, 48 frames of 38) | FAIL: **741 requests lost** (64-entry FIFO full, no backpressure) | pass: 0 lost; sustained throughput measured at 0.117 msg/cycle = 18.3 M msg/s at 156.25 MHz |

Result: **10/10 pass** (run of 2026-10-21).

### RTL bugs found and fixed

1. **Duplicates re-applied** (`moldudp64_depacketizer.sv`). Scenario: frames seq 1 (2 msgs), seq 3 (2 msgs), then seq 1 retransmitted. Expected: book unchanged. Observed: `duplicate_detected` was raised but the messages were still forwarded to the book (quantities doubled). Fix: the frame is dropped (`drop_frame`), counter `dropped_dup_frames`. A partial overlap also drops the frame; the next frame then raises a gap (detected, not silent).
2. **Parser stuck on a truncated frame or a zero-length block** (`speculative_itch_parser.sv`). The parser ignored `tlast`: the tail of a message stuck to the next frame, and a length of 0 blocked the window forever (`s_axis_tready` at 0). Fix: frame-boundary tracking (`eof_valid/eof_pos`), rejection of an incomplete end of frame, skipping the rest of the frame when the length is 0 or > 62 (`truncated_msg_count`). No cycle added for a clean single-message frame.
3. **Silent request loss** (`lob_engine_top.sv`). The 64-request FIFO silently dropped entries when the (multi-cycle) book was slower than the parser. Fix: `req_almost_full` (64 - 8) -> `book_backpressure` of `ingress_pipeline_top`, which freezes the depacketizer -> parser flow and therefore `s_axis_tready`.
4. **Non-MoldUDP64 frames being parsed** (depacketizer, `STRIP_ETH_IP_UDP=1`). EtherType 0x0800, IHL 5 and protocol 17 are checked; otherwise the frame is dropped without touching the sequence (`dropped_bad_hdr_frames`).
5. **64-bit overflow of the cumulative notional** (`pre_trade_risk.sv`, found by the formal proof, section 4). `acc + notional` could pass 2^64 and wrap back under the limit: 5-cycle yosys counterexample (acc = 2.786·10^18, notional = 1.566·10^19, limit = 2 -> approved, acc = 2). Fix: 65-bit comparison and a saturating accumulator.

The off-limits modules (`order_store.sv`, `depth_book.sv`) were not modified.

### Known gap, not fixed: FCS (`aura_hft_top`)
`sim/tests/test_fcs_top.py` sends a frame with a correct FCS, then one with a corrupted FCS. Expected: `fcs_error_count = 1` and the frame not applied. Observed: `axis_eth_fcs_checker` is instantiated with `CHECK_TRAILING_FCS=0` and without sideband FCS, in cut-through mode: nothing is counted and the frame reaches the book. The fix is non-trivial (a store-and-forward buffer, or relying on the AMD MAC to drop invalid frames) and is left for the board bring-up work. The test is marked `xfail(strict=True)`.

## 2. Real network framing: IEX HIST (`sim/tests/test_iex_framing.py`)

- Source: IEX HIST DEEP 1.0 of 2019-01-30 (same day as the NASDAQ sample), published file 1.30 GB; `data/fetch_iex.py` streams it and keeps the **first 5,000 frames** (262 KB compressed read, never committed).
- Frames: 5,000/5,000 Ethernet II / IPv4 without options / UDP, 0 VLAN, 1 source MAC, multicast 23.226.155.132 -> 233.215.21.4, port 10378, 82 to 1,512 bytes (mean 210.7).
- Method: real headers kept (MAC, EtherType, TOS/ID/flags/TTL/IP addresses, UDP ports; lengths and IP checksum recomputed, UDP checksum set to 0); the IEX-TP payload is replaced by a MoldUDP64 packet of real NASDAQ AAPL messages **filling the original size** (1 to 52 messages per frame).
- Result: **5,000 frames, 23,123 real messages, 0 top-5 divergence** after each frame, 0 gap, 0 rejected frame, 0 truncation, 0 FIFO overflow (`reports/iex_framing_20190130.json`).
- Limitation: the real FCS is not present in the capture (pcap without FCS); the framing variety of a single IEX stream is low (no real VLAN or IP options). The ARP/options/TCP cases are covered by the fault injection.

Regression on real data after the fixes: AAPL co-sim `test_real_data_rtl.py`, **125,232 messages, 0 BBO divergence, 0 top-5 divergence**.

## 3. Coverage

See [coverage_itch_lob.md](coverage_itch_lob.md).

## 4. Formal methods: what was actually done

- **Proof** (`make docker-formal`, `formal/run_risk_formal.sh`): properties P1-P6 of `rtl/assertions/pre_trade_risk_props.sv` on `pre_trade_risk`, all inputs free every cycle, reset on the first cycle. Engine: yosys `sat -tempinduct` (bit-level SAT: BMC from reset + k-induction). **Result: induction proved at k = 3 (unbounded proof).**
- This is **not** SymbiYosys: `sby` is not packaged for Ubuntu 24.04, and `yosys-smtbmc` with the Ubuntu z3/boolector did not finish step 0 in 10 min (boolector crashes during unrolling). PDR (ABC) did not converge in 15 min on the multiplier.
- **Abstraction**: the 32x32 notional product is a cut point (free value); the checker uses the same expression, merged into a single `$mul` cell (checked with `select -assert-count 1`). The properties therefore hold for *any* notional; the DSP arithmetic itself is not proved.
- **Non-vacuity**: 8 mutants (kill switch stage A, stage B, max shares, collar, notional, cumulative, 64-bit cumulative, simultaneous strobes) are all **refuted**.
- **Simulation**: the same checker is bound (`bind`) into `pre_trade_risk` and run with `--assert` under the `tb_risk_and_ouch` and `tb_tick_to_trade_top` benches (`test_risk_assertions.py`): 2/2 pass, no assertion fired.
- P1 applies to `risk_approved`, which directly drives `ouch_order_gen.order_valid`: a kill switch raised in the very cycle the approval comes out does not stop that frame (one-cycle window, documented).
- Not proved: "FIFO never overflows" (the backpressure from section 1 is verified in simulation only).

## 5. Full regression

`PYTHONPATH=. python -m pytest -q sim/tests server/tests -p no:cacheprovider` (Docker): **51 passed, 2 skipped, 1 xfailed** (26 min). Skips: `test_real_data_rtl.py` (without `REAL_STREAM`) and `test_real_data_meatpy.py` (no `.itch` capture in the worktree's `data/cache`). xfail: FCS (section 1). `make lint` (Verilator `-Wall` on the 4 tops + ruff): clean.
