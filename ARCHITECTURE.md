# RegFlow — System Architecture

**RegFlow** is an Airflow-orchestrated regulatory intelligence platform for Indian compliance workloads (GSTN, EPFO, FSSAI, State PT, and extensible sources).

**Design thesis:** Apache Airflow is the **control plane**. LangGraph agents, ChromaDB, the rule engine, FastAPI, and the Next.js dashboard are **orchestrated workers** — not the thing that starts the work.

---

## 1. High-level control plane

```
                         Apache Airflow 2.8 (LocalExecutor)
                                    │
         ┌──────────────────────────┼──────────────────────────┐
         │                          │                          │
   Collection DAG            Processing DAG             Embedding DAG
   (@hourly + dynamic map)   (Dataset-triggered)       (Dataset-triggered)
         │                          │                          │
         └──────────────────────────┼──────────────────────────┘
                                    ▼
              Compliance Intelligence DAG  →  Reporting DAG
                                    │
              ┌─────────────────────┼─────────────────────┐
              ▼                     ▼                     ▼
         Redis workers          Grafana               FastAPI / UI
```

### What runs when

| Component | Role |
|-----------|------|
| **Airflow scheduler** | Starts DAGs on cron / Dataset events |
| **Airflow webserver** | Graph, Grid, Gantt, Logs, Datasets UI |
| **PostgreSQL** | App DB (`regraph`) + Airflow metadata (`airflow`) |
| **Redis** | Queue lists for embed / llm / validate workers |
| **Grafana** | Observability dashboards |
| **FastAPI** | Interactive API, HITL, demo triggers |
| **Next.js** | Compliance dashboard (downstream consumer) |

---

## 2. Five Dataset-linked DAGs

```
reggraph_regulatory_collection          schedule: @hourly
        │  outlets Dataset  reggraph://raw_documents
        ▼
reggraph_document_processing
        │  outlets Dataset  reggraph://chunks
        ▼
reggraph_embedding_pipeline
        │  outlets Dataset  reggraph://embeddings
        ▼
reggraph_compliance_intelligence
        │  outlets Dataset  reggraph://compliance_results
        ▼
reggraph_reporting
```

| DAG ID | Trigger | Responsibility |
|--------|---------|----------------|
| `reggraph_regulatory_collection` | Hourly | Dynamic-mapped fetch per regulator; hash change detect; store raw text |
| `reggraph_document_processing` | Dataset `raw_documents` | Clean HTML/text; semantic chunk; write chunk JSON |
| `reggraph_embedding_pipeline` | Dataset `chunks` | Embed + upsert Chroma; optional Redis embed enqueue |
| `reggraph_compliance_intelligence` | Dataset `embeddings` | Obligation extraction; validation enqueue |
| `reggraph_reporting` | Dataset `compliance_results` | Report archive; Slack/email/webhook/dashboard stubs |

DAG source: `airflow_home/dags/`.

---

## 3. Modern Airflow features used

| Feature | Where |
|---------|--------|
| **TaskFlow API** (`@dag` / `@task`) | All five DAGs |
| **Dynamic task mapping** (`.expand`) | Collection → one mapped task per enabled regulator |
| **Datasets** | Cross-DAG event scheduling (URI scheme `reggraph://…`) |
| **Retries + backoff** | `retries=3` on critical DAGs |
| **Failure callback** | `services/orchestration/alerts.py` → Slack stub + metrics |
| **Sensors (plugin)** | `NewRawDocumentsSensor` under `airflow_home/plugins/sensors/` |
| **Lazy imports** | Heavy libs imported *inside* task bodies (safe DagBag parse) |

Regulators loaded from `config/regulators.yaml` (GSTN / EPFO / FSSAI / PT enabled; SEBI / RBI / MCA / GST ready to flip on).

---

## 4. Data lineage (stage chain)

```
Raw portal document
  → Parsed / cleaned text
  → Chunks
  → Embeddings (Chroma)
  → Compliance / LLM output
  → Rule validation
  → Final report archive
```

Runtime artifacts (local, not required in git):

- `data/pipeline/raw/`
- `data/pipeline/chunks/`
- `data/pipeline/compliance/`
- `data/pipeline/reports/`
- `data/lineage/events.jsonl`
- `data/metrics/counters.json`

---

## 5. Redis worker plane

Airflow **enqueues**; workers **execute**:

| Queue | Worker module | Work |
|-------|---------------|------|
| `rg:queue:embed` | `workers/embedding_worker.py` | Embedding jobs |
| `rg:queue:llm` | `workers/llm_worker.py` | Compliance / LLM jobs |
| `rg:queue:validate` | `workers/validation_worker.py` | Rule validation |

If Redis is down, embedding/compliance DAGs still **succeed** and record a skip note — the control plane stays resilient.

CLI: `python -m workers.run_worker --queue embed|llm|validate`

---

## 6. Dual-rail AI (orchestrated, not primary)

Existing agent stack under `services/agents/`:

| Piece | Role |
|-------|------|
| **Rail A** | LLM / reasoning path |
| **Rail B** | Deterministic rule engine |
| **DRCA** | Compare rails; escalate disagreements |
| **IRDA** | Portal watch / delta detection |
| **COCE** | Cascading obligation impact |
| **HITL / CAAL** | Human review + cryptographic audit ledger |

These are invoked as **pipeline stages / workers**. The scheduler — not the chat UI — drives continuous updates.

---

## 7. Repository layout (public surface)

```text
airflow_home/dags/           # Five TaskFlow DAGs
airflow_home/plugins/        # Sensors, callbacks
config/regulators.yaml       # Dynamic mapping source list
services/orchestration/      # Shared collect/process/embed/compliance/lineage
services/agents/             # LangGraph dual-rail agents
services/knowledge/          # RAG, Chroma, rule engine
services/api/                # FastAPI
workers/                     # Redis consumers
apps/web/                    # Next.js dashboard
monitoring/grafana/          # Provisioned dashboards
docker-compose.yml           # One-command stack
ARCHITECTURE.md              # This file
README.md                    # Quickstart
```

Internal planning notes under `docs/` are **intentionally not published**.

---

## 8. Quick start (Compose)

```bash
git clone https://github.com/MUKUL-PRASAD-SIGH/RegFlow.git
cd RegFlow

docker compose up -d postgres redis
docker compose exec postgres psql -U rguser -d postgres -c "CREATE DATABASE airflow;" || true
docker compose up -d airflow-init
# wait for: User "admin" created
docker compose up -d airflow-webserver airflow-scheduler grafana

# Airflow → http://localhost:8080  (admin / admin)
# Trigger: reggraph_regulatory_collection
```

**Notes**

- DAGs live in `airflow_home/` (not `airflow/`) so PYTHONPATH never shadows the Airflow package.
- Do **not** set `AIRFLOW_UID=0` on Windows.
- Logic smoke test without Airflow: `python scripts/run_v2_pipeline.py --mock`

---

## 9. What to evaluate (hackathon rubric map)

| Criterion | Evidence in this repo |
|-----------|------------------------|
| Multi-DAG platform | Five `reggraph_*` DAGs |
| Dynamic task mapping | Collection `.expand(regulator=…)` |
| Event-driven scheduling | Dataset URIs between DAGs |
| Resilience | retries=3, per-regulator error isolation, optional Redis |
| Observability | Airflow Grid/Gantt/Logs + Grafana |
| Reproducibility | `docker compose.yml` + this architecture doc |

RegFlow is built so judges open **Airflow first** — Graph, mapped tasks, Datasets — and treat AI components as orchestrated services behind that control plane.
