CXX ?= g++
CXXFLAGS ?= -std=c++20 -O3 -Wall -Wextra -Werror -pedantic -Iinclude

BUILD_DIR = build
BIN_DIR = bin

TARGET_CLI = $(BIN_DIR)/aura-ctl
TARGET_TEST = $(BIN_DIR)/test_uio_driver

all: $(TARGET_CLI) $(TARGET_TEST)

$(BIN_DIR):
	mkdir -p $(BIN_DIR)

$(TARGET_CLI): src/main_cli.cpp include/aura_hft_driver.hpp include/aura_uio_device.hpp | $(BIN_DIR)
	$(CXX) $(CXXFLAGS) $< -o $@

$(TARGET_TEST): tests/test_uio_driver.cpp include/aura_hft_driver.hpp include/aura_uio_device.hpp | $(BIN_DIR)
	$(CXX) $(CXXFLAGS) $< -o $@

test: $(TARGET_TEST)
	./$(TARGET_TEST)

clean:
	rm -rf $(BIN_DIR)

.PHONY: all test clean
