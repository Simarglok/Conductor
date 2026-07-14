# Conductor — Development Plan & Decisions

## 🎯 Vision

**Conductor** integrates **dbt Core**, **Apache Airflow 3.x**, **code-server (VS Code IDE)**, and a **server-side AI assistant** into a single workspace for data analysts and engineers — an open-source alternative to hosted dbt/transformation platforms.

---

## ✅ Milestone 1: Development Sandbox (DONE)

### What's built

| Service | Status | Details |
|---|---|---|
| PostgreSQL 18.4 | ✅ Working | `postgres:18-alpine`, arm64, volume at `/var/lib/postgresql/18/docker` |
| Redis 8.6.4 | ✅ Working | `redis:8.6.4-alpine`, arm64 |
| FastAPI backend | ✅ Working | Python 3.14, asyncpg, SQLAlchemy async, Alembic, health endpoint |
| Airflow 3.3.0 | ✅ Working | 5 containers: scheduler, dag-processor, api-server, worker, db-init |
| code-server | ✅ Working | VS Code + dbt-core + Python/YAML extensions |
| Example DAG | ✅ Done | `conductor_dbt_run.py` — dbt run → dbt test pipeline |

### Architecture decisions (confirmed)

| Decision | Choice | Rationale |
|---|---|---|
| Executor | **CeleryExecutor** (Redis) | Mature, simple. K8sExecutor for production later. |
| Dag Bundle | **LocalDagBundle** (dev) → **GitDagBundle** (prod) | Git bundle auto-syncs on merge to main. |
| API Server | **`--apps all`** | Both UI + Task SDK roles. Separable for prod scaling. |
| Triggerer | **Skip** | Not needed for dbt pipelines. |
| Airflow config | **ENV-only** | No `airflow.cfg` — all settings via environment variables. |
| Auth manager | **FAB** (FabAuthManager) | Simple Auth Manager generates random passwords (no env override in 3.3.0). |
| Python version | **3.14** | Latest stable. |
| code-server auth | **Password** | Dev mode: `conductor`. Prod: OAuth2/OIDC via FastAPI. |

### Issues encountered & solved

| Problem | Solution |
|---|---|
| PG 18+ volume format | Mount at `/var/lib/postgresql` (not `/data`). |
| PEP 668 blocks pip | Install dbt in python3 venv + symlink. |
| YAML anchor cycle | Extract env vars into separate `x-airflow-env` anchor. |
| `airflow users create` broken (Simple Auth) | Switch to FabAuthManager. |
| `_AIRFLOW_DB_UPGRADE` deprecated | Replace with `_AIRFLOW_DB_MIGRATE`. |
| Celery RESULT_BACKEND had literal `***` | Replace with real password. |
| Init container restart loop | Override `restart: "no"` on airflow-db-init. |
| Init env replacing anchor env | Use `<<: *airflow-env` instead of `<<: *airflow-common` inside environment. |
| Shared logs between containers | Add `./logs:/opt/airflow/logs` to x-airflow-common volumes. |
| Redis DB 0 conflict (backend + Celery) | FastAPI→DB 1, Airflow→DB 0. |
| code-server dbt install fails | Use venv for dbt-core installation. |

---

## 🔜 Milestone 2: FastAPI Auth & User Management

**Priority: High — unlocks multi-user**

- [ ] JWT-based auth (OAuth2 password flow)
- [ ] Register / login endpoints
- [ ] Password hashing (bcrypt via passlib)
- [ ] Token middleware on protected routes
- [ ] User CRUD API (admin only)
- [ ] Airflow FAB user sync after signup (future)

---

## 🔜 Milestone 3: React Dashboard

**Priority: High — user-facing UI**

- [ ] Scaffold Vite + TypeScript + React project
- [ ] Design system / component library (shadcn/ui or similar)
- [ ] Login page
- [ ] Dashboard: DAG status overview
- [ ] Workspace management: list/launch code-server
- [ ] User settings page

---

## 🔜 Milestone 4: Git-based Dag Bundle

**Priority: Medium — needed for prod**

- [ ] Switch from LocalDagBundle → **GitDagBundle**
- [ ] Configure `git_conn_id` via Airflow connections
- [ ] DAG versioning (pin bundle version per DAG run)
- [ ] CI/CD: auto-trigger Airflow DAG parsing on merge to main

---

## 🔜 Milestone 5: AI Assistant (Hermes Proxy)

**Priority: Low — deferred**

- Two modes:
  - **Push** — observability hooks on every dbt run/error
  - **Chat-in-IDE** — VS Code extension calling server-side LLM
- Infrastructure needed:
  - FastAPI AI proxy endpoint
  - Schema metadata enrichment
  - vLLM container (enterprise) or OpenAI-compatible API
- Not started. Focus on core first.

---

## ⏸️ Deferred Decisions

| Topic | Status | Notes |
|---|---|---|
| **Encryption at rest** | ⏸️ Deferred | Master-key pattern for warehouse credentials. Vault vs pgcrypto vs KMS — TBD. |
| **KubernetesExecutor** | ⏸️ Future | CeleryExecutor is fine for dev. K8sExecutor for production multi-tenant. |
| **Kubernetes Helm Chart** | ⏸️ Future | Enterprise deployment path from docker-compose. |
|| **Secrets management** | ✅ Done | Moved to root `.env` file with `VAR:-default` fallbacks in docker-compose. |
|| **Airflow healthchecks** | ✅ Done | FastAPI healthcheck added. Airflow healthchecks still pending. |
| **dbt Power User extension** | ⏸️ TBD | Now paid (Altimate.ai). Need open-source alternative for code-server. |
| **Triggerer** | ❌ Won't add | Deferrable operators not needed for dbt pipelines. |
| **Simple Auth Manager** | ❌ Won't use | Can't set fixed password via env in Airflow 3.3.0. FAB works. |

---

## 🧱 Known Limitations

1. **No auto-wait for db-init** — `airflow-db-init` is behind `profiles: [init]`. Must run manually before `docker compose up -d` on first start.
2. **Single-user code-server** — only one instance mapped. Multi-user provisioning via FastAPI not yet implemented.
3. **No React dashboard** — CLI/FastAPI-only for now.
4. **No OAuth2** — FAB auth manager with static `admin/admin` for dev only.
5. **Secrets in .env file** — all secrets extracted to `.env` at project root with `:-default` fallbacks. Credentials no longer hardcoded in docker-compose.yml.
6. **dbt-core 2.0.0 alpha** — `2.0.0a4` is pre-release. Track release for stable version.

---

## 📐 Tech Stack (final)

| Package | Version | Why |
|---|---|---|
| Python | 3.14.6 | Latest stable, future-proof |
| FastAPI | 0.115+ | Async, auto-docs, modern |
| PostgreSQL | 18.4 | Latest major release |
| Redis | 8.6.4 | Latest stable, Celery broker |
| Airflow | 3.3.0 | Latest stable, modern arch |
| dbt-core | 2.0.0a4 | alpha, will be stable soon |
| SQLAlchemy | 2.0+ | Async support via asyncpg |
| Alembic | 1.13+ | DB migrations |
| code-server | 4.98.0 | VS Code in browser, pinned for reproducibility |
| Node | 22 LTS | For React dashboard |