# AutoLLMCompose

AutoLLMCompose is a research codebase for multi-agent API discovery, ranking,
composition, and evaluation. Given a user goal, the pipeline decomposes the goal
into ordered API-retrieval subtasks, retrieves candidate APIs from a committed
FAISS-backed API catalog index, ranks candidates under QoS and non-QoS modes,
generates composition plans, and writes deterministic evaluation artifacts for
thesis analysis.

## Current Capabilities

- Query decomposition into 2-5 ordered API-retrieval subtasks.
- Shared semantic retrieval from the local API catalog index.
- LLM binary functional refinement over retrieved candidates.
- Candidate ranking across four modes: `no_qos`, `qos_pure_llm`,
  `qos_topsis`, and `qos_hybrid`.
- Deterministic TOPSIS scoring from QoS metrics.
- Functional-first hybrid ranking with zero-functional-match retrieval retry
  for the hybrid view.
- LLM-based planning over selected APIs.
- Deterministic candidate-ranking, duplicate, hallucination, anomaly, and
  composition-QoS evaluation outputs.
- Post-run scripts for composition summaries, ranking agreement metrics,
  weight-sensitivity tables, and research figures.

## Repository Layout

```text
AutoLLMCompose/
|-- data/
|   |-- processed/api_catalog_sample_balanced/
|   |   |-- api_repo.enriched.jsonl        # Runtime functional catalog
|   |   |-- api_qos.jsonl                  # QoS overlay keyed by api_id
|   |   |-- api_repo.tooldesc.jsonl        # Base functional catalog
|   |   |-- enrichment_manifest.json       # Catalog provenance
|   |   `-- README.md
|   |-- index/faiss_no_qos/                # Committed FAISS index
|   |-- queries/all_user_query.jsonl       # Main query set
|   |-- data_gen/                          # Archival notebooks
|   |-- raw/wsdream/                       # Archival raw matrices
|   `-- results/api_inventory/             # Archival inventory reports
|-- prompts/                               # LLM prompt templates
|-- scripts/                               # Post-experiment analysis scripts
|-- src/
|   |-- agents/                            # Decomposer, refiner, ranker, planner, evaluator
|   |-- config/pipeline_config.py          # Central pipeline defaults
|   |-- core/                              # Schemas, parsing, retry, logging helpers
|   |-- driver/run_autogen_pipeline.py     # Main experiment runner
|   |-- eval/                              # Evaluation and audit helpers
|   |-- llm/                               # Provider backends and AutoGen gateway
|   |-- rag/                               # FAISS retrieval wrapper
|   `-- tools/                             # Catalog loading utilities
|-- tests/                                 # Unit tests
|-- requirements.txt
`-- README.md
```

## Requirements

- Python 3.12 is the current local development target.
- Python 3.10+ should work for most of the code, but 3.12 best matches the
  checked-in environment.
- An LLM provider key, or a running LM Studio server for local model use.

## Installation

Run commands from the repository root:

```bash
cd AutoLLMCompose
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

`requirements.txt` includes `faiss-cpu`. If FAISS wheels are unavailable on
your platform, install FAISS through conda instead:

```bash
conda install -c conda-forge faiss-cpu
```

## Environment Variables

Create a local `.env` file in the repository root. The code loads this file
automatically. Do not commit it.

Set `LLM_PROVIDER` to your default provider, or pass `--provider` when running
the pipeline. The experiment runner exposes only the current thesis model
options: Fireworks AI `accounts/fireworks/models/gpt-oss-120b` and Mistral
`mistral-small-latest`. Other backend providers remain in code for explicit
manual use.

```bash
# Provider selection
LLM_PROVIDER=fireworks

# Mistral
MISTRAL_API_KEY=
MISTRAL_MODEL=mistral-small-latest

# Fireworks AI
FIREWORKS_API_KEY=
FIREWORKS_BASE_URL=https://api.fireworks.ai/inference/v1
FIREWORKS_MODEL=accounts/fireworks/models/gpt-oss-120b
FIREWORKS_MODELS=accounts/fireworks/models/gpt-oss-120b
FIREWORKS_TIMEOUT_SECONDS=180
```

Experiment runner provider options:

```text
fireworks, fireworks_ai
mistral
```

## Runtime Data

Normal runs use committed data under `data/`:

- `data/queries/all_user_query.jsonl`: default query set.
- `data/processed/api_catalog_sample_balanced/api_repo.enriched.jsonl`:
  primary functional catalog.
- `data/processed/api_catalog_sample_balanced/api_qos.jsonl`: QoS overlay.
- `data/index/faiss_no_qos/`: committed FAISS index and metadata.

The archival directories `data/data_gen/`, `data/raw/wsdream/`, and
`data/results/api_inventory/` are kept for research transparency. They are not
part of the normal runtime path.

This checkout uses the committed FAISS index directly. If you intentionally
change the catalog or embedding setup, rebuild the corresponding index with the
project's index-generation workflow before committing the catalog and index
together.

## Running The Pipeline

Run one query non-interactively:

```bash
python -m src.driver.run_autogen_pipeline \
  --query-ids q01 \
  --provider fireworks \
  --model accounts/fireworks/models/gpt-oss-120b \
  --run-tag DEV_RUN
```

Run multiple queries:

```bash
python -m src.driver.run_autogen_pipeline \
  --query-ids q01,q02,q03 \
  --provider fireworks \
  --model accounts/fireworks/models/gpt-oss-120b \
  --run-tag FIREWORKS_DEV
```

You can also pass repeated query IDs:

```bash
python -m src.driver.run_autogen_pipeline \
  --query-id q01 \
  --query-id q05 \
  --provider mistral \
  --model mistral-small-latest
```

Use a custom query file with the same `id`, `title`, and `goal` fields:

```bash
python -m src.driver.run_autogen_pipeline \
  --queries-path data/queries/all_user_query.jsonl \
  --query-ids q01 \
  --provider fireworks
```

If you run the driver without arguments, it opens an interactive query and
provider selector:

```bash
python -m src.driver.run_autogen_pipeline
```

## Pipeline Stages

For each selected query, the driver performs:

1. Decomposition, written to `0_decomposer.json`.
2. Shared retrieval, written to `1_retriever_s<subtask>.json`.
3. Functional refinement, written under `evaluation/`.
4. Ranking for `no_qos`, `qos_pure_llm`, `qos_topsis`, and `qos_hybrid`.
5. Candidate selection and planning for each mode when planning is enabled.
6. Candidate ranking, audit, and anomaly evaluation output generation.
7. Composition-QoS evaluation when planning and composition evaluation are
   enabled.

| Mode | Ranking Signal | Description |
| --- | --- | --- |
| `no_qos` | Functional evidence only | LLM ranks retrieved APIs without QoS fields. |
| `qos_pure_llm` | Functional labels + LLM QoS score | Scores QoS with an LLM, enriches candidates with functional labels, and enforces functional-first ranking. |
| `qos_topsis` | Deterministic TOPSIS | Ranks by computed QoS closeness score. |
| `qos_hybrid` | Functional match + TOPSIS | Places functional matches first and orders them with TOPSIS metadata; can retry retrieval for subtasks with zero functional matches. |

## Outputs

Runs are written under:

```text
results/logs/<run_tag>/<provider_model>/<query_id_timestamp>/
```

Important files in each query run include:

```text
meta.json                         # Run status, timings, provider/model metadata
run_config.json                   # Pipeline config snapshot
run.log                           # Stage-level run log
model_usage.json                  # Model usage and failover metadata
0_decomposer.json                 # Decomposed subtasks
1_retriever_s<id>.json            # Shared retrieved candidates
evaluation_result.json            # Pointers to evaluation outputs
<mode>/2_ranked_s<id>.json        # Ranked APIs per mode/subtask
<mode>/3_selected_s<id>.json      # Planner input selection per mode/subtask
<mode>/4_planner.json             # Planner output per mode
evaluation/                       # Excel, JSON, audit, anomaly, and QoS reports
```

The evaluation folder can contain:

- `query_<id>_retrieval_functional_match_rows.json`
- `query_<id>_retrieval_functional_match_summary.json`
- `query_<id>_candidate_api_rankings.xlsx`
- `query_<id>_candidate_api_rankings_rows.json`
- `query_<id>_candidate_api_rankings_summary.json`
- `query_<id>_duplicate_audit.json`
- `query_<id>_hallucination_audit.json`
- `query_<id>_ranking_anomaly_audit.json`
- `query_<id>_mode_anomalies.xlsx`
- `query_<id>_planner_selection_k_summary.json`
- `query_<id>_composition_qos_eval_rows.json`
- `query_<id>_composition_qos_eval_summary.json`
- `query_<id>_composition_qos_eval.xlsx`
- composition validity issue JSON/log outputs when applicable

## Streamlit Dashboard

The interactive dashboard lives in `src/ui/` and is the recommended way to
inspect completed runs, compare ranking/composition outputs, and launch small
interactive experiments from the same codebase.

Start the full dashboard from the repository root:

```bash
source .venv/bin/activate
streamlit run src/ui/ranking_eval_app.py --server.port 8501
```

If port `8501` is already in use, choose another port:

```bash
streamlit run src/ui/ranking_eval_app.py --server.port 8502
```

Then open:

```text
http://localhost:8501
```

The dashboard expects run-parent folders shaped like:

```text
results/logs/<run_tag>/<provider_model>/
|-- q01_<timestamp>/
|-- q02_<timestamp>/
`-- ...
```

This checkout includes local example artifacts that can be used immediately:

```bash
RUN_DIR="results/logs/DEV_RUN/fireworks_gpt-oss-120b"
```

Dashboard pages:

- `Live Demo Deep Dive`: defense-oriented single-query walkthrough with
  decomposed subtasks, retrieved/ranked candidates, selected plans, QoS scores,
  and raw artifact inspection.
- `Ranking Evaluation`: computes Spearman, average-overlap, RBO, and Jaccard
  agreement across ranking modes for a selected run folder.
- `Composition Visualizations`: compares mode-level planned workflows, QoS
  components, bottlenecks, and recommended modes from completed evaluation
  artifacts.
- `Run Experiments`: launches `src.driver.run_autogen_pipeline` in the
  background. This requires the same `.env` provider keys as CLI runs.
- `Completed Runs`: browses finished or still-running query folders and shows
  logs, stage status, Excel/JSON reports, and planner outputs.

The dashboard discovers available run folders under `results/logs/` and prefers
the most complete artifact set when duplicate timestamped folders exist for the
same query. If a page reports that no `qXX_*` folders were found, select the
provider-model folder that directly contains timestamped query directories, for
example `results/logs/DEV_RUN/fireworks_gpt-oss-120b`.

Useful dashboard verification commands:

```bash
python -c "import src.ui.ranking_eval_app as app; print('import ok')"
python -m pytest tests/test_live_demo_loader.py tests/test_composition_visualization_recommendation.py tests/test_ranking_metrics.py
curl -I http://localhost:8501
```

Run the `curl` check only while the Streamlit server is active.

## Running The Streamlit UI With Docker

The Docker setup runs the existing Streamlit dashboard entry point:
`src/ui/ranking_eval_app.py`. That dashboard imports and launches the existing
backend Python modules in this repository, including `src.driver`,
`src.eval`, `src.llm`, and `src.ui`. There is no separate backend API service
in the current app, so `docker-compose.yml` defines one service:
`streamlit-ui`.

The container starts only the UI. It does not automatically run experiments;
experiments start only when the dashboard's `Run Experiments` page launches
`src.driver.run_autogen_pipeline`.

Create a local environment file before running the container:

```bash
cp .env.example .env
```

Required settings for serving the UI:

```bash
STREAMLIT_SERVER_PORT=8501
STREAMLIT_SERVER_ADDRESS=0.0.0.0
STREAMLIT_HOST_PORT=8501
MAOF_RUNTIME_CACHE_DIR=/tmp/maof_runtime_cache
```

Provider keys such as `FIREWORKS_API_KEY` or `MISTRAL_API_KEY` are required
only when launching new experiments from the UI. Browsing already-mounted run
artifacts does not call a model provider.

Build and run with Docker:

```bash
docker build -t autollmcompose-streamlit-ui .
mkdir -p results/logs
docker run --rm \
  --name autollmcompose-streamlit-ui \
  --env-file .env \
  -p 8501:8501 \
  -v "$(pwd)/results/logs:/app/results/logs" \
  autollmcompose-streamlit-ui
```

Build and run with Docker Compose:

```bash
docker compose build streamlit-ui
docker compose up streamlit-ui
```

For detached VM use:

```bash
docker compose up -d streamlit-ui
```

Then open:

```text
http://localhost:8501
```

On a VM, keep `STREAMLIT_SERVER_ADDRESS=0.0.0.0` and open inbound TCP port
`8501`, or put a reverse proxy in front of the container and proxy to
`http://127.0.0.1:8501`. If the host port is already in use, set
`STREAMLIT_HOST_PORT=8502` in `.env` and open `http://localhost:8502`.

The image includes the committed runtime code and data needed by the dashboard:
`src/`, `prompts/`, `data/queries`, `data/processed`, and `data/index`.
Experiment outputs are intentionally not baked into the image. Compose mounts
the host path `./results/logs` at `/app/results/logs` so the dashboard can read
existing runs and write new UI-launched run logs.

Stop the UI:

```bash
docker compose down
```

Or, for the direct `docker run` command:

```bash
docker stop autollmcompose-streamlit-ui
```

Troubleshooting:

- Missing provider keys show up when starting an experiment, for example
  `FIREWORKS_API_KEY missing`. Add the key to `.env` or select a provider with
  configured credentials.
- Empty dashboard pages usually mean no query run folders are mounted under
  `results/logs/`. Keep completed runs under
  `results/logs/<run_tag>/<provider_model>/qXX_<timestamp>/`.
- Missing catalog or FAISS files mean the runtime data was not included or
  pulled. Verify `data/processed/api_catalog_sample_balanced/` and
  `data/index/faiss_no_qos/` exist before building.
- Port conflicts can be handled by changing `STREAMLIT_HOST_PORT` for Compose
  or using a different host mapping such as `-p 8502:8501` with `docker run`.
- The macOS native folder picker is unavailable inside the Linux container.
  Use the mounted `/app/results/logs` layout for run discovery.
- If using LM Studio on the host, `127.0.0.1` points at the container itself.
  Use a host-reachable address such as `host.docker.internal` on Docker
  Desktop, or the VM host/bridge IP on Linux.

## Post-Experiment Analysis

The deterministic scripts in `scripts/` operate on completed parent run folders
that contain one directory per query, named `qXX_*`.

Example run folder:

```bash
RUN_DIR="results/logs/DEV_RUN/fireworks_gpt-oss-120b"
```

Recommended order:

```bash
python scripts/consolidate_composition_results.py "$RUN_DIR"

python scripts/run_ranking_eval.py "$RUN_DIR"

python scripts/generate_weight_sensitivity_tables.py "$RUN_DIR"

python scripts/generate_research_figures.py "$RUN_DIR" \
  --path-query q02 \
  --panel-queries q01,q02,q03,q04,q05 \
  --panel-queries q06,q07,q08,q09,q10 \
  --panel-queries q11,q12,q13,q14,q15
```

Key outputs:

- `<run-folder>/summary/`: consolidated composition scores and aggregate mode
  summaries.
- `<run-folder>/ranking_eval/`: Spearman, average-overlap, RBO, and Jaccard
  ranking agreement matrices plus included/invalid cases.
- `<run-folder>/weigh_sensitivity/`: representative alpha/beta sensitivity
  tables and candidate Top-N risk summaries.
- `<run-folder>/figures/`: publication-ready PNG/PDF figures.

See `scripts/README.md` for detailed script inputs, outputs, and methodology
guards.

## Testing

Run the full unit test suite:

```bash
python -m pytest tests
```

Run focused tests while changing a subsystem:

```bash
python -m pytest tests/test_json_parsing.py tests/test_output_schemas.py
python -m pytest tests/test_ranker_parser.py
python -m pytest tests/test_composition_qos_eval.py
python -m pytest tests/test_fireworks_model_selection.py tests/test_groq_failover_backend.py
python -m pytest tests/test_live_demo_loader.py tests/test_composition_visualization_recommendation.py
```

For a quick syntax check:

```bash
python -m compileall src tests scripts
```

## Configuration

Pipeline defaults are defined in `src/config/pipeline_config.py`. Common values:

- `run_tag`: default output folder under `results/logs/`.
- `shared_index_dir`: FAISS index path.
- `catalog_path`: base functional catalog path.
- `catalog_enriched_path`: runtime functional catalog path.
- `api_qos_path`: QoS overlay path.
- `rag_top_k`: candidates retrieved per subtask.
- `zero_functional_retrieval_retry_enabled`: enables hybrid-only retrieval retry
  when a subtask has zero functional matches.
- `ranker_max_candidates` and `ranker_pool_n`: ranker candidate limits.
- `functional_match_chunk_size`: functional-refinement batch size.
- `functional_refinement_enabled`: enables LLM binary functional labeling.
- `selector_top_n`: fallback number of APIs selected for planner input.
- `planner_enabled`: enables planner generation.
- `planner_candidate_mode`: planner selection mode.
- `hybrid_workflow_selector`: hybrid composition selection strategy.
- `composition_qos_eval_enabled`: enables composition-level QoS evaluation.
- `llm_validation_max_retries`: bounded retries for structurally invalid LLM
  outputs.
- `qos_llm_batch_size`, `qos_llm_validate_formula`, and
  `qos_llm_formula_audit`: QoS LLM scoring controls.

Prefer changing defaults in code only for persistent project-wide behavior. For
one-off runs, use CLI flags such as `--provider`, `--model`, `--query-ids`,
`--queries-path`, and `--run-tag`.

## Troubleshooting

`RuntimeError: faiss is required`

Install `faiss-cpu` with pip or conda, and make sure the committed index exists
under `data/index/faiss_no_qos/`.

`FileNotFoundError` for `data/index/faiss_no_qos/faiss.index`

Restore or regenerate the FAISS index before running the pipeline. The normal
checkout expects these files:

```text
data/index/faiss_no_qos/faiss.index
data/index/faiss_no_qos/meta.jsonl
data/index/faiss_no_qos/config.json
```

Provider key errors such as `FIREWORKS_API_KEY missing`

Add the required key to `.env`, pass a different provider with `--provider`, or
use the other exposed experiment provider option.

No services loaded from catalog

Check that `data/processed/api_catalog_sample_balanced/api_repo.enriched.jsonl`
exists and that the repository data files were pulled correctly.

## Notes For Contributors

- Keep generated outputs under `results/`; this directory is ignored by git.
- Keep local secrets in `.env`; it is ignored by git.
- Rebuild retrieval artifacts after intentionally changing the functional
  catalog.
- Use JSON sidecars as the detailed source of truth for evaluation. Excel
  workbooks are user-facing reports.
- Do not overwrite historical run artifacts unless the task explicitly asks for
  regeneration.

## Citation

If you use this framework or datasets, please cite:

```bibtex
@research{Subramanian2025AutoLLMCompose,
  title={AutoLLMCompose: Multi-Agent LLM Framework for Service Discovery and Composition},
  author={Ishwarya Narayana Subramanian and Eyhab Al-Masri},
  year={2025},
  institution={University of Washington Tacoma}
}
```

## License

MIT License (c) 2025 Ishwarya Narayana Subramanian.
See [LICENSE](LICENSE) for details.

## Acknowledgments

- **Prof. Eyhab Al-Masri**, University of Washington Tacoma - ealmasri@uw.edu
- Supported by the University of Washington Master's in Computer Science &
  Systems program

**Researcher:** Ishwarya Narayana Subramanian, University of Washington Tacoma  
Contact: ishnaruw@uw.edu
