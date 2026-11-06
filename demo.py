#!/usr/bin/env python3
"""Two execution-based PromQL counterexamples. Requires promtool on PATH."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def series(pod, values, status=None):
    labels = f'pod="{pod}"'
    if status is not None:
        labels += f',status="{status}"'
    return {"series": f"http_requests_total{{{labels}}}", "values": " ".join(map(str, values))}


def traffic(rates):
    # One scrape per minute. Keep each series' rate constant within a scenario.
    return [series(pod, [60 * rate * minute for minute in range(5)], status)
            for pod, status, rate in rates]


def counter_cases():
    other = series("b", [0, 240, 480, 720, 960])
    return [
        ("No restart", [series("a", [0, 60, 120, 180, 240]), other], 5, 5),
        ("One pod restarted", [series("a", [0, 60, 120, 180, 60]), other], 5, 2),
    ]


def error_cases():
    balanced = [("a", "200", 99), ("a", "500", 1), ("b", "200", 50), ("b", "500", 50)]
    skewed = [("a", "200", 891), ("a", "500", 9), ("b", "200", 50), ("b", "500", 50)]
    return [
        ("Equal traffic", traffic(balanced), 25.5, 25.5),
        ("Nine times more traffic on pod a", traffic(skewed), 5.9, 25.5),
    ]


ERRORS = 'rate(http_requests_total{status="500"}[2m])'
TOTAL = 'rate(http_requests_total[2m])'
CASES = {
    "restart": {
        "prompt": "http_requests_total is a counter, one series per pod, scraped every minute. "
                  "Give the current service-wide requests per second from the last two samples, "
                  "accounting for independent pod restarts. Return one unlabeled instant-vector sample.",
        "reference": "sum(irate(http_requests_total[2m]))",
        "alternative": "irate((sum(http_requests_total))[2m:1m])",
        "unit": "req/s",
        "scenarios": counter_cases,
    },
    "errors": {
        "prompt": "http_requests_total is a counter with pod and status labels, scraped every minute. "
                  "Statuses are 200 and 500. What percentage of all service requests returned 500 "
                  "over the last two minutes? Return one unlabeled instant-vector sample on a 0-100 scale.",
        "reference": f"100 * sum({ERRORS}) / sum({TOTAL})",
        "alternative": f"100 * avg(sum by (pod) ({ERRORS}) / sum by (pod) ({TOTAL}))",
        "unit": "%",
        "scenarios": error_cases,
    },
}


def assertion(expression, value):
    return {"expr": expression, "eval_time": "4m", "exp_samples": [{"labels": "{}", "value": value}]}


def check(binary, suites):
    # JSON is also valid YAML. Pass PromQL as data and use the native query engine.
    with tempfile.TemporaryDirectory() as tmp:
        fixture = Path(tmp) / "cases.yml"
        fixture.write_text(json.dumps({"evaluation_interval": "1m", "tests": suites}))
        return subprocess.run([binary, "test", "rules", str(fixture)], stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True, check=False)


def run(args):
    if args.prompt:
        print(CASES[args.prompt]["prompt"])
        return 0
    if args.query and not args.case:
        raise ValueError("--query requires --case so the query is checked against the right task")
    binary = os.environ.get("PROMTOOL", "promtool")
    if not shutil.which(binary):
        raise ValueError("promtool not found. Install it or set PROMTOOL to its executable path.")
    failures = 0
    suites = []
    lines = []
    case_names = [args.case] if args.case else CASES
    for name in case_names:
        case = CASES[name]
        lines.append(f"\n{name} ({case['unit']})")
        for label, data, expected, alternative in case["scenarios"]():
            suite = {"interval": "1m", "input_series": data}
            if args.query:
                suite["promql_expr_test"] = [assertion(args.query, expected)]
                result = check(binary, [suite])
                if result.returncode:
                    print(f"FAIL: {label} (expected {expected:g} {case['unit']})", flush=True)
                    print(result.stdout.strip(), flush=True)
                    failures += 1
                else:
                    print(f"PASS: {label} ({expected:g} {case['unit']})", flush=True)
            else:
                suite["promql_expr_test"] = [assertion(case["reference"], expected),
                                             assertion(case["alternative"], alternative)]
                lines.append(f"  {label}: reference {expected:g} | alternative {alternative:g}")
                suites.append(suite)
    if args.query:
        return int(failures > 0)
    result = check(binary, suites)
    if result.returncode:
        print(result.stdout, file=sys.stderr)
        return result.returncode
    print("Verified by promtool." + "\n".join(lines))
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=CASES, help="Run just one experiment")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--prompt", choices=CASES, help="Print a task to give to a model")
    group.add_argument("--query", help="Check your own PromQL against both traffic scenarios")
    args = parser.parse_args()
    try:
        sys.exit(run(args))
    except (ValueError, OSError) as error:
        parser.exit(2, f"{error}\n")
