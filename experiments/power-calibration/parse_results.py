#!/usr/bin/env python3
"""Parse power calibration UART output and derive per-cell-type power coefficients.

The calibration device outputs 8 bytes per sensor per phase:
  [0x50, phase, sensor, freq_hi, freq_mid, freq_lo, dtr, 0x0A]

8 phases × 8 sensors = 64 records.

Thermal model (2D steady-state heat conduction on silicon slab):
  T(sensor) = T_ambient + Σ_zones [ P_zone × G(r_sz) ]
  G(r) = 1/(2π κ t) × ln(R_die / r)    (Green's function, thin slab)

where:
  κ = 148 W/(m·K)  — silicon thermal conductivity
  t = 300 μm       — die thickness (typical thinned die)
  R_die = 5 mm     — effective die radius

Ring oscillator frequency decreases with temperature:
  f(T) = f_ref × (1 - α × (T - T_ref))
  α ≈ 0.0004 /°C   — CMOS ring osc temperature coefficient

Solving:
  For each phase p, the measured frequency of sensor s is:
    f_ps = f_ref × (1 - α × ΔT_ps)
  where ΔT_ps = Σ_z [ N_z(p) × P_lut × G(d(s,z)) ]
    N_z(p) = number of active LUTs in zone z during phase p
    d(s,z) = Euclidean distance from sensor s to zone z center

  From the idle phase (p=0), f_ref = f_0s for each sensor s.
  Then: ΔT_ps = (1 - f_ps/f_0s) / α

  Linear regression on ΔT_ps vs the zone configuration matrix
  gives P_lut (power per LUT at 50% toggle rate, CLK/2).
"""

import sys
import subprocess
import json
import math

KAPPA = 148.0
DIE_THICKNESS = 300e-6
DIE_RADIUS = 5e-3
ALPHA = 0.0004
THETA_JA = 20.0
LUTS_PER_ZONE = 500
CLK_HZ = 25e6
TOGGLE_RATE = 0.5

COL_PITCH = 0.066
ROW_PITCH = 0.132

ZONE_CENTERS = {
    0: (10, 10),
    1: (10, 85),
    2: (40, 10),
    3: (40, 85),
}

SENSOR_POS = {
    0: (10, 10),
    1: (10, 85),
    2: (40, 10),
    3: (40, 85),
    4: (10, 48),
    5: (40, 48),
    6: (25, 10),
    7: (25, 48),
}

PHASE_ZONES = {
    0: [],
    1: [0],
    2: [1],
    3: [2],
    4: [3],
    5: [0, 2],
    6: [1, 3],
    7: [0, 1, 2, 3],
}

NUM_PHASES = 8
NUM_SENSORS = 8


def distance_mm(s_id, z_id):
    """Euclidean distance in mm between sensor s and zone z center."""
    sr, sc = SENSOR_POS[s_id]
    zr, zc = ZONE_CENTERS[z_id]
    dr = (sr - zr) * ROW_PITCH
    dc = (sc - zc) * COL_PITCH
    return math.sqrt(dr**2 + dc**2)


def green_function(r_mm):
    """Thermal Green's function for thin slab point source. Returns °C/W."""
    r = max(r_mm * 1e-3, 0.1e-3)
    return math.log(DIE_RADIUS / r) / (2 * math.pi * KAPPA * DIE_THICKNESS)


def parse_uart_data(filename):
    """Parse binary UART output into records."""
    with open(filename, "rb") as f:
        raw = f.read()

    records = []
    i = 0
    while i < len(raw) - 7:
        if raw[i] == 0x50 and raw[i + 7] == 0x0A:
            phase = raw[i + 1] & 0x0F
            sensor = raw[i + 2] & 0x0F
            freq = (raw[i + 3] << 16) | (raw[i + 4] << 8) | raw[i + 5]
            dtr = raw[i + 6]
            records.append((phase, sensor, freq, dtr))
            i += 8
        else:
            i += 1

    return records


def compute_coefficients(records):
    """Derive per-cell-type power from calibration data."""
    data = {}
    for phase, sensor, freq, dtr in records:
        data[(phase, sensor)] = (freq, dtr)

    if not data:
        print("No calibration data found.")
        return None

    f_ref = {}
    for s in range(NUM_SENSORS):
        if (0, s) in data:
            f_ref[s] = data[(0, s)][0]

    if len(f_ref) < NUM_SENSORS:
        print(f"Missing idle reference for {NUM_SENSORS - len(f_ref)} sensors")
        return None

    delta_t = {}
    for phase in range(1, NUM_PHASES):
        for s in range(NUM_SENSORS):
            if (phase, s) not in data or s not in f_ref:
                continue
            f_ps = data[(phase, s)][0]
            if f_ref[s] > 0:
                delta_t[(phase, s)] = (1.0 - f_ps / f_ref[s]) / ALPHA

    A_rows = []
    b_rows = []
    for phase in range(1, NUM_PHASES):
        active_zones = PHASE_ZONES[phase]
        for s in range(NUM_SENSORS):
            if (phase, s) not in delta_t:
                continue
            g_sum = sum(
                LUTS_PER_ZONE * green_function(distance_mm(s, z))
                for z in active_zones
            )
            A_rows.append(g_sum)
            b_rows.append(delta_t[(phase, s)])

    if not A_rows:
        print("Insufficient data for regression")
        return None

    num = sum(a * b for a, b in zip(A_rows, b_rows))
    den = sum(a * a for a in A_rows)
    p_lut = num / den if den > 0 else 0

    dtr_idle = sum(data[(0, s)][1] for s in range(NUM_SENSORS) if (0, s) in data) / NUM_SENSORS
    dtr_all = sum(data[(7, s)][1] for s in range(NUM_SENSORS) if (7, s) in data) / NUM_SENSORS
    dtr_delta = dtr_all - dtr_idle
    p_total_dtr = dtr_delta / THETA_JA if THETA_JA > 0 else 0
    p_lut_dtr = p_total_dtr / (4 * LUTS_PER_ZONE) if (4 * LUTS_PER_ZONE) > 0 else 0

    return {
        "p_lut_ring_w": p_lut,
        "p_lut_ring_uw_per_mhz": p_lut * 1e6 / (CLK_HZ / 1e6) / TOGGLE_RATE,
        "p_lut_dtr_w": p_lut_dtr,
        "p_lut_dtr_uw_per_mhz": p_lut_dtr * 1e6 / (CLK_HZ / 1e6) / TOGGLE_RATE if p_lut_dtr else 0,
        "dtr_idle": dtr_idle,
        "dtr_all_active": dtr_all,
        "dtr_delta": dtr_delta,
        "equations": len(A_rows),
        "residual_rms_C": math.sqrt(
            sum((a * p_lut - b) ** 2 for a, b in zip(A_rows, b_rows)) / len(A_rows)
        ) if A_rows else 0,
    }


def run_wolframscript(coefficients):
    """Use WolframScript to compute derived quantities and cross-validate."""
    wolfram = r"C:\Program Files\Wolfram Research\WolframScript\wolframscript.exe"

    p = coefficients["p_lut_ring_uw_per_mhz"]
    script = f"""
    (* Power calibration analysis *)
    pLutMeasured = {p}; (* μW/MHz per LUT at 50% toggle *)

    (* Lattice published: 4.25 μW static + 6.0 μW/MHz dynamic at 12.5% toggle *)
    pLutLatticeStatic = 4.25;
    pLutLatticeDynamic = 6.0;
    latticeToggle = 0.125;

    (* Scale Lattice dynamic to 50% toggle for comparison *)
    pLutLatticeDyn50 = pLutLatticeDynamic * (0.5 / latticeToggle);

    (* Correction factor *)
    correction = If[pLutMeasured > 0, pLutLatticeDyn50 / pLutMeasured, 1.0];

    (* Calibrated coefficients for nosis/power.py *)
    calibrated = <|
        "lut_static_uw" -> pLutLatticeStatic,
        "lut_dynamic_uw_per_mhz" -> If[pLutMeasured > 0, pLutMeasured, pLutLatticeDyn50],
        "ff_dynamic_uw_per_mhz" -> 3.5 * correction,
        "ccu2c_dynamic_uw_per_mhz" -> 13.0 * correction,
        "dp16kd_dynamic_uw_per_mhz" -> 85.0 * correction,
        "mult18x18d_dynamic_uw_per_mhz" -> 200.0 * correction,
        "correction_factor" -> correction,
        "measurement_method" -> "ring_oscillator_thermal_tomography"
    |>;

    ExportString[calibrated, "JSON"]
    """

    try:
        result = subprocess.run(
            [wolfram, "-code", script],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            return json.loads(result.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError) as e:
        print(f"WolframScript unavailable ({e}), using Python fallback")

    lattice_dyn_50 = 6.0 * (0.5 / 0.125)
    correction = lattice_dyn_50 / p if p > 0 else 1.0
    return {
        "lut_static_uw": 4.25,
        "lut_dynamic_uw_per_mhz": p if p > 0 else lattice_dyn_50,
        "ff_dynamic_uw_per_mhz": 3.5 * correction,
        "ccu2c_dynamic_uw_per_mhz": 13.0 * correction,
        "dp16kd_dynamic_uw_per_mhz": 85.0 * correction,
        "mult18x18d_dynamic_uw_per_mhz": 200.0 * correction,
        "correction_factor": correction,
        "measurement_method": "ring_oscillator_thermal_tomography",
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: parse_results.py <uart_capture.bin>")
        print("       parse_results.py --simulate  (generate synthetic data for testing)")
        return

    if sys.argv[1] == "--simulate":
        print("Generating synthetic calibration data...")
        p_lut_true = 12e-6

        records = []
        for phase in range(NUM_PHASES):
            active = PHASE_ZONES[phase]
            for s in range(NUM_SENSORS):
                dt = sum(
                    LUTS_PER_ZONE * p_lut_true * green_function(distance_mm(s, z))
                    for z in active
                )
                f_ref = 400e6
                f_ps = f_ref * (1 - ALPHA * dt)
                freq = int(f_ps / CLK_HZ * (CLK_HZ / 2))
                dtr = int(25 + dt)
                records.append((phase, s, freq, dtr))

        coefficients = compute_coefficients(records)
        print(json.dumps(coefficients, indent=2))
        print()
        calibrated = run_wolframscript(coefficients)
        print("Calibrated coefficients:")
        print(json.dumps(calibrated, indent=2))
        return

    records = parse_uart_data(sys.argv[1])
    print(f"Parsed {len(records)} records")

    coefficients = compute_coefficients(records)
    if coefficients:
        print(json.dumps(coefficients, indent=2))
        print()
        calibrated = run_wolframscript(coefficients)
        print("Calibrated coefficients for nosis/power.py:")
        print(json.dumps(calibrated, indent=2))


if __name__ == "__main__":
    main()
