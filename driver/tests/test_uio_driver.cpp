#include "aura_hft_driver.hpp"
#include <iostream>
#include <cassert>
#include <string>

using namespace aura::driver;

void run_test(const std::string& name, void (*func)()) {
    std::cout << "[RUN ] " << name << " ... ";
    try {
        func();
        std::cout << "PASSED\n";
    } catch (const std::exception& e) {
        std::cout << "FAILED (" << e.what() << ")\n";
        std::exit(1);
    }
}

void test_uio_mock_creation() {
    auto dev = UioDevice::create_mock(4096);
    assert(dev->is_mock());
    assert(dev->size() == 4096);

    dev->write32(0x10, 0x12345678);
    assert(dev->read32(0x10) == 0x12345678);

    bool threw = false;
    try {
        (void)dev->reg_ptr(4096); // Out of bounds
    } catch (const std::out_of_range&) {
        threw = true;
    }
    assert(threw);
}

void test_kill_switch_control() {
    auto drv = AuraHftDriver::open_mock();

    // Initial: kill switch off
    drv->disarm_kill_switch();
    assert((drv->device().read32(reg::CONTROL) & ctrl_bit::KILL_SWITCH) == 0);

    // Arm kill switch
    drv->arm_kill_switch();
    assert((drv->device().read32(reg::CONTROL) & ctrl_bit::KILL_SWITCH) != 0);

    // Mock status reflection (bit 3)
    drv->device().write32(reg::STATUS, status_bit::KILL_ENGAGED);
    assert(drv->is_kill_switch_active());
    assert(drv->read_status().kill_switch_engaged);

    // Disarm
    drv->disarm_kill_switch();
    assert((drv->device().read32(reg::CONTROL) & ctrl_bit::KILL_SWITCH) == 0);
}

void test_circuit_breaker_reset() {
    auto drv = AuraHftDriver::open_mock();

    // Mock circuit breaker tripped state in status register
    drv->device().write32(reg::STATUS, status_bit::BREAKER_TRIPPED);
    assert(drv->read_status().circuit_breaker_tripped);

    // Reset breaker (pulses bit 4)
    drv->reset_circuit_breaker();
    // After pulsing, the bit should be restored to 0
    assert((drv->device().read32(reg::CONTROL) & ctrl_bit::BREAKER_RESET) == 0);
}

void test_strategy_and_parameters() {
    auto drv = AuraHftDriver::open_mock();

    // Default strategy: OBI
    drv->set_strategy(StrategyMode::OBI_THRESHOLD);
    assert((drv->device().read32(reg::CONTROL) & ctrl_bit::STRAT_SELECT) == 0);

    // Switch to Avellaneda-Stoikov
    drv->set_strategy(StrategyMode::AVELLANEDA_STOIKOV);
    assert((drv->device().read32(reg::CONTROL) & ctrl_bit::STRAT_SELECT) != 0);

    // Set OBI threshold (Q1.31)
    drv->set_obi_threshold(0x53333333);
    assert(drv->device().read32(reg::OBI_THRESHOLD) == 0x53333333);

    // Set risk parameters (including 64-bit drawdown)
    uint64_t max_dd = 0x00000002540BE400ULL; // $100,000.0000
    drv->set_risk_limits(5000, 1638, 250000000, max_dd);
    assert(drv->device().read32(reg::RISK_MAX_SHARES) == 5000);
    assert(drv->device().read32(reg::RISK_PRICE_COLLAR) == 1638);
    assert(drv->device().read32(reg::RISK_MAX_NOTIONAL) == 250000000);
    assert(drv->device().read32(reg::MAX_DRAWDOWN_LOW) == (max_dd & 0xFFFFFFFF));
    assert(drv->device().read32(reg::MAX_DRAWDOWN_HIGH) == ((max_dd >> 32) & 0xFFFFFFFF));

    // Set Avellaneda params
    drv->set_avellaneda_params(150, 45);
    assert(drv->device().read32(reg::MM_GAMMA) == 150);
    assert(drv->device().read32(reg::MM_SIGMA_SQ) == 45);
}

void test_telemetry_and_ptp() {
    auto drv = AuraHftDriver::open_mock();

    // Populate mock telemetry values
    drv->device().write32(reg::STATUS, status_bit::PIPELINE_READY | status_bit::BBO_VALID);
    drv->device().write32(reg::INGRESS_COUNT, 1420);
    drv->device().write32(reg::EGRESS_COUNT, 85);
    drv->device().write32(reg::LAST_LATENCY, 44); // 44 cycles
    drv->device().write32(reg::CURRENT_INVENTORY, static_cast<uint32_t>(-50)); // -50 shares short

    // 64-bit PnL: +$1,250.5000 = 12505000
    int64_t pnl = 12505000;
    drv->device().write32(reg::MTM_PNL_LOW, static_cast<uint32_t>(pnl & 0xFFFFFFFF));
    drv->device().write32(reg::MTM_PNL_HIGH, static_cast<uint32_t>((pnl >> 32) & 0xFFFFFFFF));

    // PTP Time: 1729267200 sec, 543210000 ns
    uint64_t ptp_sec = 1729267200ULL;
    drv->device().write32(reg::PTP_TIME_SEC_LOW, static_cast<uint32_t>(ptp_sec & 0xFFFFFFFF));
    drv->device().write32(reg::PTP_TIME_SEC_HIGH, static_cast<uint32_t>((ptp_sec >> 32) & 0xFFFFFFFF));
    drv->device().write32(reg::PTP_TIME_NS, 543210000);

    auto tele = drv->read_telemetry();
    assert(tele.flags.pipeline_ready);
    assert(tele.flags.bbo_valid);
    assert(!tele.flags.risk_reject);
    assert(tele.ingress_count == 1420);
    assert(tele.egress_count == 85);
    assert(tele.last_latency_cycles == 44);
    assert(tele.current_inventory == -50);
    assert(tele.mtm_pnl == 12505000);

    auto ptp = drv->read_ptp_timestamp();
    assert(ptp.seconds == 1729267200ULL);
    assert(ptp.nanoseconds == 543210000);
}

int main() {
    std::cout << "========================================================\n"
              << "  AURA-HFT C++20 Linux UIO Driver Test Suite\n"
              << "========================================================\n";

    run_test("test_uio_mock_creation", test_uio_mock_creation);
    run_test("test_kill_switch_control", test_kill_switch_control);
    run_test("test_circuit_breaker_reset", test_circuit_breaker_reset);
    run_test("test_strategy_and_parameters", test_strategy_and_parameters);
    run_test("test_telemetry_and_ptp", test_telemetry_and_ptp);

    std::cout << "All C++20 UIO driver tests PASSED successfully!\n";
    return 0;
}
