"""Single source of truth for the latency figures shown by the dashboard.

- FPGA: *simulated* clock cycles (Verilator), never a silicon measurement.
- CPU: *measured* software reference path (software/ref_pipeline), read from
  the JSON files written by `aura_ref bench` in reports/software_latency/.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
SOFTWARE_LATENCY_DIR = REPO_ROOT / "reports" / "software_latency"

# docs/CLAIMS.md C1 (step P5a): tick-to-trade of aura_hft_top, measured in
# simulation by sim/tests/tb_tick_to_trade_top.py on the synthetic scenario.
FPGA_SIM_CYCLES = 29
FPGA_CLOCK_MHZ = 156.25

NASDAQ_SOURCE = {
    "kind": "file",
    "name": "NASDAQ TotalView-ITCH 5.0 sample",
    "date": "2019-01-30",
    "file": "01302019.NASDAQ_ITCH50 (first 20,000,000 messages)",
}


def fpga_simulated() -> dict[str, Any]:
    return {
        "kind": "simulated",
        "cycles": FPGA_SIM_CYCLES,
        "clock_mhz": FPGA_CLOCK_MHZ,
        "ns": round(FPGA_SIM_CYCLES * 1000.0 / FPGA_CLOCK_MHZ, 1),
        "scope": "aura_hft_top, AXI-Stream ingress to OUCH egress, Verilator, synthetic scenario",
        "source": "docs/CLAIMS.md C1 (P5a), sim/tests/tb_tick_to_trade_top.py",
    }


def software_measured(directory: Path = SOFTWARE_LATENCY_DIR) -> list[dict[str, Any]]:
    """Every `aura_ref bench` result found on disk (empty list when none)."""
    out: list[dict[str, Any]] = []
    if not directory.is_dir():
        return out
    for path in sorted(directory.glob("*.json")):
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        lat = data.get("latency_ns", {})
        out.append({
            "kind": "measured",
            "symbol": data.get("symbol"),
            "events": data.get("events"),
            "messages": data.get("messages"),
            "p50_ns": lat.get("p50"),
            "p99_ns": lat.get("p99"),
            "p999_ns": lat.get("p999"),
            "mean_ns": lat.get("mean"),
            "max_ns": lat.get("max"),
            "throughput_msgs_per_s": data.get("throughput_msgs_per_s"),
            "timer_overhead_ns": data.get("timer_overhead_ns"),
            "cpu": data.get("cpu", "Intel Core Ultra 7 155H (laptop)"),
            "histogram": data.get("histogram", []),
            "data_source": NASDAQ_SOURCE,
            "source": f"reports/software_latency/{path.name}",
        })
    return out


def latency_summary(directory: Path = SOFTWARE_LATENCY_DIR) -> dict[str, Any]:
    return {"fpga": fpga_simulated(), "software": software_measured(directory)}
