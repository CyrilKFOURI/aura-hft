# AURA-HFT promo v2 — shot list

1080×1350 (4:5), 30 fps, 2,700 frames (90 s), EEVEE. Built by `video/scripts/build_scene_v2.py`.
Voiceover timing: `video/VOICEOVER_v2.md`. Palette carried over from v1: dark PCB, gold traces,
cyan data, amber risk, green "pass". Text overlay is a separate orthographic scene composited on top.

## Geography

Board 16 × 12 units, FPGA package at the origin, SFP+ cages on the left (IN at y = +2, OUT at y = −2).
Inside the die (3.7 × 3.7, top at z ≈ 0.33) the eight pipeline blocks sit on a serpentine
over a carpet of dim CLB tiles with BRAM/DSP columns:

```
 y=+1.1   ING ──▶ MOLD ──▶ PARSE ──▶ ORDER STORE
                                         │
 y=−0.7   OUT ◀── RISK ◀── SIGNAL ◀── DEPTH BOOK
```

## Shots

| Shot | Frames | Time (s) | Camera | Action | Overlay |
|:--|:--|:--|:--|:--|:--|
| S1 Hook | 1–180 | 0–6 | Macro, low over a gold trace, 45 mm f/1.6, slow truck right | A lone cyan pulse races along a trace in the dark; board lights come up at the end | "Markets move in / nanoseconds." |
| S2 Board | 181–480 | 6–16 | Crane up to a ¾ aerial, then slow orbit around the board, 40 mm f/9 | Gold traces draw themselves; key/rim lights fade in | "AURA-HFT · Tick-to-trade pipeline on FPGA" |
| S3 Dive | 481–630 | 16–21 | Low dolly chasing the packet from SFP IN along the trace, rise over the package, plunge straight down through the glass lid | Packet enters SFP IN, rides the trace, glass lid fades, die grid lights up | "01 · MARKET DATA IN" |
| S4 Ingress | 631–840 | 21–28 | Three-quarter close-up from the front-left, slow push-in | Four SerDes lanes with coil serializers feed a MAC block; packet passes the FCS gate arch, which flashes green | "02 · INGRESS — SerDes · MAC · CRC-32 check" |
| S5 MoldUDP64 | 841–1020 | 28–34 | Overhead tilt, slow rotate around the ring | Sequence ring of 16 slots advances one slot; PTP dial hand sweeps; message drops out of the hub | "03 · MOLDUDP64 — sequence · timestamp · unpack" |
| S6 Parser | 1021–1215 | 34–40.5 | Side tracking shot along the decoder lanes | Input bus fans out into six lanes of different widths (type, ref, side, shares, stock, price); field slugs slide into registers | "04 · ITCH PARSER — parallel field decode" |
| S7 Order store | 1216–1485 | 40.5–49.5 | Crane from low between the banks up to a ¾ view | Two BRAM banks (sets × 4 ways tiles); hash probe lights one set in each bank (two choices), one way turns green; stash tiles pulse | "05 · ORDER STORE — 2 banks × 4 ways + stash" |
| S8 Depth book | 1486–1725 | 49.5–57.5 | Long lateral slide along the price array, then tilt up to the bitmap tree | Price-indexed bid/ask slot rows; 3-level occupancy tree lights top-down; five best levels rise out of the extractor | "06 · DEPTH BOOK — one slot per tick · top-5" |
| S9 Signal | 1726–1965 | 57.5–65.5 | Low hero angle on the DSP column, slow arc | Four DSP48 tiles (pre-adder / multiplier / ALU sub-blocks) fire as a cascade into a comparator wedge | "07 · SIGNAL — order-book imbalance · no divider" |
| S10 Risk | 1966–2145 | 65.5–71.5 | Straight-on axial view down the gate, push through | Stage 1 amber multiplier block, stage 2 row of comparator arches turn amber → green as the order passes | "08 · PRE-TRADE RISK — notional · limits" |
| S11 Egress | 2146–2295 | 71.5–76.5 | Chase shot behind the packet, rising out of the die | Header slabs stack into an OUCH frame, serializer streams it to SFP OUT, cage mouth flares | "09 · OUCH OUT — order on the wire" + "ORDER SENT" |
| S12 End | 2296–2700 | 76.5–90 | Pull-back up and out to a top-down of the whole board, end plate darkens | Pipeline stays lit; cycle bar full | `27 CYCLES` · `172.8 ns` · facts card · AURA-HFT |

Bottom of frame, S4–S11: a 27-segment progress bar fills as the packet advances (a progress
indicator, not a per-stage cycle breakdown, which CLAIMS does not provide).

## Honesty rules applied

- Only numbers from CLAIMS / reports: 27 cycles, 172.8 ns, 156.25 MHz, 215,674 messages, 0 divergence.
- "cycle-accurate simulation" is shown wherever the latency appears. No "measured on silicon".
- No CDC chapter: the reference top is single-clock (dual-clock variant is 🧪 in CLAIMS).
