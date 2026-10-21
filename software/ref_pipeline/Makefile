# Software reference path (step P6). g++ >= 13 (C++20), Linux for CPU pinning.
CXX ?= g++
CXXFLAGS ?= -std=c++20 -O3 -march=native -Wall -Wextra -Werror -pedantic -Iinclude
BIN := bin
HDRS := include/ref_pipeline.hpp include/latency_hist.hpp

all: $(BIN)/aura_ref $(BIN)/test_ref_pipeline

$(BIN):
	mkdir -p $(BIN)

$(BIN)/aura_ref: src/main.cpp $(HDRS) | $(BIN)
	$(CXX) $(CXXFLAGS) $< -o $@

$(BIN)/test_ref_pipeline: tests/test_ref_pipeline.cpp $(HDRS) | $(BIN)
	$(CXX) $(CXXFLAGS) $< -o $@

test: $(BIN)/test_ref_pipeline
	./$(BIN)/test_ref_pipeline

clean:
	rm -rf $(BIN)

.PHONY: all test clean
