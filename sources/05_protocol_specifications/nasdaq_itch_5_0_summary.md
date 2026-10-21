# Technical Specification: NASDAQ TotalView-ITCH 5.0 Protocol

## 1. Overview
* **Official document:** NASDAQ TotalView-ITCH 5.0 specification (`NQTVITCHspecification.pdf`, public, not included in this repository)
* **Data format:** Pure binary, big-endian (network byte order).
* **Price representation:** Unsigned 32-bit integers with an implicit 4 decimal places (e.g. $150.25 \$ \rightarrow 1502500$).
* **Order identifier:** Unsigned 64-bit integer (`Order Reference Number`).

---

## 2. Binary structure of the key messages to decode in hardware

### A. Message type `'A'`: Add Order (displayed order, no MPID attribution) - Length: 36 bytes
| Offset (byte) | Field | Size (bytes) | Type | Description |
| :--- | :--- | :--- | :--- | :--- |
| 0 | `Message Type` | 1 | Alpha (`'A'`) | Add Order message identifier |
| 1 | `Stock Locate` | 2 | Integer | Internal numeric identifier of the stock symbol |
| 3 | `Tracking Number` | 2 | Integer | Internal Nasdaq tracking number |
| 5 | `Timestamp` | 6 | Integer | Timestamp in nanoseconds since midnight |
| 11 | `Order Reference Number` | 8 | Integer | Unique 64-bit order identifier |
| 19 | `Buy/Sell Indicator` | 1 | Alpha | `'B'` = Buy (Bid), `'S'` = Sell (Ask) |
| 20 | `Shares` | 4 | Integer | Number of shares (volume) |
| 24 | `Stock` | 8 | Alpha | Ticker symbol (e.g. "AAPL    "), space padded |
| 32 | `Price` | 4 | Integer | Fixed-point price (4 decimals) |

### B. Message type `'E'`: Order Executed (partial or full execution) - Length: 31 bytes
| Offset (byte) | Field | Size (bytes) | Type | Description |
| :--- | :--- | :--- | :--- | :--- |
| 0 | `Message Type` | 1 | Alpha (`'E'`) | Order Executed message identifier |
| 1 | `Stock Locate` | 2 | Integer | Stock identifier |
| 3 | `Tracking Number` | 2 | Integer | Nasdaq tracking |
| 5 | `Timestamp` | 6 | Integer | Timestamp in nanoseconds |
| 11 | `Order Reference Number` | 8 | Integer | Reference of the executed order |
| 19 | `Executed Shares` | 4 | Integer | Number of executed shares to deduct from the book |
| 23 | `Match Number` | 8 | Integer | Unique trade identifier (trade ID) |

### C. Message type `'X'`: Order Cancel (partial cancellation) - Length: 23 bytes
| Offset (byte) | Field | Size (bytes) | Type | Description |
| :--- | :--- | :--- | :--- | :--- |
| 0 | `Message Type` | 1 | Alpha (`'X'`) | Order Cancel message identifier |
| 1 | `Stock Locate` | 2 | Integer | Stock identifier |
| 3 | `Tracking Number` | 2 | Integer | Nasdaq tracking |
| 5 | `Timestamp` | 6 | Integer | Timestamp |
| 11 | `Order Reference Number` | 8 | Integer | Reference of the canceled order |
| 19 | `Canceled Shares` | 4 | Integer | Number of shares to deduct from the book |

### D. Message type `'D'`: Order Delete (full removal) - Length: 19 bytes
| Offset (byte) | Field | Size (bytes) | Type | Description |
| :--- | :--- | :--- | :--- | :--- |
| 0 | `Message Type` | 1 | Alpha (`'D'`) | Order Delete message identifier |
| 1 | `Stock Locate` | 2 | Integer | Stock identifier |
| 3 | `Tracking Number` | 2 | Integer | Nasdaq tracking |
| 5 | `Timestamp` | 6 | Integer | Timestamp |
| 11 | `Order Reference Number` | 8 | Integer | Reference of the order to remove entirely |

---

## 3. Implementation constraints in Verilog / SystemVerilog
1. **Byte alignment machine:** Since messages are 36, 31, 23 or 19 bytes long, none is aligned on a power of 2. A 64 to 128-bit shift register (*barrel shifter*) is required to align the fields before extraction.
2. **Endianness handling:** Multi-byte fields must be byte-swapped:
   ```systemverilog
   assign price = {raw_data[7:0], raw_data[15:8], raw_data[23:16], raw_data[31:24]};
   ```
