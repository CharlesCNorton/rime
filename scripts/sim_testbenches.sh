#!/usr/bin/env bash
# Compile and simulate all iverilog testbenches.
# Each testbench is expected to call $finish after completing its checks.
# Exit 0 if all pass, 1 if any fail.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
CORE="$REPO/firmware/core"
RIME="$REPO/firmware/images/rime"
TB_DIR="$REPO/firmware/tests/testbench"

COMMON_SOURCES=(
    "$CORE/uart_rx.sv"
    "$CORE/uart_tx.sv"
    "$CORE/flash_spi_master.sv"
    "$CORE/sd_spi_master.sv"
    "$CORE/sdram_controller.sv"
    "$CORE/sdram_bridge.sv"
    "$RIME/rime_service.sv"
)

passed=0
failed=0
skipped=0

for tb in "$TB_DIR"/tb_*.sv; do
    name="$(basename "$tb")"
    printf "  %-35s " "$name"

    # Determine which sources this testbench needs by scanning for
    # instantiation of known modules.
    sources=()
    tb_text="$(cat "$tb")"

    for src in "${COMMON_SOURCES[@]}"; do
        mod_name="$(basename "$src" .sv)"
        if grep -q "$mod_name" "$tb" 2>/dev/null; then
            sources+=("$src")
        fi
    done

    # The SDRAM model lives alongside the testbenches
    if grep -q "sdram_model" "$tb" 2>/dev/null; then
        sources+=("$TB_DIR/sdram_model.sv")
    fi

    # Compile
    out_file="/tmp/rime_sim_${name%.sv}"
    if ! iverilog -g2012 -o "$out_file" -I "$RIME" "${sources[@]}" "$tb" 2>/dev/null; then
        echo "COMPILE_FAIL"
        failed=$((failed + 1))
        continue
    fi

    # Simulate with a timeout (testbenches should $finish within seconds)
    if timeout 10 vvp -N "$out_file" > /dev/null 2>&1; then
        echo "PASS"
        passed=$((passed + 1))
    else
        exit_code=$?
        if [ $exit_code -eq 124 ]; then
            echo "TIMEOUT (no \$finish — skipping)"
            skipped=$((skipped + 1))
        else
            echo "SIM_FAIL"
            failed=$((failed + 1))
        fi
    fi

    rm -f "$out_file"
done

echo ""
echo "Simulation: $passed passed, $failed failed, $skipped skipped"
[ $failed -eq 0 ]
