// aura_ref: software reference path of the AURA-HFT pipeline (step P6).
//
//   aura_ref trace <file.itch> [opts] --out trace.csv   one line per applied book event
//   aura_ref bench <file.itch> [opts] --json out.json   per-message latency + throughput
//
// Options: --symbol AAPL  --limit N  --buy-q31 N  --sell-q31 N  --shares N
//          --max-shares N --collar N --max-notional N --max-cum N --cpu N --reps N
#include "ref_pipeline.hpp"
#include "latency_hist.hpp"

#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#ifdef __linux__
#include <sched.h>
#endif

using namespace aura;

namespace {

struct Args {
    std::string mode, file, symbol = "AAPL", out, json;
    size_t limit = 0;
    int cpu = 0;
    int reps = 3;
    StrategyConfig strat;
    RiskConfig risk;
};

[[noreturn]] void usage() {
    std::cerr << "usage: aura_ref trace|bench <file.itch> [--symbol S] [--limit N] [--out F] [--json F]\n"
                 "       [--buy-q31 N] [--sell-q31 N] [--shares N] [--max-shares N] [--collar N]\n"
                 "       [--max-notional N] [--max-cum N] [--cpu N] [--reps N]\n";
    std::exit(2);
}

Args parse(int argc, char** argv) {
    if (argc < 3) usage();
    Args a;
    a.mode = argv[1];
    a.file = argv[2];
    for (int i = 3; i < argc; ++i) {
        std::string k = argv[i];
        if (i + 1 >= argc) usage();
        std::string v = argv[++i];
        if (k == "--symbol") a.symbol = v;
        else if (k == "--limit") a.limit = std::stoull(v);
        else if (k == "--out") a.out = v;
        else if (k == "--json") a.json = v;
        else if (k == "--buy-q31") a.strat.buy_q31 = int32_t(std::stol(v));
        else if (k == "--sell-q31") a.strat.sell_q31 = int32_t(std::stol(v));
        else if (k == "--shares") a.strat.order_shares = uint32_t(std::stoul(v));
        else if (k == "--max-shares") a.risk.max_order_shares = uint32_t(std::stoul(v));
        else if (k == "--collar") a.risk.price_collar = uint32_t(std::stoul(v));
        else if (k == "--max-notional") a.risk.max_notional_raw = std::stoull(v);
        else if (k == "--max-cum") a.risk.max_cum_notional_raw = std::stoull(v);
        else if (k == "--cpu") a.cpu = std::stoi(v);
        else if (k == "--reps") a.reps = std::stoi(v);
        else usage();
    }
    return a;
}

// Whole file in memory; offsets of each length-prefixed message.
struct Stream {
    std::vector<uint8_t> bytes;
    std::vector<size_t> offsets;
};

Stream load(const std::string& path, size_t limit) {
    std::ifstream f(path, std::ios::binary);
    if (!f) { std::cerr << "cannot open " << path << "\n"; std::exit(1); }
    Stream s;
    s.bytes.assign(std::istreambuf_iterator<char>(f), std::istreambuf_iterator<char>());
    size_t off = 0;
    while (off + 2 <= s.bytes.size()) {
        const size_t len = be16(&s.bytes[off]);
        if (off + 2 + len > s.bytes.size()) break;
        s.offsets.push_back(off);
        off += 2 + len;
        if (limit && s.offsets.size() >= limit) break;
    }
    return s;
}

void write_event(std::ostream& o, const Event& e) {
    o << e.ts << ',' << char(e.type);
    for (const auto& l : e.top.bids) o << ',' << l.price << ',' << l.shares;
    for (const auto& l : e.top.asks) o << ',' << l.price << ',' << l.shares;
    o << ',' << int(e.sig.valid) << ',' << int(e.sig.buy) << ',' << int(e.sig.sell) << ','
      << int(e.decision) << ',' << int(e.reason) << ',' << e.cum_notional << '\n';
}

int run_trace(const Args& a) {
    Stream s = load(a.file, a.limit);
    Pipeline p(a.symbol, a.strat, a.risk);
    std::ofstream out(a.out);
    if (!out) { std::cerr << "cannot write " << a.out << "\n"; return 1; }
    Event ev;
    size_t events = 0;
    for (size_t off : s.offsets) {
        const size_t len = be16(&s.bytes[off]);
        if (p.on_message(&s.bytes[off + 2], len, ev)) { write_event(out, ev); ++events; }
    }
    std::cout << "messages " << s.offsets.size() << " events " << events << " approved " << p.risk().approved()
              << " rejected " << p.risk().rejected() << "\n";
    return 0;
}

void pin(int cpu) {
#ifdef __linux__
    cpu_set_t set;
    CPU_ZERO(&set);
    CPU_SET(cpu, &set);
    if (sched_setaffinity(0, sizeof(set), &set) != 0) std::perror("sched_setaffinity");
#else
    (void)cpu;
#endif
}

using Clock = std::chrono::steady_clock;

uint64_t ns_between(Clock::time_point a, Clock::time_point b) {
    return uint64_t(std::chrono::duration_cast<std::chrono::nanoseconds>(b - a).count());
}

// Median cost of two back-to-back steady_clock::now() calls.
uint64_t timer_overhead_ns() {
    std::vector<uint64_t> v(200000);
    for (auto& x : v) { auto t0 = Clock::now(); auto t1 = Clock::now(); x = ns_between(t0, t1); }
    std::nth_element(v.begin(), v.begin() + v.size() / 2, v.end());
    return v[v.size() / 2];
}

int run_bench(const Args& a) {
    pin(a.cpu);
    Stream s = load(a.file, a.limit);
    const uint64_t overhead = timer_overhead_ns();

    // Throughput pass (no per-message timer), repeated; the first rep warms caches.
    double best_mps = 0;
    size_t events = 0;
    for (int r = 0; r < std::max(a.reps, 2); ++r) {
        Pipeline p(a.symbol, a.strat, a.risk);
        Event ev;
        size_t n = 0;
        const auto t0 = Clock::now();
        for (size_t off : s.offsets) n += p.on_message(&s.bytes[off + 2], be16(&s.bytes[off]), ev);
        const auto t1 = Clock::now();
        events = n;
        if (r > 0) best_mps = std::max(best_mps, double(s.offsets.size()) * 1e9 / double(ns_between(t0, t1)));
    }

    // Latency pass: timer around each message of the target symbol that changes the book.
    Pipeline warm(a.symbol, a.strat, a.risk);
    Pipeline p(a.symbol, a.strat, a.risk);
    Event ev;
    for (size_t off : s.offsets) warm.on_message(&s.bytes[off + 2], be16(&s.bytes[off]), ev);
    LatencyHistogram hist;
    std::vector<uint64_t> samples;
    samples.reserve(events + 16);
    for (size_t off : s.offsets) {
        const uint8_t* m = &s.bytes[off + 2];
        const size_t len = be16(&s.bytes[off]);
        const auto t0 = Clock::now();
        const bool applied = p.on_message(m, len, ev);
        const auto t1 = Clock::now();
        if (applied) { const uint64_t d = ns_between(t0, t1); samples.push_back(d); hist.record(d); }
    }
    std::sort(samples.begin(), samples.end());
    auto pct = [&](double q) -> uint64_t {
        if (samples.empty()) return 0;
        size_t i = size_t(q * double(samples.size() - 1) + 0.5);
        return samples[std::min(i, samples.size() - 1)];
    };

    double mean = 0;
    for (uint64_t x : samples) mean += double(x);
    if (!samples.empty()) mean /= double(samples.size());

    std::ostringstream j;
    j << "{\n"
      << "  \"symbol\": \"" << a.symbol << "\",\n"
      << "  \"messages\": " << s.offsets.size() << ",\n"
      << "  \"events\": " << samples.size() << ",\n"
      << "  \"throughput_msgs_per_s\": " << uint64_t(best_mps) << ",\n"
      << "  \"timer_overhead_ns\": " << overhead << ",\n"
      << "  \"latency_ns\": {\"p50\": " << pct(0.50) << ", \"p99\": " << pct(0.99) << ", \"p999\": " << pct(0.999)
      << ", \"mean\": " << uint64_t(mean + 0.5) << ", \"max\": " << (samples.empty() ? 0 : samples.back()) << ", \"min\": " << (samples.empty() ? 0 : samples.front())
      << "},\n"
      << "  \"histogram\": " << hist.to_json() << "\n"
      << "}\n";
    std::cout << j.str();
    if (!a.json.empty()) std::ofstream(a.json) << j.str();
    return 0;
}

}  // namespace

int main(int argc, char** argv) {
    Args a = parse(argc, argv);
    if (a.mode == "trace") { if (a.out.empty()) usage(); return run_trace(a); }
    if (a.mode == "bench") return run_bench(a);
    usage();
}
