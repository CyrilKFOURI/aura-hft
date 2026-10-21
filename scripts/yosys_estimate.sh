#!/bin/sh
# Resource estimate with Yosys (step P5a) -- NOT Vivado, no timing.
#
# Installs nothing on the host: runs in a throwaway container from the
# aura-hft-ci image (Ubuntu 24.04), apt-installs yosys inside it, converts
# the SystemVerilog to Verilog-2005 with sv2v (Yosys 0.33 cannot parse our
# packages / packed structs), then runs `synth_xilinx -family xcup`
# (UltraScale+) on the requested top. The SAT-based `share` pass of the
# coarse stage is skipped (it exhausts 15 GB on this design); everything else
# is the stock synth_xilinx script. -noiopad: the block is not a chip top.
#
#   scripts/yosys_estimate.sh [top]
#   FILES="..." scripts/yosys_estimate.sh aura_hft_top
#
# Output: reports/yosys_<top>.log (full log), reports/yosys_<top>_stat.txt.
set -eu

TOP=${1:-lob_engine_top}
IMAGE=${IMAGE:-aura-hft-ci}
SV2V_VERSION=${SV2V_VERSION:-v0.0.13}
cd "$(dirname "$0")/.."
HOSTDIR=$(pwd -W 2>/dev/null || pwd)

# Files needed by lob_engine_top (packages first). Override with FILES=...
FILES=${FILES:-"rtl/include/itch_pkg.sv rtl/include/lob_pkg.sv rtl/include/ouch_pkg.sv rtl/book/order_store.sv rtl/book/depth_book.sv rtl/book/top_of_book_cache.sv rtl/book/lob_engine_top.sv"}

mkdir -p reports
MSYS_NO_PATHCONV=1 docker run --rm -v "$HOSTDIR":/work -w /work "$IMAGE" sh -c "
  set -e
  (apt-get update -qq && apt-get install -y -qq --no-install-recommends yosys curl unzip) > /dev/null 2>&1
  curl -sSL -o /tmp/sv2v.zip https://github.com/zachjs/sv2v/releases/download/${SV2V_VERSION}/sv2v-Linux.zip
  unzip -q -o /tmp/sv2v.zip -d /tmp/sv2v
  yosys -V
  /tmp/sv2v/sv2v-Linux/sv2v --version
  mkdir -p build/yosys
  /tmp/sv2v/sv2v-Linux/sv2v -DSYNTHESIS -I rtl/include --top=${TOP} ${FILES} > build/yosys/${TOP}.v
  # sv2v lists memories in always_comb sensitivity lists, which Yosys rejects:
  # use @(*) instead (same combinational semantics for synthesis).
  perl -pi -e 's/^(\s*)always @\((?!posedge|negedge).*\) begin/\1always @(*) begin/' build/yosys/${TOP}.v
  yosys -q -l reports/yosys_${TOP}.log -p '
    read_verilog build/yosys/${TOP}.v;
    synth_xilinx -family xcup -top ${TOP} -flatten -noiopad -run :coarse;
    techmap -map +/cmp2lut.v -map +/cmp2lcu.v -D LUT_WIDTH=6;
    alumacc; opt; memory -nomap; opt_clean;
    synth_xilinx -family xcup -top ${TOP} -flatten -noiopad -run map_memory:;
    tee -o reports/yosys_${TOP}_stat.txt stat' > /dev/null
  cat reports/yosys_${TOP}_stat.txt
"
