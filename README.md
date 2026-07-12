# Conductor

Open-source data transformation platform — integrates **dbt Core**, **Apache Airflow 3.x**, **code-server (VS Code IDE)**, and a **Server-Side AI Assistant** into a single workspace for data analysts and engineers.

## Stack

| Component | Version | Image |
|---|---|---|
| PostgreSQL | 18.4 | `postgres:18-alpine` |
| Redis | 8.6.4 | `redis:8.6.4-alpine` |
| Airflow | 3.3.0 | `apache/airflow:3.3.0` + dbt-core |
| dbt-core | 2.0.0a4 | pip inside Airflow + code-server |
| FastAPI | latest | `python:3.14-slim` |
| code-server | latest | VS Code + dbt + Python extensions |

## Quick Start

### Prerequisites

- Docker Desktop (with Apple Silicon / arm64 support)
- Git

### 1. Clone & prepare

```bash
git clone https://github.com/Simarglok/Conductor.git
cd Conductor
```

### 2. Start the stack

```bash
# Initialize Airflow database + create admin user (one-time)
docker compose --profile init up airflow-db-init

# Start all services
docker compose up -d
```

### 3. Access services

| Service | URL | Credentials |
|---|---|---|
| FastAPI (Conductor API) | http://localhost:8000/docs | Swagger UI |
| Airflow UI | http://localhost:8080 | `admin` / `admin` |
| code-server (VS Code) | http://localhost:8443 | password: `conductor` |
| PostgreSQL | `localhost:5432` | `conductor` / `conductor` |

### 4. Stop

```bash
docker compose down
# To also wipe the database (fresh start):
docker compose down -v
```

## Development Workflow

### Local Development (code-server)
1. Open code-server at http://localhost:8443
2. Write dbt models in the `dags/` workspace
3. Run `dbt run` / `dbt test` directly in the VS Code terminal
4. No Airflow involvement — fast iteration

### Production Pipeline (Airflow)
1. Merge feature branch → `main`
2. Git-based Dag Bundle auto-detects the new commit
3. Airflow workers execute production dbt runs

## Project Structure

```
Conductor/
├── backend/                  # FastAPI control plane
│   ├── app/
│   │   ├── main.py           # API entry point
│   │   ├── config.py         # Env-based settings
│   │   ├── database.py       # SQLAlchemy async session
│   │   ├── models/           # ORM models (User, ...)
│   │   ├── routers/          # API endpoints
│   │   └── schemas/          # Pydantic validation
│   ├── alembic/              # Database migrations
│   ├── Dockerfile
│   └── pyproject.toml
├── dags/                     # Airflow DAGs + dbt projects
│   └── conductor_dbt_run.py  # Example dbt DAG
├── docker/
│   ├── airflow/Dockerfile    # Airflow + dbt-core image
│   └── code-server/Dockerfile# VS Code + dbt image
├── docker-compose.yml        # Full dev environment
└── workspaces/               # code-server user data
```

## Troubleshooting

### PostgreSQL 18+ volume migration
If you previously ran an older PostgreSQL version, clear the volume:

```bash
docker compose down -v
```

### Apple Silicon (arm64)
All images support `linux/arm64` natively — no Rosetta emulation needed.

### Python venv (local development)
```bash
python3.14 -m venv .venv
env -u PYTHONPATH .venv/bin/pip install -e "backend[dev]"
```

The `env -u PYTHONPATH` is needed because Hermes Agent injects its own site-packages into `PYTHONPATH`.