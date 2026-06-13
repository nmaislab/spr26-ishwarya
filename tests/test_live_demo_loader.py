from __future__ import annotations

import json
from pathlib import Path

from src.ui import live_demo_catalog as catalog
from src.ui import live_demo_loader as loader


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = PROJECT_ROOT / "results/logs/DEV_RUN/fireworks_gpt-oss-120b"
Q07_DUPLICATE_RUN_DIR = PROJECT_ROOT / "results/logs/Q07_TEST/fireworks_gpt-oss-120b"


def test_scan_run_folder_discovers_dynamic_queries_and_prefers_complete_duplicate() -> None:
    dev_scan = loader.scan_run_folder(str(RUN_DIR))
    q07_scan = loader.scan_run_folder(str(Q07_DUPLICATE_RUN_DIR))

    dev_query_ids = {row["query_id"] for row in dev_scan["queries"]}
    q07_row = next(row for row in q07_scan["queries"] if row["query_id"] == "q07")

    assert "q01" in dev_query_ids
    assert all("query_dir" in row for row in dev_scan["queries"])
    assert q07_row["folder_name"] == "q07_20260613T122924"
    assert any("more complete artifact set" in warning for warning in q07_scan["warnings"])


def test_live_demo_query_loads_scores_and_selected_paths() -> None:
    bundle = loader.load_live_demo_query(str(RUN_DIR), "q01")

    rows = {row["Mode"]: row for row in bundle["composition_rows"]}
    paths = bundle["selected_paths"]

    assert bundle["available"] is True
    assert float(rows["qos_hybrid"]["QoS_Adjusted_Composition_Score"]) > float(rows["no_qos"]["QoS_Adjusted_Composition_Score"])
    assert paths["no_qos"]
    assert paths["qos_hybrid"]
    assert any(row["selected_for_planner"] == "Yes" for row in bundle["ranking_rows"] if row["mode"] == "qos_pure_llm")
    assert any(row["subtask_id"] == "1" for row in bundle["retrieval_rows"])


def test_live_demo_query_enriches_retrieval_and_ranking_rows() -> None:
    bundle = loader.load_live_demo_query(str(RUN_DIR), "q01")

    retrieval_row = next(row for row in bundle["retrieval_rows"] if row["api_id"] == "weatherdl_weather_forecast")
    ranking_row = next(
        row
        for row in bundle["ranking_rows"]
        if row["mode"] == "qos_pure_llm" and row["api_id"] == "weather_change_live_get_weather_report"
    )
    selected_retrieval_row = next(row for row in bundle["retrieval_rows"] if row["api_id"] == "weather_change_live_get_weather_report")

    assert retrieval_row["display_name"]
    assert retrieval_row["category"] == "Weather"
    assert ranking_row["selected_for_planner"] == "Yes"
    assert ranking_row["category"] == "Weather"
    assert "QoS-Pure-LLM" in selected_retrieval_row["selected_by_modes"]
    assert bundle["query_category"] == "Weather"
    assert bundle["query_domain"] == "Weather alert notification"


def test_official_query_aggregate_averages_scores_across_loaded_queries(tmp_path: Path) -> None:
    q01_eval = tmp_path / "q01_20260531T000001" / "evaluation"
    q02_eval = tmp_path / "q02_20260531T000002" / "evaluation"
    q01_eval.mkdir(parents=True)
    q02_eval.mkdir(parents=True)
    (q01_eval / "query_q01_composition_qos_eval_rows.json").write_text(
        json.dumps(
            [
                {"Query_ID": "q01", "Mode": "no_qos", "QoS_Adjusted_Composition_Score": 0.2, "Functional_Coverage": 0.5},
                {"Query_ID": "q01", "Mode": "qos_pure_llm", "QoS_Adjusted_Composition_Score": 0.8, "Functional_Coverage": 1.0},
            ]
        ),
        encoding="utf-8",
    )
    (q02_eval / "query_q02_composition_qos_eval_rows.json").write_text(
        json.dumps(
            [
                {"Query_ID": "q02", "Mode": "no_qos", "QoS_Adjusted_Composition_Score": 0.4, "Functional_Coverage": 0.7},
            ]
        ),
        encoding="utf-8",
    )

    aggregate = loader.load_official_query_aggregate(str(tmp_path))
    rows = {row["Mode"]: row for row in aggregate["score_rows"]}
    components = {row["Mode"]: row for row in aggregate["component_rows"]}

    assert aggregate["found_query_ids"] == ["q01", "q02"]
    assert rows["no_qos"]["Number_of_queries_included"] == 2
    assert rows["no_qos"]["Missing_query_count"] == 13
    assert abs(rows["no_qos"]["Average_QoS_Adjusted_Composition_Score"] - 0.3) < 1e-12
    assert rows["qos_pure_llm"]["Number_of_queries_included"] == 1
    assert rows["qos_pure_llm"]["Missing_query_count"] == 14
    assert rows["qos_pure_llm"]["Average_QoS_Adjusted_Composition_Score"] == 0.8
    assert abs(components["no_qos"]["Average_Functional_Coverage"] - 0.6) < 1e-12


def test_catalog_helper_loads_inspector_metadata() -> None:
    loaded = catalog.load_api_catalog()
    metadata = catalog.find_api_metadata(loaded, "smsto_send_campaign_message-2")

    assert metadata is not None
    assert metadata["tool_name"] == "SMSto"
    assert metadata["category"] == "SMS"
    assert metadata["http_method"] == "POST"
    assert metadata["source_file"].endswith("api_repo.enriched.jsonl")
