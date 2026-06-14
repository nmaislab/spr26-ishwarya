#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent


@dataclass(frozen=True)
class Step:
    name: str
    command: list[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the full documented post-processing workflow for a completed "
            "AutoLLMCompose run folder."
        )
    )
    parser.add_argument(
        "run_folder",
        type=Path,
        help="Run folder containing qXX_* result folders, for example results/logs/DEV_RUN/fireworks_gpt-oss-120b.",
    )
    parser.add_argument(
        "--path-query",
        help=(
            "Query id for the selected API path comparison figure. "
            "Defaults to the first discovered query."
        ),
    )
    parser.add_argument(
        "--panel-queries",
        action="append",
        default=[],
        help=(
            "Comma-separated query ids for one query-panel figure. May be repeated. "
            "Defaults to automatic groups of discovered queries."
        ),
    )
    parser.add_argument("--png-dpi", type=int, default=300, help="PNG export resolution for generated figures.")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without running them.")
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Run remaining steps after a failure and exit non-zero at the end.",
    )
    return parser.parse_args()


def resolve_run_folder(path: Path) -> Path:
    candidate = path.expanduser()
    if not candidate.is_absolute():
        candidate = (PROJECT_ROOT / candidate).resolve()
    if not candidate.exists():
        raise FileNotFoundError(f"Run folder does not exist: {candidate}")
    if not candidate.is_dir():
        raise NotADirectoryError(f"Run folder is not a directory: {candidate}")
    return candidate


def build_steps(args: argparse.Namespace, run_folder: Path) -> list[Step]:
    steps = [
        Step(
            "Consolidate composition results",
            [sys.executable, str(SCRIPT_DIR / "consolidate_composition_results.py"), str(run_folder)],
        ),
        Step(
            "Evaluate ranking agreement",
            [sys.executable, str(SCRIPT_DIR / "run_ranking_eval.py"), str(run_folder)],
        ),
        Step(
            "Generate weight-sensitivity tables",
            [sys.executable, str(SCRIPT_DIR / "generate_weight_sensitivity_tables.py"), str(run_folder)],
        ),
    ]

    figure_command = [
        sys.executable,
        str(SCRIPT_DIR / "generate_research_figures.py"),
        str(run_folder),
        "--png-dpi",
        str(args.png_dpi),
    ]
    if args.path_query:
        figure_command.extend(["--path-query", args.path_query])
    for group in args.panel_queries:
        figure_command.extend(["--panel-queries", group])
    steps.append(Step("Generate research figures", figure_command))
    return steps


def print_command(command: list[str]) -> None:
    print(shlex.join(command), flush=True)


def run_step(index: int, total: int, step: Step, *, dry_run: bool) -> int:
    print(f"\n[{index}/{total}] {step.name}", flush=True)
    print_command(step.command)
    if dry_run:
        return 0

    started_at = time.monotonic()
    completed = subprocess.run(step.command, cwd=PROJECT_ROOT, check=False)
    elapsed = time.monotonic() - started_at
    if completed.returncode == 0:
        print(f"[ok] {step.name} completed in {elapsed:.1f}s", flush=True)
    else:
        print(f"[failed] {step.name} exited with code {completed.returncode} after {elapsed:.1f}s", flush=True)
    return completed.returncode


def main() -> int:
    args = parse_args()
    run_folder = resolve_run_folder(args.run_folder)
    steps = build_steps(args, run_folder)

    print(f"Run folder: {run_folder}", flush=True)
    failures: list[tuple[str, int]] = []
    for index, step in enumerate(steps, start=1):
        return_code = run_step(index, len(steps), step, dry_run=args.dry_run)
        if return_code != 0:
            failures.append((step.name, return_code))
            if not args.continue_on_error:
                return return_code

    if failures:
        print("\nCompleted with failures:", flush=True)
        for name, return_code in failures:
            print(f"- {name}: exit code {return_code}", flush=True)
        return 1

    print("\nAll post-processing steps completed successfully.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
