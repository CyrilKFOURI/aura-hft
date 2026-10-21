# Reference Sources: FPGA for Finance & HFT

This folder collects the source code references, exchange specifications and research papers used to design a hardware high-frequency trading or quantitative computing architecture.

---

## Layout of `sources/`

```
sources/
├── README.md                                  # This master catalog
├── 01_github_repositories/                    # Major open-source repositories and architectures
│   ├── corundum_nic.md                        # Modular 100G NIC (Alex Forencich / UCSD)
│   ├── verilog_ethernet.md                    # 10G/25G MAC cores, UDP/IP and AXI-Stream FIFOs
│   ├── nasdaq_itch_sub25ns_parser.md          # Sub-25ns ITCH parser in Verilog (Marc Battyani)
│   ├── itch_order_book_hugobrh.md             # Full ITCH + order book guide (Hugo Brosse)
│   ├── open_nic.md                            # AMD/Xilinx Alveo 100GbE SmartNIC platform
│   ├── vitis_quantitative_finance.md          # Official AMD Vitis Quantitative Finance HLS library
│   └── fipo_fpga_order_book.md                # FIPO and HIMANK729 ITCH processors
│
├── 02_research_papers/                        # Scientific literature and foundational papers
│   ├── execution_and_low_latency.md           # Notes on papers about order books & latency
│   └── quantitative_computation_pricing.md    # Notes on papers about Monte Carlo, Heston and PDEs
│
├── 03_books/                                  # Reference books and engineering manuals
│   ├── hft_and_market_microstructure.md       # Bouchaud (LOB), Cartea (HFT), Ghosh (low-latency C++)
│   └── fpga_design_and_hpc_finance.md         # de Schryver (FPGA finance), Kilts (Advanced FPGA)
│
├── 04_courses_and_labs/                       # University courses, labs and vendor guides
│   ├── columbia_w4840_itch_lab.md             # Columbia University ITCH / LOB design lab
│   ├── imperial_college_custom_computing.md   # Wayne Luk & David Thomas research group
│   ├── hugobrh_itch_systemverilog_series.md   # Step-by-step SystemVerilog + Cocotb tutorial series
│   ├── amd_xilinx_engineering_guides.md       # UG1399 (HLS), UG901 (Synthesis), WP401 (HFT)
│   └── el_karoui_hft_and_local_fpga_docs.md   # HFT course notes mapped to FPGA components
│
└── 05_protocol_specifications/                # Official exchange protocol specifications
    ├── nasdaq_itch_5_0_summary.md             # Binary layout of Add, Executed, Cancel, Delete messages
    ├── nasdaq_moldudp64_summary.md            # Network packet headers and sequence checking
    └── nasdaq_ouch_5_0_summary.md             # Binary layout for outbound order entry
```

The original PDFs (papers and NASDAQ specifications) are not stored in this repository. Each summary links to the public source where one exists.

---

## 1. Key GitHub repositories
* [Corundum 100G NIC](01_github_repositories/corundum_nic.md)
* [Verilog Ethernet & AXI-Stream](01_github_repositories/verilog_ethernet.md)
* [Sub-25ns NASDAQ ITCH Parser](01_github_repositories/nasdaq_itch_sub25ns_parser.md)
* [SystemVerilog ITCH Order Book (Hugo Brosse)](01_github_repositories/itch_order_book_hugobrh.md)
* [AMD OpenNIC](01_github_repositories/open_nic.md)
* [AMD Vitis Quantitative Finance](01_github_repositories/vitis_quantitative_finance.md)
* [FIPO & HIMANK729 Processors](01_github_repositories/fipo_fpga_order_book.md)

---

## 2. Research papers
* **Papers:**
  * FPL 2017: *Exploring the Potential of Reconfigurable Platforms for Order Book Update* (Wayne Luk et al.)
  * FCCM 2020: *Corundum: An Open-Source 100-Gbps NIC* (Alex Forencich et al.)
  * IEEE: *FPGA Acceleration of Monte Carlo Simulation* (David Thomas & Wayne Luk)
* **Summaries:**
  * [Execution & low latency](02_research_papers/execution_and_low_latency.md)
  * [Quantitative computation & pricing](02_research_papers/quantitative_computation_pricing.md)

---

## 3. Reference books
* [Market microstructure & HFT systems (Bouchaud, Cartea, Ghosh)](03_books/hft_and_market_microstructure.md)
* [High-performance FPGA design & numerical finance (de Schryver, Kilts, Vanderbauwhede)](03_books/fpga_design_and_hpc_finance.md)

---

## 4. Courses & learning resources
* [Columbia University CSEE W4840 - Embedded System Design ITCH Lab](04_courses_and_labs/columbia_w4840_itch_lab.md)
* [Imperial College London - Custom Computing Group](04_courses_and_labs/imperial_college_custom_computing.md)
* [Step-by-step SystemVerilog + Cocotb guide (Hugo Brosse)](04_courses_and_labs/hugobrh_itch_systemverilog_series.md)
* [AMD / Xilinx vendor guides (UG1399 HLS, UG901, WP401)](04_courses_and_labs/amd_xilinx_engineering_guides.md)
* [HFT course notes mapped to FPGA components](04_courses_and_labs/el_karoui_hft_and_local_fpga_docs.md)

---

## 5. Official exchange protocol specifications
* **Official documents (public):**
  * NASDAQ TotalView-ITCH 5.0 specification (`NQTVITCHspecification.pdf`)
  * NASDAQ MoldUDP64 1.0 specification (`moldudp64.pdf`)
* **Binary layout summaries:**
  * [ITCH 5.0 (Add, Executed, Cancel, Delete)](05_protocol_specifications/nasdaq_itch_5_0_summary.md)
  * [MoldUDP64 (UDP header & message block framing)](05_protocol_specifications/nasdaq_moldudp64_summary.md)
  * [OUCH 5.0 (outbound order entry format)](05_protocol_specifications/nasdaq_ouch_5_0_summary.md)

---

## 6. Course notes
* **Summary note:** [el_karoui_hft_and_local_fpga_docs.md](04_courses_and_labs/el_karoui_hft_and_local_fpga_docs.md)
* **Master 2 course on econometrics and high-frequency trading (Mathieu Rosenbaum):** lecture slides on order book and queue dynamics (`HFT_slides_seance3.pdf`), summary sheets (`HFT_fiche.pdf`), and 10 real tick datasets in `.h5` format (Amazon, Apple, Total, etc.). These course materials are not distributed with this repository.
* **Books consulted:**
  * *Developing High-Frequency Trading Systems* (Donadio & Ghosh)
  * *High-Frequency Trading* (Gomber et al., E-Finance Lab)
