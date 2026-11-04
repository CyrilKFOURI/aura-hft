// Unit tests of the software reference path (no data file needed).
#include "ref_pipeline.hpp"
#include "latency_hist.hpp"

#include <cstdio>
#include <vector>

using namespace aura;

static int failures = 0;
#define CHECK(c) do { if (!(c)) { std::printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #c); ++failures; } } while (0)

static std::vector<uint8_t> add_msg(uint16_t locate, uint64_t ref, char side, uint32_t shares, uint32_t price) {
    std::vector<uint8_t> m(36, 0);
    m[0] = 'A';
    m[1] = uint8_t(locate >> 8); m[2] = uint8_t(locate);
    for (int i = 0; i < 8; ++i) m[11 + i] = uint8_t(ref >> (56 - 8 * i));
    m[19] = uint8_t(side);
    for (int i = 0; i < 4; ++i) m[20 + i] = uint8_t(shares >> (24 - 8 * i));
    for (int i = 0; i < 8; ++i) m[24 + i] = uint8_t("AAPL    "[i]);
    for (int i = 0; i < 4; ++i) m[32 + i] = uint8_t(price >> (24 - 8 * i));
    return m;
}

static std::vector<uint8_t> dir_msg(uint16_t locate, const char* sym8) {
    std::vector<uint8_t> m(39, 0);
    m[0] = 'R';
    m[1] = uint8_t(locate >> 8); m[2] = uint8_t(locate);
    for (int i = 0; i < 8; ++i) m[11 + i] = uint8_t(sym8[i]);
    return m;
}

int main() {
    const int32_t t40 = 858993459;  // round(0.4 * 2^31)

    // OBI: (Vb - Va)/(Vb + Va) = 0.4 exactly at 70/30 -> 0.4*2^31 = 858993459.2 > threshold
    CHECK(obi_signal(70, 30, t40, -t40).buy);
    CHECK(!obi_signal(69, 31, t40, -t40).buy);
    CHECK(obi_signal(30, 70, t40, -t40).sell);
    CHECK(!obi_signal(0, 0, t40, -t40).valid);
    CHECK(obi_signal(1, 0, t40, -t40).buy && !obi_signal(1, 0, t40, -t40).sell);
    // 32-bit extremes: lhs = (2^32-1)*2^31 >= rhs = (2^31-1)*(2^32-1), no overflow
    CHECK(obi_signal(0xFFFFFFFFu, 0, INT32_MAX, INT32_MIN).buy);
    CHECK(obi_signal(0, 0xFFFFFFFFu, INT32_MAX, INT32_MIN).sell);

    // Risk priority and collar
    RiskConfig rc;
    rc.max_cum_notional_raw = 3'000'000;
    PreTradeRisk r(rc);
    CHECK(r.check(false, 2000, 100, 90, 110) == RISK_REJECT_MAX_SHARES);
    CHECK(r.check(false, 10, 110 + 5001, 90, 110) == RISK_REJECT_PRICE_COLLAR);
    CHECK(r.check(true, 10, 89 , 90, 110) == RISK_PASS);  // bid <= collar: sell collar disabled
    CHECK(r.check(false, 1000, 1'500'000, 0, 0) == RISK_REJECT_MAX_NOTIONAL);
    CHECK(r.check(false, 1000, 2'000, 0, 0) == RISK_PASS);             // cum 2'000'890
    CHECK(r.check(false, 1000, 1'000, 0, 0) == RISK_REJECT_CUMULATIVE_NOTIONAL);
    CHECK(r.accumulated() == 2'000'890);

    // Saturating accumulator with the cumulative limit disabled
    RiskConfig open;
    open.max_order_shares = 0; open.price_collar = 0; open.max_notional_raw = 0;
    PreTradeRisk s(open);
    s.set_accumulated(~uint64_t(0) - 5);
    CHECK(s.check(false, 10, 10, 0, 0) == RISK_PASS);
    CHECK(s.accumulated() == ~uint64_t(0));
    // With a limit, the 65-bit sum must not wrap and pass
    RiskConfig lim = open; lim.max_cum_notional_raw = ~uint64_t(0) - 1;
    PreTradeRisk w(lim);
    w.set_accumulated(~uint64_t(0) - 5);
    CHECK(w.check(false, 10, 10, 0, 0) == RISK_REJECT_CUMULATIVE_NOTIONAL);

    // Pipeline: symbol filtering via stock directory, top-5 ordering, signal + order
    Pipeline p("AAPL", StrategyConfig{}, RiskConfig{});
    Event ev;
    auto feed = [&](const std::vector<uint8_t>& m) { return p.on_message(m.data(), m.size(), ev); };
    CHECK(!feed(add_msg(7, 1, 'B', 100, 1'000'000)));  // locate unknown yet
    CHECK(!feed(dir_msg(7, "AAPL    ")));
    CHECK(feed(add_msg(7, 2, 'B', 300, 1'500'000)));
    CHECK(ev.sig.buy && ev.decision == 1);  // ask side empty -> OBI = +1
    CHECK(feed(add_msg(7, 3, 'S', 100, 1'500'100)));
    CHECK(feed(add_msg(7, 4, 'B', 50, 1'500'200 - 300)));
    CHECK(ev.top.bids[0].price == 1'500'000 && ev.top.bids[1].price == 1'499'900);
    CHECK(!feed(add_msg(8, 5, 'B', 50, 1)));  // other locate

    // Histogram buckets
    LatencyHistogram h;
    h.record(3); h.record(16); h.record(17); h.record(1000);
    CHECK(h.total() == 4);
    CHECK(LatencyHistogram::lower(16) == 16 && LatencyHistogram::lower(32) == 32);

    std::printf(failures ? "%d failure(s)\n" : "all ref_pipeline tests passed\n", failures);
    return failures ? 1 : 0;
}
