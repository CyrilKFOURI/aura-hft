#pragma once

#include "aura_uio_device.hpp"
#include <cstdint>
#include <string>
#include <memory>
#include <atomic>

namespace aura::driver {

// ============================================================================
// Register Address Offsets (Matching axi_lite_control_registers.sv)
// ============================================================================
namespace reg {
    inline constexpr uint32_t CONTROL           = 0x00;
    inline constexpr uint32_t OBI_THRESHOLD     = 0x04;
    inline constexpr uint32_t RISK_MAX_SHARES   = 0x08;
    inline constexpr uint32_t RISK_PRICE_COLLAR = 0x0C;
    inline constexpr uint32_t RISK_MAX_NOTIONAL = 0x10;
    inline constexpr uint32_t MM_GAMMA          = 0x14;
    inline constexpr uint32_t MM_SIGMA_SQ       = 0x18;
    inline constexpr uint32_t STATUS            = 0x1C;
    inline constexpr uint32_t INGRESS_COUNT     = 0x20;
    inline constexpr uint32_t EGRESS_COUNT      = 0x24;
    inline constexpr uint32_t LAST_LATENCY      = 0x28;
    inline constexpr uint32_t CURRENT_INVENTORY = 0x2C;
    inline constexpr uint32_t MAX_DRAWDOWN_LOW  = 0x30;
    inline constexpr uint32_t MAX_DRAWDOWN_HIGH = 0x34;
    inline constexpr uint32_t MTM_PNL_LOW       = 0x38;
    inline constexpr uint32_t MTM_PNL_HIGH      = 0x3C;
    inline constexpr uint32_t DRAWDOWN_LOW      = 0x40;
    inline constexpr uint32_t DRAWDOWN_HIGH     = 0x44;
    inline constexpr uint32_t FCS_ERROR_COUNT   = 0x48;
    inline constexpr uint32_t MIN_LATENCY_NS    = 0x4C;
    inline constexpr uint32_t MAX_LATENCY_NS    = 0x50;
    inline constexpr uint32_t PTP_TIME_SEC_LOW  = 0x54;
    inline constexpr uint32_t PTP_TIME_SEC_HIGH = 0x58;
    inline constexpr uint32_t PTP_TIME_NS       = 0x5C;
}

// Control register bit masks
namespace ctrl_bit {
    inline constexpr uint32_t PIPELINE_EN   = (1u << 0);
    inline constexpr uint32_t SOFT_RESET    = (1u << 1);
    inline constexpr uint32_t KILL_SWITCH   = (1u << 2);
    inline constexpr uint32_t STRAT_SELECT  = (1u << 3); // 0 = OBI, 1 = Avellaneda-Stoikov
    inline constexpr uint32_t BREAKER_RESET = (1u << 4);
}

// Status register bit masks
namespace status_bit {
    inline constexpr uint32_t PIPELINE_READY   = (1u << 0);
    inline constexpr uint32_t BBO_VALID        = (1u << 1);
    inline constexpr uint32_t RISK_REJECT      = (1u << 2);
    inline constexpr uint32_t KILL_ENGAGED     = (1u << 3);
    inline constexpr uint32_t BREAKER_TRIPPED  = (1u << 4);
}

enum class StrategyMode : uint8_t {
    OBI_THRESHOLD       = 0,
    AVELLANEDA_STOIKOV  = 1
};

struct StatusFlags {
    bool pipeline_ready{false};
    bool bbo_valid{false};
    bool risk_reject{false};
    bool kill_switch_engaged{false};
    bool circuit_breaker_tripped{false};
};

struct TelemetrySnapshot {
    StatusFlags flags;
    uint32_t ingress_count{0};
    uint32_t egress_count{0};
    uint32_t last_latency_cycles{0};
    int32_t  current_inventory{0};
    int64_t  mtm_pnl{0};
    uint64_t drawdown{0};
    uint32_t fcs_error_count{0};
    uint32_t min_latency_ns{0};
    uint32_t max_latency_ns{0};
};

struct PtpTimestamp {
    uint64_t seconds{0};
    uint32_t nanoseconds{0};
};

/**
 * @brief High-performance C++20 Linux UIO Driver for AURA-HFT FPGA hardware.
 * Provides < 50 ns direct memory-mapped access to PL registers.
 */
class AuraHftDriver {
public:
    explicit AuraHftDriver(std::unique_ptr<UioDevice> uio_dev)
        : m_uio(std::move(uio_dev)) {}

    static std::unique_ptr<AuraHftDriver> open(const std::string& dev_path = "/dev/uio0") {
        return std::make_unique<AuraHftDriver>(std::make_unique<UioDevice>(dev_path));
    }

    static std::unique_ptr<AuraHftDriver> open_mock() {
        return std::make_unique<AuraHftDriver>(UioDevice::create_mock(4096));
    }

    // ------------------------------------------------------------------------
    // Fast-path Kill Switch & Safety Control (< 50 ns execution)
    // ------------------------------------------------------------------------
    inline void arm_kill_switch() noexcept {
        uint32_t ctrl = m_uio->read32(reg::CONTROL);
        ctrl |= ctrl_bit::KILL_SWITCH;
        m_uio->write32(reg::CONTROL, ctrl);
        std::atomic_signal_fence(std::memory_order_seq_cst);
    }

    inline void disarm_kill_switch() noexcept {
        uint32_t ctrl = m_uio->read32(reg::CONTROL);
        ctrl &= ~ctrl_bit::KILL_SWITCH;
        m_uio->write32(reg::CONTROL, ctrl);
        std::atomic_signal_fence(std::memory_order_seq_cst);
    }

    [[nodiscard]] inline bool is_kill_switch_active() const noexcept {
        return (m_uio->read32(reg::STATUS) & status_bit::KILL_ENGAGED) != 0;
    }

    inline void reset_circuit_breaker() noexcept {
        uint32_t ctrl = m_uio->read32(reg::CONTROL);
        m_uio->write32(reg::CONTROL, ctrl | ctrl_bit::BREAKER_RESET);
        std::atomic_signal_fence(std::memory_order_seq_cst);
        m_uio->write32(reg::CONTROL, ctrl & ~ctrl_bit::BREAKER_RESET);
    }

    inline void set_pipeline_enable(bool enable) noexcept {
        uint32_t ctrl = m_uio->read32(reg::CONTROL);
        if (enable) ctrl |= ctrl_bit::PIPELINE_EN;
        else        ctrl &= ~ctrl_bit::PIPELINE_EN;
        m_uio->write32(reg::CONTROL, ctrl);
    }

    inline void trigger_soft_reset() noexcept {
        uint32_t ctrl = m_uio->read32(reg::CONTROL);
        m_uio->write32(reg::CONTROL, ctrl | ctrl_bit::SOFT_RESET);
        std::atomic_signal_fence(std::memory_order_seq_cst);
        m_uio->write32(reg::CONTROL, ctrl & ~ctrl_bit::SOFT_RESET);
    }

    inline void set_strategy(StrategyMode mode) noexcept {
        uint32_t ctrl = m_uio->read32(reg::CONTROL);
        if (mode == StrategyMode::AVELLANEDA_STOIKOV) {
            ctrl |= ctrl_bit::STRAT_SELECT;
        } else {
            ctrl &= ~ctrl_bit::STRAT_SELECT;
        }
        m_uio->write32(reg::CONTROL, ctrl);
    }

    // ------------------------------------------------------------------------
    // Parameter Tuning
    // ------------------------------------------------------------------------
    inline void set_obi_threshold(uint32_t threshold_q1_31) noexcept {
        m_uio->write32(reg::OBI_THRESHOLD, threshold_q1_31);
    }

    inline void set_risk_limits(uint32_t max_shares, uint32_t price_collar, uint32_t max_notional, uint64_t max_drawdown) noexcept {
        m_uio->write32(reg::RISK_MAX_SHARES, max_shares);
        m_uio->write32(reg::RISK_PRICE_COLLAR, price_collar);
        m_uio->write32(reg::RISK_MAX_NOTIONAL, max_notional);
        m_uio->write32(reg::MAX_DRAWDOWN_LOW, static_cast<uint32_t>(max_drawdown & 0xFFFFFFFFULL));
        m_uio->write32(reg::MAX_DRAWDOWN_HIGH, static_cast<uint32_t>((max_drawdown >> 32) & 0xFFFFFFFFULL));
    }

    inline void set_avellaneda_params(uint16_t gamma, uint16_t sigma_sq) noexcept {
        m_uio->write32(reg::MM_GAMMA, static_cast<uint32_t>(gamma));
        m_uio->write32(reg::MM_SIGMA_SQ, static_cast<uint32_t>(sigma_sq));
    }

    // ------------------------------------------------------------------------
    // Telemetry & Metrics
    // ------------------------------------------------------------------------
    [[nodiscard]] StatusFlags read_status() const noexcept {
        uint32_t s = m_uio->read32(reg::STATUS);
        StatusFlags flags;
        flags.pipeline_ready          = (s & status_bit::PIPELINE_READY) != 0;
        flags.bbo_valid               = (s & status_bit::BBO_VALID) != 0;
        flags.risk_reject             = (s & status_bit::RISK_REJECT) != 0;
        flags.kill_switch_engaged     = (s & status_bit::KILL_ENGAGED) != 0;
        flags.circuit_breaker_tripped = (s & status_bit::BREAKER_TRIPPED) != 0;
        return flags;
    }

    [[nodiscard]] TelemetrySnapshot read_telemetry() const noexcept {
        TelemetrySnapshot snap;
        snap.flags = read_status();
        snap.ingress_count        = m_uio->read32(reg::INGRESS_COUNT);
        snap.egress_count         = m_uio->read32(reg::EGRESS_COUNT);
        snap.last_latency_cycles  = m_uio->read32(reg::LAST_LATENCY);
        snap.current_inventory    = static_cast<int32_t>(m_uio->read32(reg::CURRENT_INVENTORY));

        uint64_t pnl_low  = m_uio->read32(reg::MTM_PNL_LOW);
        uint64_t pnl_high = m_uio->read32(reg::MTM_PNL_HIGH);
        snap.mtm_pnl = static_cast<int64_t>((pnl_high << 32) | pnl_low);

        uint64_t dd_low  = m_uio->read32(reg::DRAWDOWN_LOW);
        uint64_t dd_high = m_uio->read32(reg::DRAWDOWN_HIGH);
        snap.drawdown = (dd_high << 32) | dd_low;

        snap.fcs_error_count = m_uio->read32(reg::FCS_ERROR_COUNT);
        snap.min_latency_ns  = m_uio->read32(reg::MIN_LATENCY_NS);
        snap.max_latency_ns  = m_uio->read32(reg::MAX_LATENCY_NS);
        return snap;
    }

    [[nodiscard]] PtpTimestamp read_ptp_timestamp() const noexcept {
        uint64_t sec_low  = m_uio->read32(reg::PTP_TIME_SEC_LOW);
        uint64_t sec_high = m_uio->read32(reg::PTP_TIME_SEC_HIGH);
        uint32_t ns       = m_uio->read32(reg::PTP_TIME_NS);
        return PtpTimestamp{
            .seconds = ((sec_high & 0xFFFFULL) << 32) | sec_low,
            .nanoseconds = ns
        };
    }

    [[nodiscard]] UioDevice& device() noexcept { return *m_uio; }
    [[nodiscard]] const UioDevice& device() const noexcept { return *m_uio; }

private:
    std::unique_ptr<UioDevice> m_uio;
};

} // namespace aura::driver
