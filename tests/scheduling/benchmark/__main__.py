"""Benchmark and validate the EOS schedulers: python -m tests.scheduling.benchmark --help"""

import argparse
import asyncio
import logging
import sys

from eos.logging.logger import log
from tests.scheduling.benchmark.harness import SCENARIOS, SCHEDULERS, run_scenario


async def main() -> int:
    parser = argparse.ArgumentParser(description="Run the EOS schedulers on benchmark workloads and check them.")
    parser.add_argument("--scenarios", nargs="*", help="Run only scenarios whose name starts with one of these")
    parser.add_argument("--sizes", nargs="*", help="Run only these sizes (small, medium, large, features)")
    parser.add_argument("--schedulers", nargs="*", choices=list(SCHEDULERS), default=list(SCHEDULERS))
    parser.add_argument("--cpsat-time-limit", type=float, help="CP-SAT time limit per solve in seconds")
    args = parser.parse_args()

    log.set_level("ERROR")
    logging.getLogger("rich").setLevel(logging.ERROR)

    scenarios = [
        s
        for s in SCENARIOS
        if (not args.scenarios or any(s.name.startswith(prefix) for prefix in args.scenarios))
        and (not args.sizes or s.size in args.sizes)
    ]
    print(f"{'size':9}{'scenario':20}{'scheduler':11}{'runs':>5}{'tasks':>7}{'makespan':>10}{'wall':>9}  status")
    configuration_managers = {}
    failures = 0
    for scenario in scenarios:
        for scheduler in args.schedulers:
            parameters = {}
            if scheduler == "cpsat" and args.cpsat_time_limit:
                parameters["max_time_in_seconds"] = args.cpsat_time_limit
            result = await run_scenario(scenario, scheduler, parameters, configuration_managers)
            runs = sum(count for _, count in scenario.runs)
            status = "ok" if result.ok else "FAIL"
            print(
                f"{scenario.size:9}{scenario.name:20}{scheduler:11}{runs:>5}{len(result.executions):>7}"
                f"{result.makespan:>10}{result.wall_s:>8.1f}s  {status}",
                flush=True,
            )
            if result.error:
                print(f"    {result.error}")
            for violation in result.violations[:10]:
                print(f"    {violation}")
            failures += not result.ok
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
