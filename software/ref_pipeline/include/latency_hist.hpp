// HDR-style log-linear latency histogram (ns): each power-of-two range is
// split into 16 linear sub-buckets, so the relative error stays below 6.25 %
// at every magnitude while memory is fixed (64 x 16 counters).
#pragma once

#include <array>
#include <bit>
#include <cstdint>
#include <sstream>
#include <string>

namespace aura {

class LatencyHistogram {
public:
    static constexpr int kSub = 16;

    void record(uint64_t ns) { ++counts_[index(ns)]; ++total_; }
    uint64_t total() const { return total_; }

    // Lower bound (ns) of bucket i.
    static uint64_t lower(int i) {
        const int mag = i / kSub, sub = i % kSub;
        if (mag == 0) return uint64_t(sub);
        return (uint64_t(kSub) + sub) << (mag - 1);
    }

    // Non-empty buckets as [[lower_ns, upper_ns, count], ...].
    std::string to_json() const {
        std::ostringstream o;
        o << '[';
        bool first = true;
        for (int i = 0; i < int(counts_.size()); ++i) {
            if (!counts_[i]) continue;
            o << (first ? "" : ", ") << '[' << lower(i) << ", " << lower(i + 1) << ", " << counts_[i] << ']';
            first = false;
        }
        o << ']';
        return o.str();
    }

private:
    static int index(uint64_t v) {
        if (v < uint64_t(kSub)) return int(v);
        const int msb = 63 - std::countl_zero(v);   // >= 4
        const int mag = msb - 3;                    // 16..31 -> 1, 32..63 -> 2 ...
        const int sub = int((v >> (mag - 1)) - kSub);
        const int i = mag * kSub + sub;
        return i < int(kBuckets) ? i : int(kBuckets) - 1;
    }
    static constexpr size_t kBuckets = 61 * kSub;
    std::array<uint64_t, kBuckets + 1> counts_{};
    uint64_t total_ = 0;
};

}  // namespace aura
