# Golden model vs MeatPy — real NASDAQ ITCH 5.0 (01/30/2019, first 20M messages)

- Data: `https://emi.nasdaq.com/ITCH/Nasdaq%20ITCH/01302019.NASDAQ_ITCH50.gz` (stream-prefix), SHA-256 `e24c84422e4b891bab714e89f935a82078f2bdf9e4f59cc023097bbcedee7ddb`
- Messages replayed: **20,000,000** in 47.2 min
- Reference: MeatPy 0.5.0 `ITCH50MarketProcessor` (independent implementation)
- Checks: BBO after every message touching the symbol; full 5-level depth on both sides every 100,000 messages
- Run: one process per symbol (`make validate-real` runs them sequentially)
- **Result: 0 divergence across 6 symbols**

| Symbol | BBO checks | BBO mismatches | Depth checks | Depth mismatches | Out-of-priority executions* | Final BBO (raw price ×10⁴, shares) |
| :-- | --: | --: | --: | --: | --: | :-- |
| AAPL | 125,232 | 0 | 200 | 0 | 15 | bid [(1622700, 100)] / ask [(1622900, 100)] |
| MSFT | 58,888 | 0 | 200 | 0 | 5 | bid [(1048600, 100)] / ask [(1048800, 200)] |
| NVDA | 46,314 | 0 | 200 | 0 | 6 | bid [(1346100, 102)] / ask [(1347900, 100)] |
| QQQ | 210,287 | 0 | 200 | 0 | 0 | bid [(1637500, 200)] / ask [(1637600, 1303)] |
| SAP | 314,351 | 0 | 200 | 0 | 0 | bid [(1020000, 259)] / ask [(1020500, 500)] |
| TSLA | 31,554 | 0 | 200 | 0 | 11 | bid [(3002000, 200)] / ask [(3005100, 400)] |

\* Executions MeatPy flags as not first in time priority (around the 09:30 opening cross). MeatPy still applies them; reported for transparency, not counted as divergences.

Sanity check of the comparison itself: deliberately disabling partial-cancel (`X`) handling in the golden model produces 10,081 BBO divergences on QQQ within the first 2M messages.
