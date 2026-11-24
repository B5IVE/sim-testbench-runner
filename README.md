# sim-testbench-runner

A zero-dependency Python 3.10+ CLI harness for **deterministic simulation testbenches, benchmark execution, wall-clock timing, and numeric metric regression checks**.

Built to orchestrate simulation or verification commands from a JSON/JSONL suite file, enforce exit codes and timeouts, flag numeric metric drift beyond tolerance bands, and output CI-ready JSON and Markdown reports.

## Capabilities

- **Command & Timeout Execution (`SIM-EXIT`, `SIM-TIMEOUT`):** Runs testbench commands deterministically with per-case timeout enforcement and expected exit code verification.
- **Numeric Metric Tolerance Gate (`SIM-METRIC`):** Compares `actual_metric` against `expected_metric` within `abs_tolerance` and rejects `NaN`/`Inf` values.
- **Duplicate Case Guard (`SIM-DUP`):** Flags duplicate `case_id` definitions in a suite.
- **Dual Output & CI Exit Codes:** Emits `sim_bench_report.json` and `sim_bench_summary.md`, exiting with code `1` on any `FAIL` result.

## Quickstart

Requires **Python 3.10+** (standard library only).

```bash
git clone [https://github.com/B5IVE/sim-testbench-runner.git](https://github.com/B5IVE/sim-testbench-runner.git)
cd sim-testbench-runner

python3 run_sim.py sample_suite.json
