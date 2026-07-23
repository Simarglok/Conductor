# Conductor

**Conductor** is an open-source workspace for building and operating data transformations. It brings together dbt Core, Apache Airflow, a FastAPI control plane, and a browser-based VS Code environment behind a project-aware React dashboard.

> **Status:** active development. The repository provides a complete local development stack; some project-runtime integrations are still being expanded. See [Current capabilities](#current-capabilities) for the supported scope.

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

## Current capabilities

- JWT authentication with access-token refresh and a seeded local super-admin account.
- Project creation, memberships, role-based access, environments, and project settings.
- Encrypted storage for configured Git credentials; tokens are never returned by the API.
- A durable project lifecycle queue and worker.
- Airflow project widgets, proxy endpoints, and local Airflow services for the base, data-warehouse, and marketing examples.
- A React dashboard for projects, pipeline views, development workspaces, Git merge-request records, settings, and administration.
- Per-user code-server JWTs issued by the control plane.

The Git branch/commit views and automatic provisioning of arbitrary project runtimes are still under development. The checked-in Docker Compose stack exposes the three local Airflow environments described below.

## Quick start

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

Create a stable encryption key without printing it to the terminal:

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

For a shared or non-local deployment, also set strong values in the root `.env` before starting the stack:

```dotenv
CONDUCTOR_JWT_SECRET=replace-with-a-long-random-value
CONDUCTOR_CODE_SERVER_JWT_SECRET=replace-with-a-separate-long-random-value
CONDUCTOR_AIRFLOW_ADMIN_PASSWORD=replace-with-a-strong-password
CONDUCTOR_DB_PASSWORD=replace-with-a-strong-password
```

Keep `CONDUCTOR_CREDENTIALS_ENCRYPTION_KEY` unchanged for the lifetime of the data. Rotating or losing it makes previously encrypted Git credentials unreadable. The application-specific variables and defaults are documented in [`backend/.env.example`](backend/.env.example).

### 3. Initialise Airflow databases

Run this once for a new Docker volume. It migrates the base, data-warehouse, and marketing Airflow metadata databases and creates their local admin users:

```bash
docker compose --profile init up \
  airflow-db-init \
  airflow-dw-db-init \
  airflow-mktg-db-init
```

### 4. Start the development stack

```bash
docker compose up -d
docker compose ps
```

### 5. Open Conductor

| Service | URL | Local development access |
| --- | --- | --- |
| Conductor dashboard | <http://localhost:3000> | Sign in with the seeded `admin@conductor.local` / `admin` account, or register a user |
| Conductor API | <http://localhost:8000/docs> | OpenAPI / Swagger UI |
| API health check | <http://localhost:8000/api/v1/health> | Reports PostgreSQL and Redis connectivity |
| Base Airflow | <http://localhost:8080> | `admin` / `CONDUCTOR_AIRFLOW_ADMIN_PASSWORD` (defaults to `admin`) |
| Data-warehouse Airflow | <http://localhost:8081> | Same local Airflow admin credentials |
| Marketing Airflow | <http://localhost:8082> | Same local Airflow admin credentials |
| code-server | <http://localhost:8443> | JWT access is issued through a project's **Development** view; there is no static password |
| PostgreSQL | `localhost:5432` | `CONDUCTOR_DB_USER` / `CONDUCTOR_DB_PASSWORD` (both default to `conductor`) |
| Redis | `localhost:6379` | Local development port |

The supplied credentials are development defaults only. Change them before exposing any service outside your machine.

## Using the dashboard

1. Sign in with the seeded super-admin account or register a new account.
2. Create a project from **Projects** (project creation requires the super-admin role).
3. Configure repository, environment, and membership settings in the project **Settings** view.
4. Use **Pipeline** to inspect the configured Airflow views and **Development** to open a short-lived JWT-authenticated code-server workspace.

Default project roles, from broadest to narrowest access, are `super_admin`, `project_admin`, `maintainer`, `developer`, and `viewer`.

## Architecture

```text
Browser
  │
  ├── React dashboard :3000 ───────────────┐
  │                                         │
  └── code-server :8443 (project JWT)       │
                                            ▼
                                  FastAPI control plane :8000
                                  ├── PostgreSQL :5432
                                  ├── Redis :6379
                                  ├── Airflow base :8080
                                  ├── Airflow data warehouse :8081
                                  └── Airflow marketing :8082
```

The frontend proxies `/api` requests to FastAPI inside Docker. FastAPI owns authentication, authorization, project metadata, credential encryption, and integration-facing API endpoints. Airflow runs with the CeleryExecutor; PostgreSQL stores its metadata and Redis serves as its broker.

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

The Docker stack mounts the backend application and frontend source for development. Use these commands after the services are running:

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

### Stop or reset the stack

```bash
# Stop containers and retain volumes
docker compose down

# Remove containers and volumes for a completely fresh local start
docker compose down -v
```

After `docker compose down -v`, repeat the [Airflow initialisation](#3-initialise-airflow-databases) step before starting the stack again.

### View logs

```bash
docker compose logs -f fastapi
docker compose logs -f frontend
docker compose logs -f airflow-worker
docker compose logs -f airflow-dw-worker
docker compose logs -f airflow-mktg-worker
```

### Docker Compose requires an encryption key

If Compose reports that `CONDUCTOR_CREDENTIALS_ENCRYPTION_KEY` is missing, create the root `.env` file with the command in [Create local environment files](#2-create-local-environment-files). Do not substitute a short plain-text value: this setting must be a stable, high-entropy value of at least 32 characters.

### Migrating from an older PostgreSQL volume

PostgreSQL 18 stores data in a version-specific volume path. For an expendable local environment created with an older image, reset the volumes and initialise again:

```bash
docker compose down -v
docker compose --profile init up \
  airflow-db-init \
  airflow-dw-db-init \
  airflow-mktg-db-init
docker compose up -d
```

## License

Conductor is licensed under the [Apache License 2.0](LICENSE).
