#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any


QUERY_ORDER = tuple(f"q{idx:02d}" for idx in range(1, 16))
MODE_ORDER = ("qos_hybrid", "qos_pure_llm", "no_qos", "qos_topsis")
SCORE_COL = "QoS_Adjusted_Composition_Score"
TIE_TOLERANCE = 1e-12


@dataclass(frozen=True)
class Subtask:
    subtask_id: str
    description: str


@dataclass(frozen=True)
class FlowStep:
    step: int
    subtask_id: str
    api_id: str
    method: str
    url: str
    input_mapping: str
    output_mapping: str
    expected_output: str


@dataclass(frozen=True)
class PlannedFlow:
    mode: str
    score: float
    query_text: str
    run_dir: Path
    subtasks: list[Subtask]
    steps: list[FlowStep]


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON file: {path}") from exc


def _rows_from_summary(summary_path: Path) -> list[dict[str, str]]:
    with summary_path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_official_q02_rows(summary_path: str | Path) -> tuple[list[dict[str, str]], str]:
    path = Path(summary_path)
    rows = [row for row in _rows_from_summary(path) if row.get("Query_ID") == "q02"]
    if not rows:
        raise ValueError(f"No q02 rows found in {path}")
    by_mode = {row.get("Mode", ""): row for row in rows}
    missing = [mode for mode in MODE_ORDER if mode not in by_mode]
    if missing:
        raise ValueError(f"{path} q02 rows are missing modes: {', '.join(missing)}")
    ordered = [by_mode[mode] for mode in MODE_ORDER]
    return ordered, ordered[0].get("Query_Text", "")


def _score(row: dict[str, str]) -> float:
    try:
        score = float(row.get(SCORE_COL, ""))
    except ValueError as exc:
        raise ValueError(f"Non-numeric {SCORE_COL} for {row.get('Mode')}: {row.get(SCORE_COL)!r}") from exc
    if not math.isfinite(score):
        raise ValueError(f"Non-finite {SCORE_COL} for {row.get('Mode')}: {row.get(SCORE_COL)!r}")
    return score


def choose_mode_row(q02_rows: list[dict[str, str]], requested_mode: str | None = None) -> dict[str, str]:
    by_mode = {row.get("Mode", ""): row for row in q02_rows}
    if requested_mode:
        if requested_mode not in by_mode:
            raise ValueError(f"Requested mode {requested_mode!r} was not found for q02")
        return by_mode[requested_mode]

    best_score = max(_score(row) for row in q02_rows)
    best_modes = [row.get("Mode", "") for row in q02_rows if math.isclose(_score(row), best_score, rel_tol=TIE_TOLERANCE, abs_tol=TIE_TOLERANCE)]
    if len(best_modes) > 1:
        raise ValueError(f"q02 has tied best modes; request one explicitly: {', '.join(best_modes)}")
    return next(row for row in q02_rows if row.get("Mode") == best_modes[0])


def _workflow_steps(payload: dict[str, Any]) -> list[dict[str, Any]]:
    workflow = payload.get("execution_workflow")
    if isinstance(workflow, dict) and isinstance(workflow.get("steps"), list):
        return [step for step in workflow["steps"] if isinstance(step, dict)]
    if isinstance(payload.get("steps"), list):
        return [step for step in payload["steps"] if isinstance(step, dict)]
    return []


def parse_planner_steps(
    planner_path: str | Path,
    mode: str,
    *,
    subtask_ids: list[str],
    expected_steps: int,
) -> list[FlowStep]:
    path = Path(planner_path)
    payload = _read_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"Planner payload must be a JSON object: {path}")
    steps = _workflow_steps(payload)
    if len(steps) != expected_steps:
        raise ValueError(f"{mode} planner has {len(steps)} steps; expected {expected_steps}: {path}")

    selected_api_ids = [str(api_id) for api_id in payload.get("selected_api_ids", [])]
    step_api_ids = [str(step.get("api_id") or step.get("API_ID") or "") for step in steps]
    if selected_api_ids and selected_api_ids != step_api_ids:
        raise ValueError(f"{mode} selected_api_ids sequence does not match workflow steps in {path}")

    step_subtask_ids = [str(step.get("subtask_id") or step.get("Subtask_ID") or index) for index, step in enumerate(steps, start=1)]
    if step_subtask_ids != [str(subtask_id) for subtask_id in subtask_ids]:
        raise ValueError(f"{mode} workflow subtask IDs {step_subtask_ids} do not match decomposer subtasks {subtask_ids}")

    return [
        FlowStep(
            step=int(step.get("step") or index),
            subtask_id=step_subtask_ids[index - 1],
            api_id=step_api_ids[index - 1],
            method=str(step.get("method") or ""),
            url=str(step.get("url") or ""),
            input_mapping=str(step.get("input_mapping") or ""),
            output_mapping=str(step.get("output_mapping") or ""),
            expected_output=str(step.get("expected_output") or ""),
        )
        for index, step in enumerate(steps, start=1)
    ]


def _subtask_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("subtasks", "rows", "data"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
    return []


def load_subtasks(path: str | Path) -> list[Subtask]:
    rows = _subtask_rows(_read_json(Path(path)))
    subtasks = [
        Subtask(
            subtask_id=str(row.get("id") or row.get("subtask_id") or row.get("Subtask_ID") or index),
            description=str(row.get("description") or row.get("goal") or row.get("Subtask") or ""),
        )
        for index, row in enumerate(rows, start=1)
    ]
    if not subtasks:
        raise ValueError(f"No subtasks found in {path}")
    return subtasks


def load_planned_flow(
    summary_path: str | Path,
    logs_root: str | Path,
    requested_mode: str | None = None,
    *,
    expected_steps: int,
) -> PlannedFlow:
    q02_rows, query_text = load_official_q02_rows(summary_path)
    row = choose_mode_row(q02_rows, requested_mode=requested_mode)
    run_dir = Path(logs_root) / str(row.get("Run_Folder") or "")
    subtasks = load_subtasks(run_dir / "0_decomposer.json")
    planner_file = row.get("Planner_Output_File") or f"{row.get('Mode')}/4_planner.json"
    steps = parse_planner_steps(
        run_dir / planner_file,
        str(row.get("Mode") or ""),
        subtask_ids=[subtask.subtask_id for subtask in subtasks],
        expected_steps=expected_steps,
    )
    return PlannedFlow(
        mode=str(row.get("Mode") or ""),
        score=_score(row),
        query_text=query_text,
        run_dir=run_dir,
        subtasks=subtasks,
        steps=steps,
    )

