# Conductor

**Conductor** is an open-source foundation for building and operating data transformations. It combines dbt Core, Apache Airflow, a FastAPI control plane, and a React dashboard. The repository is in active development: the supported local path starts the control plane and one base Airflow environment, while the project-runtime workflow is not yet wired end to end.

## Stack

| Component | Version / implementation |
| --- | --- |
| Control plane | FastAPI on Python 3.14 with async SQLAlchemy and Alembic |
| Dashboard | React 19, TypeScript, Vite, Tailwind CSS |
| Orchestration | Apache Airflow 3.3.0 with CeleryExecutor |
| Transformations | dbt-core 2.0.0a4 |
| Development IDE | code-server with JWT authentication |
| Data store | PostgreSQL 18 |
| Cache and broker | Redis 8.6.4 |

## Current implementation status

- JWT authentication, refresh tokens, and a seeded local super-admin account are implemented.
- The API has project, membership, environment, Git configuration, Airflow, workspace, and administration endpoints.
- Configured Git credentials are encrypted at rest and never returned by the API.
- The dashboard provides routes and views for projects, pipeline data, development, Git, settings, and administration.
- The base Airflow environment can be initialised and started locally.

The following pieces are present in the codebase but are **not a working local project workflow** yet:

- The project-creation UI does not send the API's required `Idempotency-Key` header.
- Project creation queues a provisioning job, but Docker Compose does not run a lifecycle worker and the default runner registry is intentionally empty. A project therefore remains in `PROVISIONING`.
- The data-warehouse and marketing Airflow definitions expect PostgreSQL databases that the checked-in Compose flow does not create.
- The code-server endpoint returns the Docker-internal URL `http://code-server:8080`, so the dashboard cannot open the published `localhost:8443` port in a host browser.
- Git branch and commit views currently return placeholder data.

## Quick start: supported local services

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) with Docker Compose v2
- Git
- Apple Silicon is supported natively; no Rosetta emulation is required.

### 1. Clone the repository

```bash
git clone https://github.com/ConductorPlatform/Conductor.git
cd Conductor
```

### 2. Create local environment files

The root `.env` is required by Docker Compose. It holds deployment-level settings, including a stable secret used to derive the Fernet key for stored credentials. It is gitignored and must never be committed.

Create a stable credentials-encryption value without printing it to the terminal:

```bash
umask 077
touch .env
chmod 600 .env

if ! grep -q '^CONDUCTOR_CREDENTIALS_ENCRYPTION_KEY=' .env; then
  python3 - <<'PY'
import base64
import secrets
from pathlib import Path

key = base64.urlsafe_b64encode(secrets.token_bytes(32))
path = Path(".env")
with path.open("a+b") as env_file:
    env_file.seek(0, 2)
    if env_file.tell():
        env_file.seek(-1, 2)
        separator = b"" if env_file.read(1) == b"\n" else b"\n"
    else:
        separator = b""
    env_file.seek(0, 2)
    env_file.write(separator + b"CONDUCTOR_CREDENTIALS_ENCRYPTION_KEY=" + key + b"\n")
PY
fi

[ -f backend/.env ] || cp backend/.env.example backend/.env
chmod 600 backend/.env
```

For a shared or non-local deployment, set strong values in the root `.env` before starting the stack:

```dotenv
CONDUCTOR_JWT_SECRET=replace-with-a-long-random-value
CONDUCTOR_CODE_SERVER_JWT_SECRET=replace-with-a-separate-long-random-value
CONDUCTOR_AIRFLOW_ADMIN_PASSWORD=replace-with-a-strong-password
CONDUCTOR_DB_PASSWORD=replace-with-a-strong-password
```

Keep `CONDUCTOR_CREDENTIALS_ENCRYPTION_KEY` unchanged for the lifetime of the data. Rotating or losing it makes previously encrypted Git credentials unreadable. The application-specific variables and defaults are documented in [`backend/.env.example`](backend/.env.example).

### 3. Initialise the base Airflow database

Run this once for a new Docker volume. It migrates the base Airflow metadata database and creates its local admin user:

```bash
docker compose --profile init up airflow-db-init
```

### 4. Start the supported local services

Start the control plane, dashboard, base Airflow, and their dependencies explicitly. Do not start the data-warehouse or marketing Airflow services until their database provisioning is wired into Compose.

```bash
docker compose up -d \
  postgres redis fastapi frontend \
  airflow-api-server airflow-scheduler airflow-dag-processor airflow-worker

docker compose ps
```

### 5. Access local services

| Service | URL | Local development access |
| --- | --- | --- |
| Conductor dashboard | <http://localhost:3000> | Sign in with the seeded `admin@conductor.local` / `admin`, or register a user |
| Conductor API | <http://localhost:8000/docs> | OpenAPI / Swagger UI |
| API health check | <http://localhost:8000/api/v1/health> | Reports PostgreSQL and Redis connectivity |
| Base Airflow | <http://localhost:8080> | `admin` / `CONDUCTOR_AIRFLOW_ADMIN_PASSWORD` (defaults to `admin`) |
| PostgreSQL | `localhost:5432` | `CONDUCTOR_DB_USER` / `CONDUCTOR_DB_PASSWORD` (both default to `conductor`) |
| Redis | `localhost:6379` | Local development port |

The supplied credentials are development defaults only. Change them before exposing any service outside your machine.

## Dashboard and API limitations

The dashboard is useful for exercising authentication and inspecting the in-progress UI, but project provisioning, Pipeline, and Development are not currently usable as an end-to-end local workflow.

If you call `POST /api/v1/projects` directly, it requires a super-admin bearer token and an `Idempotency-Key` UUID header. It returns an accepted provisioning operation, not a ready project, because no lifecycle runner is configured. The Swagger UI at <http://localhost:8000/docs> is the authoritative reference for the implemented API contracts.

The Compose file defines additional data-warehouse and marketing Airflow services on ports `8081` and `8082`, plus code-server on `8443`. They are not part of the supported quick-start path described above. See [Current implementation status](#current-implementation-status) for the present blockers.

## Architecture

```text
Browser
  │
  ├── React dashboard :3000 ───────────────┐
  │                                         │
  └─────────────────────────────────────────▼
                                  FastAPI control plane :8000
                                  ├── PostgreSQL :5432
                                  ├── Redis :6379
                                  └── Base Airflow :8080
```

The frontend proxies `/api` requests to FastAPI inside Docker. FastAPI owns authentication, authorization, project metadata, credential encryption, and integration-facing API endpoints. The base Airflow environment runs with the CeleryExecutor; PostgreSQL stores its metadata and Redis serves as its broker.

## Repository layout

```text
.
├── backend/                 # FastAPI application, migrations, and backend tests
│   ├── app/                 # Routers, models, schemas, services, workers
│   ├── alembic/             # Database migrations
│   └── .env.example         # Application environment-variable reference
├── frontend/                # React/Vite dashboard and frontend tests
├── dags/                    # Base, data-warehouse, and marketing DAG directories
├── docker/                  # Airflow and code-server image definitions
├── logs/                    # Airflow task logs (runtime artifact)
├── plugins/                 # Shared Airflow plugins
├── workspaces/              # code-server workspaces (runtime artifact)
├── docker-compose.yml       # Local development stack
└── README.md
```

## Development

The Docker stack mounts the backend application and frontend source for development. After starting the supported services, run:

```bash
# Backend tests
docker compose exec fastapi pytest

# Frontend checks
docker compose exec frontend npm run lint
docker compose exec frontend npm run build
docker compose exec frontend npx vitest run
```

For local backend tooling outside Docker, Python 3.14 is required:

```bash
python3.14 -m venv .venv
env -u PYTHONPATH .venv/bin/pip install -e "backend[dev]"
```

`env -u PYTHONPATH` prevents injected site-packages from affecting the local environment.

## Operations and troubleshooting

### Stop or reset the supported local stack

```bash
# Stop containers and retain volumes
docker compose down

# Remove containers and volumes for a completely fresh local start
docker compose down -v
```

After `docker compose down -v`, repeat the [base Airflow initialisation](#3-initialise-the-base-airflow-database) step before starting services again.

### View logs

```bash
docker compose logs -f fastapi
docker compose logs -f frontend
docker compose logs -f airflow-worker
docker compose logs -f airflow-scheduler
docker compose logs -f airflow-api-server
```

### Docker Compose requires an encryption key

If Compose reports that `CONDUCTOR_CREDENTIALS_ENCRYPTION_KEY` is missing, create the root `.env` file with the command in [Create local environment files](#2-create-local-environment-files). Do not substitute a short plain-text value: this setting must be a stable, high-entropy value of at least 32 characters.

### Migrating from an older PostgreSQL volume

PostgreSQL 18 stores data in a version-specific volume path. For an expendable local environment created with an older image, reset the volumes and initialise again:

```bash
docker compose down -v
docker compose --profile init up airflow-db-init
docker compose up -d \
  postgres redis fastapi frontend \
  airflow-api-server airflow-scheduler airflow-dag-processor airflow-worker
```

## License

Conductor is licensed under the [Apache License 2.0](LICENSE).