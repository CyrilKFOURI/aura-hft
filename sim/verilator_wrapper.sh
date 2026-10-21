#!/bin/bash
export VERILATOR_ROOT=/usr/local/lib/python3.10/dist-packages/verilator
export PATH=$VERILATOR_ROOT/bin:$PATH
exec perl $VERILATOR_ROOT/bin/verilator "$@"
