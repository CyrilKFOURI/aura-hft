#!/bin/sh
# Formal proof of the pre-trade risk safety properties (step P3b).
#   docker build -t aura-hft-formal -f formal/Dockerfile formal
#   docker run --rm -v "$PWD":/work -w /work aura-hft-formal sh formal/run_risk_formal.sh
#
# Engine: yosys `sat -tempinduct` (bit-level SAT): base case = BMC from reset,
# then temporal k-induction, increasing k up to DEPTH. "SUCCESS" = the
# properties hold in every reachable state (unbounded proof), every input free
# at every cycle. sby is not packaged for Ubuntu 24.04, and its smtbmc back-end
# with the Ubuntu z3 / boolector builds did not complete step 0 in 10 min here.
#
# Abstraction (sound, stated in reports/robustness.md): the 32x32 notional
# product is a free value (cutpoint). The checker computes the notional with
# the very same expression, so after flattening opt_merge folds both into one
# $mul cell (asserted below) and one cut point feeds both. The properties are
# thus proved for ANY notional value, which covers the real product; the
# multiplier's arithmetic itself (a DSP48E2) is not part of this proof.
#
# Non-vacuity: each mutant below removes one check from a copy of the RTL and
# MUST be refuted (counterexample found), otherwise the run fails.
set -e
DEPTH=${DEPTH:-10}
OUT=sim/build/formal_risk
mkdir -p $OUT

# prove <tag> <extra sed expression or empty>  -> returns 0 when proved
prove() {
    dir=$OUT/$1
    mkdir -p $dir
    # yosys 0.33 rejects package imports: package-qualified names in a build-local copy
    sed -e '/^ *import ouch_pkg::\*;/d' -e 's/\bRISK_/ouch_pkg::RISK_/g' ${2:+-e "$2"} \
        rtl/risk/pre_trade_risk.sv > $dir/pre_trade_risk_formal.sv
    yosys -q -l $dir/yosys.log -p "
      read_verilog -sv -formal -I rtl/include rtl/include/ouch_pkg.sv $dir/pre_trade_risk_formal.sv rtl/assertions/pre_trade_risk_props.sv formal/risk_formal_top.sv
      prep -top risk_formal_top
      flatten
      opt_merge
      select -assert-count 1 t:\$mul
      cutpoint t:\$mul
      async2sync
      dffunmap
      setundef -anyseq
      opt -keepdc -fast
      dffunmap
      sat -tempinduct -prove-asserts -set-assumes -maxsteps $DEPTH -dump_vcd $dir/cex.vcd -show-public risk_formal_top
    " > /dev/null 2>&1 || true
    grep -q "Induction step proven: SUCCESS!" $dir/yosys.log
}

echo "== proof: pre_trade_risk + pre_trade_risk_props (k <= $DEPTH)"
if prove main ""; then
    grep -E "Induction step proven|Base case for induction length [0-9]+ proven" $OUT/main/yosys.log | tail -2
    echo "PROOF PASS"
else
    grep -E "FAIL|failed" $OUT/main/yosys.log | tail -3
    echo "PROOF FAIL (trace: $OUT/main/cex.vcd)"; exit 1
fi

echo "== non-vacuity mutants (each must FAIL)"
status=0
for m in \
    "kill_stage_b:s/if (a_kill || cfg_kill_switch) begin/if (a_kill) begin/" \
    "kill_stage_a:s/if (a_kill || cfg_kill_switch) begin/if (cfg_kill_switch) begin/" \
    "max_shares:s/end else if (a_max_shares) begin/end else if (1'b0) begin/" \
    "collar:s/end else if (a_collar) begin/end else if (1'b0) begin/" \
    "max_notional:s/end else if (notional_violation) begin/end else if (1'b0) begin/" \
    "cum_notional:s/end else if (cum_notional_violation) begin/end else if (1'b0) begin/" \
    "cum_wrap:s/(cum_sum > {1'b0, cfg_max_cum_notional_raw})/(cum_sum[63:0] > cfg_max_cum_notional_raw)/" \
    "strobes:s/risk_rejected         <= 1'b1;/risk_rejected         <= 1'b1; risk_approved <= 1'b1;/"
do
    tag=${m%%:*}; expr=${m#*:}
    if prove mut_$tag "$expr"; then echo "  $tag: NOT refuted (vacuous!)"; status=1; else echo "  $tag: refuted"; fi
done
[ $status -eq 0 ] && echo "FORMAL PASS" || { echo "FORMAL FAIL (vacuous property)"; exit 1; }
