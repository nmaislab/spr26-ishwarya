#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


QUERY_ORDER = tuple(f"q{idx:02d}" for idx in range(1, 16))
MODE_ORDER = ("qos_hybrid", "qos_pure_llm", "no_qos", "qos_topsis")


@dataclass(frozen=True)
class PlannerStep:
    step: int
    api_id: str
    method: str
    url: str


@dataclass(frozen=True)
class ModePath:
    mode: str
    score: float
    planner_path: Path
    steps: list[PlannerStep]


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


def _workflow_steps(payload: dict[str, Any]) -> list[dict[str, Any]]:
    workflow = payload.get("execution_workflow")
    if isinstance(workflow, dict) and isinstance(workflow.get("steps"), list):
        return [step for step in workflow["steps"] if isinstance(step, dict)]
    if isinstance(payload.get("steps"), list):
        return [step for step in payload["steps"] if isinstance(step, dict)]
    return []


def extract_planner_steps(mode: str, planner_path: str | Path, *, expected_steps: int) -> list[PlannerStep]:
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

    return [
        PlannerStep(
            step=int(step.get("step") or index),
            api_id=step_api_ids[index - 1],
            method=str(step.get("method") or ""),
            url=str(step.get("url") or ""),
        )
        for index, step in enumerate(steps, start=1)
    ]


def load_mode_paths(q02_rows: list[dict[str, str]], logs_root: str | Path, *, expected_steps: int) -> list[ModePath]:
    root = Path(logs_root)
    by_mode = {row.get("Mode", ""): row for row in q02_rows}
    mode_paths: list[ModePath] = []
    for mode in MODE_ORDER:
        row = by_mode.get(mode)
        if row is None:
            raise ValueError(f"Missing q02 summary row for mode {mode}")
        planner_file = row.get("Planner_Output_File") or f"{mode}/4_planner.json"
        planner_path = root / str(row.get("Run_Folder") or "") / planner_file
        steps = extract_planner_steps(mode, planner_path, expected_steps=expected_steps)
        mode_paths.append(
            ModePath(
                mode=mode,
                score=float(row.get("QoS_Adjusted_Composition_Score") or 0.0),
                planner_path=planner_path,
                steps=steps,
            )
        )
    return mode_paths

