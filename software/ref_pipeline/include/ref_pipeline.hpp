// AURA-HFT software reference path (step P6).
//
// Same logic as the RTL reference path, in plain C++20:
//   ITCH 5.0 parse -> full-depth book (exact top 5) -> division-free OBI
//   threshold signal (rtl/quant/obi_signal.sv) -> pre-trade risk
//   (rtl/risk/pre_trade_risk.sv, saturating cumulative notional).
// Paper only: nothing here sends an order anywhere.
#pragma once

#include <array>
#include <cstdint>
#include <cstring>
#include <functional>
#include <map>
#include <string>
#include <unordered_map>

namespace aura {

// 128-bit integers (GCC/Clang extension) hold the RTL's 65/66-bit intermediates exactly.
__extension__ typedef __int128 i128;
__extension__ typedef unsigned __int128 u128;

// ---------------------------------------------------------------- ITCH 5.0
inline uint16_t be16(const uint8_t* p) { return uint16_t((p[0] << 8) | p[1]); }
inline uint32_t be32(const uint8_t* p) {
    return (uint32_t(p[0]) << 24) | (uint32_t(p[1]) << 16) | (uint32_t(p[2]) << 8) | uint32_t(p[3]);
}
inline uint64_t be48(const uint8_t* p) {
    uint64_t v = 0;
    for (int i = 0; i < 6; ++i) v = (v << 8) | p[i];
    return v;
}
inline uint64_t be64(const uint8_t* p) {
    uint64_t v = 0;
    for (int i = 0; i < 8; ++i) v = (v << 8) | p[i];
    return v;
}

// Minimum payload length per book-relevant message type (0 = not handled).
inline size_t itch_min_len(uint8_t type) {
    switch (type) {
        case 'A': return 36;
        case 'F': return 40;
        case 'E': return 31;
        case 'C': return 36;
        case 'X': return 23;
        case 'D': return 19;
        case 'U': return 35;
        case 'R': return 39;
        default: return 0;
    }
}

// ---------------------------------------------------------------- Book
constexpr int kDepth = 5;

struct Level {
    uint32_t price = 0;   // 1/10000 $
    uint64_t shares = 0;
};

struct Top5 {
    std::array<Level, kDepth> bids{};  // best first, zero padded
    std::array<Level, kDepth> asks{};
};

class FullDepthBook {
public:
    FullDepthBook() { orders_.reserve(1 << 20); }

    void clear() { orders_.clear(); bids_.clear(); asks_.clear(); }
    bool has(uint64_t ref) const { return orders_.count(ref) != 0; }

    void add(uint64_t ref, bool buy, uint32_t price, uint32_t shares) {
        orders_[ref] = Order{price, shares, buy};
        if (buy) bids_[price] += shares; else asks_[price] += shares;
    }
    // Executes / cancels min(order.shares, n); returns false if unknown ref.
    bool reduce(uint64_t ref, uint32_t n) {
        auto it = orders_.find(ref);
        if (it == orders_.end()) return false;
        Order& o = it->second;
        uint32_t q = n < o.shares ? n : o.shares;
        take(o.buy, o.price, q);
        o.shares -= q;
        if (o.shares == 0) orders_.erase(it);
        return true;
    }
    bool remove(uint64_t ref) {
        auto it = orders_.find(ref);
        if (it == orders_.end()) return false;
        take(it->second.buy, it->second.price, it->second.shares);
        orders_.erase(it);
        return true;
    }
    bool replace(uint64_t old_ref, uint64_t new_ref, uint32_t price, uint32_t shares) {
        auto it = orders_.find(old_ref);
        if (it == orders_.end()) return false;
        bool buy = it->second.buy;
        remove(old_ref);
        add(new_ref, buy, price, shares);
        return true;
    }

    Level best_bid() const { return bids_.empty() ? Level{} : Level{bids_.begin()->first, bids_.begin()->second}; }
    Level best_ask() const { return asks_.empty() ? Level{} : Level{asks_.begin()->first, asks_.begin()->second}; }

    Top5 top5() const {
        Top5 t;
        int i = 0;
        for (auto it = bids_.begin(); it != bids_.end() && i < kDepth; ++it, ++i) t.bids[i] = {it->first, it->second};
        i = 0;
        for (auto it = asks_.begin(); it != asks_.end() && i < kDepth; ++it, ++i) t.asks[i] = {it->first, it->second};
        return t;
    }
    size_t live_orders() const { return orders_.size(); }

private:
    struct Order { uint32_t price; uint32_t shares; bool buy; };

    template <class M>
    static void take_from(M& side, uint32_t price, uint64_t q) {
        auto it = side.find(price);
        if (it == side.end()) return;
        if (it->second <= q) side.erase(it); else it->second -= q;
    }
    void take(bool buy, uint32_t price, uint64_t q) {
        if (buy) take_from(bids_, price, q); else take_from(asks_, price, q);
    }

    std::unordered_map<uint64_t, Order> orders_;
    std::map<uint32_t, uint64_t, std::greater<uint32_t>> bids_;
    std::map<uint32_t, uint64_t> asks_;
};

// ---------------------------------------------------------------- OBI signal
// Exact replica of obi_signal.sv: OBI >= T  <=>  (Vb - Va) * 2^31 >= T * (Vb + Va).
// The RTL inputs are 32-bit share counts; the products fit in 66 bits, so
// i128 is exact.
struct ObiDecision { bool valid; bool buy; bool sell; };

inline ObiDecision obi_signal(uint32_t vb, uint32_t va, int32_t buy_q31, int32_t sell_q31) {
    const i128 diff = i128(vb) - i128(va);
    const i128 sum = i128(vb) + i128(va);
    if (sum == 0) return {false, false, false};
    const i128 lhs = diff * (i128(1) << 31);
    return {true, lhs >= i128(buy_q31) * sum, lhs <= i128(sell_q31) * sum};
}

// ---------------------------------------------------------------- Risk
enum RiskReason : uint8_t {  // rtl/include/ouch_pkg.sv risk_reject_reason_e
    RISK_PASS = 0,
    RISK_REJECT_KILL_SWITCH = 1,
    RISK_REJECT_MAX_SHARES = 2,
    RISK_REJECT_PRICE_COLLAR = 3,
    RISK_REJECT_MAX_NOTIONAL = 4,
    RISK_REJECT_CUMULATIVE_NOTIONAL = 5,
    RISK_REJECT_CIRCUIT_BREAKER = 6,
};

struct RiskConfig {           // pre_trade_risk.sv registers; 0 disables a limit
    bool kill_switch = false;
    bool circuit_breaker = false;
    uint32_t max_order_shares = 1000;
    uint32_t price_collar = 5000;             // $0.50
    uint64_t max_notional_raw = 500'000'000;  // shares * raw price ($50k)
    uint64_t max_cum_notional_raw = 0;
};

class PreTradeRisk {
public:
    explicit PreTradeRisk(RiskConfig cfg) : cfg_(cfg) {}

    // side: false = buy, true = sell. Same priority order as the RTL.
    RiskReason check(bool sell, uint32_t shares, uint32_t price, uint32_t bbo_bid, uint32_t bbo_ask) {
        RiskReason r = decide(sell, shares, price, bbo_bid, bbo_ask);
        if (r == RISK_PASS) {
            const u128 sum = (u128)acc_ + (uint64_t(shares) * uint64_t(price));
            acc_ = (sum >> 64) ? ~uint64_t(0) : uint64_t(sum);  // saturating, as in the RTL
            ++approved_;
        } else {
            ++rejected_;
        }
        return r;
    }
    uint64_t accumulated() const { return acc_; }
    uint32_t approved() const { return approved_; }
    uint32_t rejected() const { return rejected_; }
    void set_accumulated(uint64_t v) { acc_ = v; }  // self-test only

private:
    RiskReason decide(bool sell, uint32_t shares, uint32_t price, uint32_t bid, uint32_t ask) const {
        if (cfg_.kill_switch) return RISK_REJECT_KILL_SWITCH;
        if (cfg_.circuit_breaker) return RISK_REJECT_CIRCUIT_BREAKER;
        if (cfg_.max_order_shares > 0 && shares > cfg_.max_order_shares) return RISK_REJECT_MAX_SHARES;
        if (cfg_.price_collar > 0) {
            if (!sell) {
                if (ask > 0 && price > uint32_t(ask + cfg_.price_collar)) return RISK_REJECT_PRICE_COLLAR;
            } else if (bid > 0 && bid > cfg_.price_collar && price < bid - cfg_.price_collar) {
                return RISK_REJECT_PRICE_COLLAR;
            }
        }
        const uint64_t notional = uint64_t(shares) * uint64_t(price);
        if (cfg_.max_notional_raw > 0 && notional > cfg_.max_notional_raw) return RISK_REJECT_MAX_NOTIONAL;
        const u128 cum = (u128)acc_ + notional;
        if (cfg_.max_cum_notional_raw > 0 && cum > cfg_.max_cum_notional_raw) return RISK_REJECT_CUMULATIVE_NOTIONAL;
        return RISK_PASS;
    }

    RiskConfig cfg_;
    uint64_t acc_ = 0;
    uint32_t approved_ = 0;
    uint32_t rejected_ = 0;
};

// ---------------------------------------------------------------- Pipeline
struct StrategyConfig {
    int32_t buy_q31 = 858993459;     // +0.40
    int32_t sell_q31 = -858993459;   // -0.40
    uint32_t order_shares = 100;     // cfg_default_order_shares
};

// One applied book event of the target symbol.
struct Event {
    uint64_t ts = 0;
    uint8_t type = 0;
    Top5 top{};
    ObiDecision sig{};
    uint8_t decision = 0;  // 0 no intent, 1 approved, 2 rejected
    RiskReason reason = RISK_PASS;
    uint64_t cum_notional = 0;
};

class Pipeline {
public:
    Pipeline(std::string symbol, StrategyConfig s, RiskConfig r)
        : symbol_(pad8(symbol)), strat_(s), risk_(r) {}

    // Returns true when the message changed the target book; `ev` is then filled.
    bool on_message(const uint8_t* m, size_t len, Event& ev) {
        if (len == 0) return false;
        const uint8_t t = m[0];
        const size_t need = itch_min_len(t);
        if (need == 0 || len < need) return false;
        const uint16_t locate = be16(m + 1);
        if (t == 'R') {
            if (std::memcmp(m + 11, symbol_.data(), 8) == 0) { locate_ = locate; have_locate_ = true; }
            return false;
        }
        if (!have_locate_ || locate != locate_) return false;
        const uint64_t ref = be64(m + 11);
        bool applied = true;
        switch (t) {
            case 'A': case 'F':
                book_.add(ref, m[19] == 'B', be32(m + 32), be32(m + 20));
                break;
            case 'E': case 'C': case 'X':
                applied = book_.reduce(ref, be32(m + 19));
                break;
            case 'D':
                applied = book_.remove(ref);
                break;
            case 'U':
                applied = book_.replace(ref, be64(m + 19), be32(m + 31), be32(m + 27));
                break;
            default:
                applied = false;
        }
        if (!applied) return false;
        ev.ts = be48(m + 5);
        ev.type = t;
        decide(ev);
        return true;
    }

    const FullDepthBook& book() const { return book_; }
    const PreTradeRisk& risk() const { return risk_; }

private:
    static std::string pad8(std::string s) { s.resize(8, ' '); return s; }

    void decide(Event& ev) {
        ev.top = book_.top5();
        const Level bb = ev.top.bids[0], ba = ev.top.asks[0];
        ev.sig = obi_signal(uint32_t(bb.shares), uint32_t(ba.shares), strat_.buy_q31, strat_.sell_q31);
        ev.decision = 0;
        ev.reason = RISK_PASS;
        if (ev.sig.buy || ev.sig.sell) {  // buy has priority, as in risk_ouch_top.sv
            const bool sell = !ev.sig.buy;
            const uint32_t px = sell ? ba.price : bb.price;
            ev.reason = risk_.check(sell, strat_.order_shares, px, bb.price, ba.price);
            ev.decision = ev.reason == RISK_PASS ? 1 : 2;
        }
        ev.cum_notional = risk_.accumulated();
    }

    std::string symbol_;
    StrategyConfig strat_;
    PreTradeRisk risk_;
    FullDepthBook book_;
    uint16_t locate_ = 0;
    bool have_locate_ = false;
};

}  // namespace aura
