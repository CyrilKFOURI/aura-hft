# Resource estimate — `lob_engine_top`

> **Yosys estimate, no timing, not Vivado.** Yosys 0.33 `synth_xilinx -family xcup`
> after sv2v v0.0.13 conversion. Yosys' packing, LUT mapping and memory
> inference differ from Vivado; treat these numbers as an order of magnitude.
> Vivado synthesis + place & route (timing, real utilisation) has not been run yet.

Reproduce: `sh scripts/yosys_estimate.sh lob_engine_top` (runs in a throwaway
`aura-hft-ci` container; nothing installed on the host). Raw statistics:
[`yosys_lob_engine_top_stat.txt`](yosys_lob_engine_top_stat.txt).
Deviation from stock `synth_xilinx`: the SAT-based `share` pass is skipped
(it ran out of memory with 15 GB available); `-noiopad` (not a chip top).

## Memory inference

| Memory | Size | Inferred as |
| :--- | :--- | :--- |
| `depth_book.shares_mem` | 2 × 65 536 × 32 bit (4 Mb) | Block RAM (`$__XILINX_BLOCKRAM_TDP_`) |
| `order_store.bank0` | 8 192 × 552 bit (4.5 Mb) | Block RAM |
| `order_store.bank1` | 8 192 × 552 bit (4.5 Mb) | Block RAM |
| `depth_book.l0` | 2 × 2 048 × 32 bit (128 Kb) | LUTRAM (async read, replicated per read port) |

All three large memories now map to block RAM (they used to be read
combinationally and could not be inferred).

## Totals (Yosys)

| Resource | Yosys count | KR260 / K26 (`xck26`) available |
| :--- | ---: | ---: |
| LUT (logic, LUT1–LUT6) | 47 760 | 117 120 |
| LUTRAM (`RAM64M8` × 8 LUT) | 2 048 cells = 16 384 LUT | (part of the LUT budget) |
| FF (`FDRE` + `FDCE` + `FDPE`) | 20 788 | 234 240 |
| RAMB36E2 | **376** | **144** |
| URAM288 | 0 | 64 |
| DSP48E2 | 35 | 1 248 |
| CARRY4 / MUXF7 / F8 / F9 | 536 / 7 743 / 2 773 / 815 | — |

## Reading

- **Does not fit as-is in block RAM**: 376 RAMB36 (≈ 13 Mb) vs 144 on the K26.
  The two order-store banks (9 Mb) and the share array (4 Mb) must go to
  **UltraRAM** (64 × 288 Kb = 18 Mb on the K26); Yosys 0.33 chose BRAM.
  Next step: `ram_style = "ultra"` on these arrays and check in Vivado,
  or shrink the entry (e.g. 64-bit reference → narrower tag) if URAM is short.
- The L0 bitmap as LUTRAM costs ~16 K LUTs because each async read port
  (`find_le` / `find_ge` / apply) replicates it; a registered L0 read would
  remove that at the cost of scan cycles.
- 35 DSPs: hash multipliers (64 × 64, two banks) and the price reciprocal multiply.
- No timing information: Fmax / WNS remain unknown until a Vivado run.
