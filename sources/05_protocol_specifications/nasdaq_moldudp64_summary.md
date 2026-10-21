# Technical Specification: NASDAQ MoldUDP64 1.0 Protocol

## 1. Role of the protocol
* **Official document:** NASDAQ MoldUDP64 1.0 specification (`moldudp64.pdf`, public, not included in this repository)
* MoldUDP64 is the transport layer on top of UDP multicast used to broadcast ITCH market data in order.
* Since UDP guarantees neither ordering nor loss-free delivery, MoldUDP64 adds a session header containing the sequence number of the first message carried in the packet.

---

## 2. MoldUDP64 packet structure

A MoldUDP64 UDP network packet consists of:
1. **The MoldUDP64 header (20 bytes)**
2. **A sequence of concatenated ITCH message blocks**

```
+-----------------------------------------------------------------------+
|                        MoldUDP64 Header (20 Bytes)                    |
| - Session Name (10 Bytes ASCII)                                       |
| - Sequence Number (8 Bytes Integer, Big Endian)                       |
| - Message Count (2 Bytes Integer, Big Endian)                         |
+-----------------------------------------------------------------------+
| Message Block 1: Length (2 Bytes) | ITCH Payload (variable: ex 36 B)  |
+-----------------------------------------------------------------------+
| Message Block 2: Length (2 Bytes) | ITCH Payload (variable: ex 19 B)  |
+-----------------------------------------------------------------------+
| ...                                                                   |
+-----------------------------------------------------------------------+
```

### Session header table (20 bytes)
| Offset (byte) | Field | Size (bytes) | Description |
| :--- | :--- | :--- | :--- |
| 0 | `Session Name` | 10 | Broadcast session identifier (e.g. "SESSION001") |
| 10 | `Sequence Number`| 8 | Global sequence number of the first message in this packet |
| 18 | `Message Count` | 2 | Number of application messages in this packet (`0xFFFF` = End of Session) |

### Message block table
| Offset (byte) | Field | Size (bytes) | Description |
| :--- | :--- | :--- | :--- |
| 0 | `Message Length` | 2 | Size of the ITCH message that immediately follows |
| 2 | `Message Data` | $N$ | Raw ITCH message content (e.g. 36 bytes for type `'A'`) |

---

## 3. Hardware decapsulation logic
1. **Sequence number check:**
   * The hardware block keeps an `expected_sequence_number` register.
   * If `incoming_seq == expected_seq`, the packet is valid and the register is incremented by `Message Count`.
   * If `incoming_seq > expected_seq`, a packet was lost: the FPGA raises an alert flag (*gap detected*) to request retransmission over the host unicast channel.
2. **Streaming extraction:**
   * After the 20 header bytes, a length counter decrements on each word until the end of the current message, then reads the 2 bytes of the next message.
