# AURA-HFT — single entry point for build, test and lint.
# Run natively (Linux + Verilator 5) or in Docker: `make docker-test`.

PYTHON  ?= python3
PYTEST  := PYTHONPATH=. $(PYTHON) -m pytest -q
IMAGE   := aura-hft-ci
RTL_INC := rtl/include
RTL_PKG := $(RTL_INC)/itch_pkg.sv $(RTL_INC)/lob_pkg.sv $(RTL_INC)/ouch_pkg.sv
RTL_SRC := $(filter-out $(RTL_PKG),$(wildcard rtl/*/*.sv))
RTL_TOPS := aura_hft_top aura_hft_dual_clock_top multi_ticker_pipeline_top cross_exchange_pipeline_top
LINT_FLAGS := --lint-only -Wall -Wno-DECLFILENAME -Wno-UNUSED -Wno-MULTITOP -Wno-PINCONNECTEMPTY -I$(RTL_INC)

ITCH_DATE ?= 01302019
ITCH_MSGS ?= 20000000
ITCH_FILE := data/cache/$(ITCH_DATE).NASDAQ_ITCH50.first$(ITCH_MSGS).itch

.PHONY: test-software fetch-data fetch-iex validate-real test test-golden test-rtl test-server test-driver test-robustness test-iex coverage formal lint lint-rtl lint-py typecheck docker-build docker-test docker-formal clean

test: test-golden test-server test-driver test-software test-rtl

test-software:
	$(MAKE) -C software/ref_pipeline test

test-golden:
	$(PYTEST) sim/tests/test_golden_model.py sim/tests/test_real_data_meatpy.py

test-server:
	$(PYTEST) server/tests

test-driver:
	$(MAKE) -C driver test
	$(PYTEST) sim/tests/test_driver_uio.py

test-rtl:
	$(PYTEST) $(filter-out sim/tests/test_golden_model.py sim/tests/test_driver_uio.py sim/tests/test_real_data_meatpy.py sim/tests/test_real_data_rtl.py sim/tests/test_iex_framing.py,$(wildcard sim/tests/test_*.py))

fetch-data: $(ITCH_FILE)

# --- Step P3b: robustness (fault injection, real IEX framing, coverage, formal)
IEX_DATE   ?= 20190130
IEX_FRAMES ?= 5000
FORMAL_IMAGE := aura-hft-formal

fetch-iex:
	$(PYTHON) data/fetch_iex.py --date $(IEX_DATE) --packets $(IEX_FRAMES)

test-robustness:
	$(PYTEST) sim/tests/test_fault_injection.py sim/tests/test_fcs_top.py sim/tests/test_risk_assertions.py

# Skipped (not failed) when data/cache has no IEX pcap or no AAPL stream.
test-iex:
	IEX_FRAMES=$(IEX_FRAMES) $(PYTEST) sim/tests/test_iex_framing.py

# Line + toggle coverage of itch_lob_pipeline_top under the fault-injection bench.
coverage:
	rm -rf sim/build/fault_cov
	RTL_COVERAGE=1 $(PYTEST) sim/tests/test_fault_injection.py
	verilator_coverage --write sim/build/fault_cov/merged.dat sim/build/fault_cov/coverage_*.dat
	verilator_coverage --annotate sim/build/fault_cov/annotated sim/build/fault_cov/merged.dat
	PYTHONPATH=. $(PYTHON) -m sim.validation.coverage_summary sim/build/fault_cov/merged.dat --out sim/build/fault_cov/summary.md

# Needs yosys (formal/Dockerfile); run in Docker with `make docker-formal`.
formal:
	sh formal/run_risk_formal.sh

$(ITCH_FILE):
	$(PYTHON) data/fetch.py --date $(ITCH_DATE) --messages $(ITCH_MSGS)

validate-real: $(ITCH_FILE)
	PYTHONPATH=. $(PYTHON) -m sim.validation.itch_stats $(ITCH_FILE) --out reports/itch_stats_$(ITCH_DATE).md
	PYTHONPATH=. $(PYTHON) -m sim.validation.compare_meatpy $(ITCH_FILE) --symbols AAPL MSFT QQQ NVDA TSLA SAP 		--out reports/golden_vs_meatpy_$(ITCH_DATE).md

lint: lint-rtl lint-py

lint-rtl:
	@set -e; for top in $(RTL_TOPS); do \
		echo "verilator lint: $$top"; \
		verilator $(LINT_FLAGS) --top-module $$top $(RTL_PKG) $(RTL_SRC); \
	done

lint-py:
	ruff check sim server software

typecheck:
	mypy server

docker-build:
	docker build -t $(IMAGE) .

docker-test: docker-build
	docker run --rm -v "$(CURDIR)":/work $(IMAGE) make test lint

docker-formal: docker-build
	docker build -t $(FORMAL_IMAGE) -f formal/Dockerfile formal
	docker run --rm -v "$(CURDIR)":/work -w /work $(FORMAL_IMAGE) make formal

clean:
	rm -rf sim/build sim_build obj_dir results.xml
	$(MAKE) -C driver clean
