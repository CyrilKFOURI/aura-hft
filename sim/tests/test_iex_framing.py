"""Real IEX Ethernet/IPv4/UDP framing around real NASDAQ ITCH (skipped when data is absent).

Prepare: python data/fetch_iex.py --packets 5000
         python data/fetch.py && python -m sim.validation.extract_symbol_stream <capture> --symbol AAPL
Run:     pytest sim/tests/test_iex_framing.py   (IEX_FRAMES=N to shorten)
"""

import os

import pytest
from cocotb_test.simulator import run

from sim.tests.rtl_sources import ITCH_LOB_SOURCES, REPO

CACHE = REPO / "data" / "cache"
PCAPS = sorted(CACHE.glob("iex_*.pcap"))
STREAMS = sorted(CACHE.glob("*.AAPL.stream.json"))

pytestmark = pytest.mark.skipif(not PCAPS or not STREAMS,
                                reason="needs data/cache/iex_*.pcap (data/fetch_iex.py) and an AAPL stream")


def test_iex_framing_with_real_itch():
    pcap, stream = PCAPS[0], STREAMS[0]
    date = pcap.name.split("_")[1]
    run(
        verilog_sources=ITCH_LOB_SOURCES,
        toplevel="itch_lob_pipeline_top",
        module="sim.tests.tb_iex_framing",
        simulator="verilator",
        includes=[str(REPO / "rtl" / "include")],
        compile_args=["-Wall", "-Wno-DECLFILENAME", "-Wno-UNUSED", "-O3"],
        sim_build=str(REPO / "sim" / "build" / "iex_framing"),
        extra_env={"PYTHONPATH": str(REPO), "IEX_PCAP": str(pcap), "REAL_STREAM": str(stream),
                   "IEX_FRAMES": os.environ.get("IEX_FRAMES", ""),
                   "IEX_REPORT": str(REPO / "reports" / f"iex_framing_{date}.json")},
    )
