# OBI backtest

Backtest of the trading rule **as wired in the RTL**
(`rtl/quant/obi_signal.sv`, `rtl/risk/risk_ouch_top.sv`, `rtl/risk/pre_trade_risk.sv`)
on real NASDAQ ITCH 5.0 data, after costs. Methodology and results:
[`../obi_backtest.md`](../obi_backtest.md).

## Run

```bash
python data/fetch.py --messages 60000000      # ~750 MB read, ~1.9 GB written to data/cache/ (gitignored)
python -m research.obi_backtest               # picks the largest 01302019 file in data/cache/
python -m pytest research                     # unit tests of the fill model and the costs
```

Options: `--itch FILE`, `--symbols AAPL MSFT ...`, `--re-extract`.

## Files

| File | Role |
| :-- | :-- |
| `extract.py` | One pass over the ITCH file, rebuilds the books with `GoldenOrderBook` (validated at 0 divergence vs MeatPy), exports one event array per symbol (`data/cache/*.obi_events.<SYM>.npz`). |
| `model.py` | Exact Q1.31 OBI rule, risk checks, passive fill model (price-time priority), costs. |
| `backtest.py` | Strategy loop, mid-to-mid upper bound, literal RTL behaviour, statistics (drawdown, block bootstrap). |
| `__main__.py` | Threshold × horizon × latency grid, writes `results/results.json` and `results/results.md`. |
| `test_fill_costs.py` | Hand-written scenarios: queue position, partial fills, trade-through, costs, Q1.31 rule, risk, absence of look-ahead. |

NASDAQ data is never committed; only the aggregates (`results/`) are.
