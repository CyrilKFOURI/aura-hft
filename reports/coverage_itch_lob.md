# Verilator coverage: `itch_lob_pipeline_top` under the fault-injection bench

- Run: `make coverage` (Docker `aura-hft-ci`, Verilator 5.040, `--coverage-line --coverage-toggle`), 2026-10-21.
- Stimulus: the 10 scenarios of `sim/tests/test_fault_injection.py` (one process per scenario, `.dat` files merged with `verilator_coverage --write`). **Not** the real-data co-simulations (not instrumented).
- Overall `verilator_coverage`: **57.0 %** (647/1,125 points). Detail (`python -m sim.validation.coverage_summary`):

| File | line | branch | toggle |
| :-- | --: | --: | --: |
| `depth_book.sv` | 92.1 % (35/38) | 64.6 % (53/82) | 16.2 % (150/926) |
| `ingress_pipeline_top.sv` | — | — | 29.8 % (635/2130) |
| `itch_lob_pipeline_top.sv` | — | — | 36.6 % (1015/2776) |
| `itch_pkg.sv` | 0.0 % (0/4) | — | — |
| `lob_engine_top.sv` | 87.5 % (7/8) | 85.0 % (17/20) | 32.3 % (1055/3268) |
| `moldudp64_depacketizer.sv` | 34.3 % (12/35) | 51.5 % (34/66) | 34.0 % (557/1636) |
| `order_store.sv` | 54.3 % (25/46) | 73.7 % (28/38) | 15.5 % (189/1220) |
| `speculative_itch_parser.sv` | 61.8 % (21/34) | 61.5 % (32/52) | 49.2 % (354/720) |
| `top_of_book_cache.sv` | 100.0 % (3/3) | 90.9 % (20/22) | 38.0 % (742/1952) |
| **Total** | **61.3 %** (103/168) | **65.7 %** (184/280) | **32.1 %** (4697/14628) |

## Honest reading

**Far from the 90 % target.** What is missing and matters:

- **Parser**: `F` (Add with MPID) and `C` (Executed with price) messages are never sent by this bench; the `skip_frame` mode (length 0 or > 62 *in the middle* of a frame) is not exercised, only the end-of-frame case is.
- **Depacketizer**: the `STRIP_ETH_IP_UDP=0` branch is never instantiated in the reference top (dead code for this top); one-word frames or frames with < 2 payload bytes in the last word are untested; `keep_to_len` / `len_to_keep` outside contiguous values (non-contiguous tkeep is never sent).
- **Book** (`order_store.sv`, `depth_book.sv`, out of scope for this batch): the two-choice hash stash, full table, out-of-window prices and `U` (replace) are lightly covered here; they are partly covered by the real-data co-simulation (not instrumented).
- **Toggle 32 %**: expected to be low with directed stimuli (64-bit buses, FIFO memory); not a goal in itself.

Next: instrument `tb_order_book` too, a prefix of the real-data co-simulation and a constrained-random bench, then aim for 90 % line/branch on ingress + parser.
