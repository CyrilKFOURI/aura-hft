#include "aura_hft_driver.hpp"
#include <iostream>
#include <iomanip>
#include <string>
#include <cstring>

using namespace aura::driver;

void print_usage(const char* prog_name) {
    std::cout << "Usage: " << prog_name << " [options] <command>\n\n"
              << "Options:\n"
              << "  --mock               Run against an in-memory mock device (for testing without FPGA)\n"
              << "  --device <path>      Specify UIO device path (default: /dev/uio0)\n\n"
              << "Commands:\n"
              << "  status               Display live hardware telemetry and status flags\n"
              << "  kill                 ENGAGE HARDWARE KILL-SWITCH (Stops all order emission)\n"
              << "  unkill               Disengage kill-switch (Resume trading)\n"
              << "  reset-breaker        Manually reset tripped PnL Circuit Breaker\n"
              << "  enable               Enable trading pipeline\n"
              << "  disable              Disable trading pipeline\n"
              << "  soft-reset           Issue single-cycle soft reset pulse to PL core\n"
              << "  set-strategy <obi|as> Set quantitative strategy mode\n";
}

int main(int argc, char* argv[]) {
    bool use_mock = false;
    std::string dev_path = "/dev/uio0";
    std::string command;
    std::string arg1;

    for (int i = 1; i < argc; ++i) {
        if (std::strcmp(argv[i], "--mock") == 0) {
            use_mock = true;
        } else if (std::strcmp(argv[i], "--device") == 0 && i + 1 < argc) {
            dev_path = argv[++i];
        } else if (command.empty()) {
            command = argv[i];
        } else if (arg1.empty()) {
            arg1 = argv[i];
        }
    }

    if (command.empty() || command == "help" || command == "-h" || command == "--help") {
        print_usage(argv[0]);
        return 0;
    }

    try {
        std::unique_ptr<AuraHftDriver> drv;
        if (use_mock) {
            drv = AuraHftDriver::open_mock();
            std::cout << "[INFO] Running in MOCK mode (simulated PL registers)\n";
        } else {
            drv = AuraHftDriver::open(dev_path);
        }

        if (command == "status") {
            auto tele = drv->read_telemetry();
            auto ptp = drv->read_ptp_timestamp();

            std::cout << "========================================================\n"
                      << "  AURA-HFT FPGA Hardware Telemetry Snapshot (KR260)\n"
                      << "========================================================\n"
                      << "Pipeline Ready      : " << (tele.flags.pipeline_ready ? "YES" : "NO") << "\n"
                      << "BBO Valid           : " << (tele.flags.bbo_valid ? "YES" : "NO") << "\n"
                      << "Risk Reject Active  : " << (tele.flags.risk_reject ? "YES" : "NO") << "\n"
                      << "Kill Switch Engaged : " << (tele.flags.kill_switch_engaged ? "YES (BLOCKED)" : "NO") << "\n"
                      << "Breaker Tripped     : " << (tele.flags.circuit_breaker_tripped ? "TRIPPED" : "OK") << "\n"
                      << "--------------------------------------------------------\n"
                      << "Ingress Packets     : " << tele.ingress_count << "\n"
                      << "Egress Orders       : " << tele.egress_count << "\n"
                      << "Current Inventory   : " << tele.current_inventory << " shares\n"
                      << "Mark-to-Market PnL  : $" << std::fixed << std::setprecision(2) << (tele.mtm_pnl / 10000.0) << "\n"
                      << "Max Drawdown        : $" << std::fixed << std::setprecision(2) << (tele.drawdown / 10000.0) << "\n"
                      << "Last Latency        : " << tele.last_latency_cycles << " cycles (" << (tele.last_latency_cycles * 3.2) << " ns)\n"
                      << "FCS Error Count     : " << tele.fcs_error_count << "\n"
                      << "PTP Timestamp       : " << ptp.seconds << "s " << ptp.nanoseconds << "ns\n"
                      << "========================================================\n";
        } else if (command == "kill") {
            drv->arm_kill_switch();
            std::cout << "[EMERGENCY] Hardware Kill-Switch ENGAGED in PL core.\n";
        } else if (command == "unkill") {
            drv->disarm_kill_switch();
            std::cout << "[INFO] Hardware Kill-Switch DISARMED. Normal trading active.\n";
        } else if (command == "reset-breaker") {
            drv->reset_circuit_breaker();
            std::cout << "[INFO] Circuit Breaker reset pulse sent.\n";
        } else if (command == "enable") {
            drv->set_pipeline_enable(true);
            std::cout << "[INFO] Trading pipeline enabled.\n";
        } else if (command == "disable") {
            drv->set_pipeline_enable(false);
            std::cout << "[INFO] Trading pipeline disabled.\n";
        } else if (command == "soft-reset") {
            drv->trigger_soft_reset();
            std::cout << "[INFO] PL soft-reset issued.\n";
        } else if (command == "set-strategy") {
            if (arg1 == "as" || arg1 == "avellaneda") {
                drv->set_strategy(StrategyMode::AVELLANEDA_STOIKOV);
                std::cout << "[INFO] Active Strategy set to AVELLANEDA_STOIKOV.\n";
            } else if (arg1 == "obi") {
                drv->set_strategy(StrategyMode::OBI_THRESHOLD);
                std::cout << "[INFO] Active Strategy set to OBI_THRESHOLD.\n";
            } else {
                std::cerr << "Unknown strategy: " << arg1 << " (expected 'obi' or 'as')\n";
                return 1;
            }
        } else {
            std::cerr << "Unknown command: " << command << "\n";
            print_usage(argv[0]);
            return 1;
        }

    } catch (const std::exception& e) {
        std::cerr << "Error: " << e.what() << "\n";
        return 1;
    }

    return 0;
}
