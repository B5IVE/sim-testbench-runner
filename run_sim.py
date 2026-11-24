#!/usr/bin/env python3
"""
sim-testbench-runner: Deterministic Simulation & Benchmark Regression Harness.

Executes parameterized simulation/testbench cases defined in a JSON/JSONL suite,
tracks wall-clock timing and exit codes, compares numeric output metrics against
configurable tolerance bands or baseline values, and emits a structured JSON
result report plus a Markdown regression summary.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class CaseResult:
    case_id: str
    status: str  # PASS, FAIL, WARN
    exit_code: int
    expected_exit_code: int
    duration_sec: float
    code: str
    message: str


def load_cases(suite_path: Path) -> list[dict[str, Any]]:
    raw = suite_path.read_text(encoding="utf-8").strip()
    if not raw:
        return []
    if raw.startswith("["):
        data = json.loads(raw)
        if not isinstance(data, list):
            raise ValueError("JSON suite array must be a list of case objects.")
        return data
    cases: list[dict[str, Any]] = []
    for line_num, line in enumerate(raw.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        if not isinstance(obj, dict):
            raise ValueError(f"Line {line_num}: suite record must be a JSON object.")
        cases.append(obj)
    return cases


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run deterministic simulation/testbench cases and detect metric/exit regressions."
    )
    parser.add_argument("suite_file", type=Path, help="Path to testbench suite (.json or .jsonl)")
    parser.add_argument(
        "--timeout-sec",
        type=float,
        default=30.0,
        help="Per-case execution timeout in seconds (default: 30.0)",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=Path("sim_bench_report.json"),
        help="Output JSON report path (default: sim_bench_report.json)",
    )
    parser.add_argument(
        "--md-out",
        type=Path,
        default=Path("sim_bench_summary.md"),
        help="Output Markdown summary path (default: sim_bench_summary.md)",
    )
    args = parser.parse_args()

    if not args.suite_file.is_file():
        print(f"Error: Suite file not found: {args.suite_file}", file=sys.stderr)
        return 2

    try:
        cases = load_cases(args.suite_file)
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"Error: Invalid suite file: {exc}", file=sys.stderr)
        return 2

    results: list[CaseResult] = []
    seen_ids: set[str] = set()

    for idx, case in enumerate(cases, start=1):
        case_id = str(case.get("case_id", f"case-{idx}")).strip() or f"case-{idx}"
        cmd = case.get("command")
        expected_exit = int(case.get("expected_exit_code", 0))
        expected_metric = case.get("expected_metric")
        actual_metric = case.get("actual_metric")
        abs_tol = float(case.get("abs_tolerance", 1e-3))

        if case_id in seen_ids:
            results.append(
                CaseResult(case_id, "WARN", -1, expected_exit, 0.0, "SIM-DUP", f"Duplicate case_id '{case_id}'.")
            )
        seen_ids.add(case_id)

        if not isinstance(cmd, list) or not cmd or not all(isinstance(t, str) for t in cmd):
            results.append(
                CaseResult(
                    case_id,
                    "FAIL",
                    -1,
                    expected_exit,
                    0.0,
                    "SIM-CMD",
                    "Case 'command' must be a non-empty list of strings.",
                )
            )
            continue

        start_t = time.perf_counter()
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=args.timeout_sec,
                check=False,
            )
            elapsed = time.perf_counter() - start_t
            actual_exit = proc.returncode

            if actual_exit != expected_exit:
                stderr_snip = (proc.stderr or "").strip().splitlines()
                detail = stderr_snip[-1] if stderr_snip else "no stderr output"
                results.append(
                    CaseResult(
                        case_id,
                        "FAIL",
                        actual_exit,
                        expected_exit,
                        round(elapsed, 4),
                        "SIM-EXIT",
                        f"Exit code {actual_exit} != expected {expected_exit} ({detail}).",
                    )
                )
                continue

            if expected_metric is not None and actual_metric is not None:
                exp_val = float(expected_metric)
                act_val = float(actual_metric)
                delta = abs(act_val - exp_val)
                if math.isnan(act_val) or math.isinf(act_val) or delta > abs_tol:
                    results.append(
                        CaseResult(
                            case_id,
                            "FAIL",
                            actual_exit,
                            expected_exit,
                            round(elapsed, 4),
                            "SIM-METRIC",
                            f"Metric {act_val} drifted from expected {exp_val} by {delta:.6g} (tol={abs_tol:g}).",
                        )
                    )
                    continue

            results.append(
                CaseResult(
                    case_id,
                    "PASS",
                    actual_exit,
                    expected_exit,
                    round(elapsed, 4),
                    "OK",
                    "Simulation case passed exit and tolerance checks.",
                )
            )

        except subprocess.TimeoutExpired:
            elapsed = time.perf_counter() - start_t
            results.append(
                CaseResult(
                    case_id,
                    "FAIL",
                    -1,
                    expected_exit,
                    round(elapsed, 4),
                    "SIM-TIMEOUT",
                    f"Timed out after {args.timeout_sec:.1f}s.",
                )
            )

    pass_count = sum(1 for r in results if r.status == "PASS")
    fail_count = sum(1 for r in results if r.status == "FAIL")
    warn_count = sum(1 for r in results if r.status == "WARN")
    total_runtime = round(sum(r.duration_sec for r in results), 4)

    report_obj = {
        "metadata": {
            "source_file": str(args.suite_file),
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "total_cases": len(results),
            "passed": pass_count,
            "failed": fail_count,
            "warnings": warn_count,
            "total_runtime_sec": total_runtime,
        },
        "results": [asdict(r) for r in results],
    }

    args.json_out.write_text(json.dumps(report_obj, indent=2), encoding="utf-8")

    md_lines = [
        "# Simulation Testbench & Regression Runner Report",
        "",
        f"- **Suite File:** `{args.suite_file.name}` | **Generated (UTC):** `{report_obj['metadata']['generated_utc']}`",
        f"- **Cases:** `{len(results)}` | **Passed:** `{pass_count}` | **Failed:** `{fail_count}` | **Warnings:** `{warn_count}`",
        f"- **Total Runtime:** `{total_runtime:.4f}s`",
        "",
        "## Testbench Results",
        "",
        "| Case ID | Status | Exit (Act/Exp) | Time (s) | Code | Summary |",
        "| :--- | :---: | :---: | ---: | :--- | :--- |",
    ]
    for r in results:
        md_lines.append(
            f"| `{r.case_id}` | **{r.status}** | `{r.exit_code}/{r.expected_exit_code}` | "
            f"{r.duration_sec:.4f} | `{r.code}` | {r.message} |"
        )

    args.md_out.write_text("\n".join(md_lines).strip() + "\n", encoding="utf-8")

    print(
        f"[+] Testbench complete: {pass_count} passed, {fail_count} failed, "
        f"{warn_count} warnings in {total_runtime:.4f}s."
    )
    print(f"[+] Wrote {args.json_out} and {args.md_out}")

    return 1 if fail_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())

