ARG AIRFLOW_VERSION=3.3.0
FROM apache/airflow:${AIRFLOW_VERSION}

USER root

# ── System deps for dbt-core + git ──
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

USER airflow

# ── dbt-core + Celery for Airflow ──
RUN pip install --no-cache-dir \
    "dbt-core==2.0.0a4" \
    "apache-airflow[celery]==${AIRFLOW_VERSION}"