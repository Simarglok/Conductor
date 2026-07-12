"""
Conductor — example dbt DAG for Airflow 3.x.

This DAG runs dbt models in production after a developer merges
their feature branch to main. The dbt invocation uses the manifest
generated during development.

Requirements:
  - dbt-core 2.0.0a4 installed on the worker
  - A dbt project exists at /opt/airflow/dags/dbt_project/
  - The dbt profiles.yml is configured for the target warehouse
"""

from __future__ import annotations

from datetime import datetime

from airflow.sdk import DAG
from airflow.providers.standard.operators.bash import BashOperator

DBT_PROJECT_DIR = "/opt/airflow/dags/dbt_project"
DBT_PROFILES_DIR = "/opt/airflow/dags/dbt_project/profiles"


with DAG(
    dag_id="conductor_dbt_run",
    start_date=datetime(2026, 1, 1),
    schedule="@daily",
    catchup=False,
    default_args={
        "retries": 1,
        "retry_delay": 5,
    },
) as dag:

    dbt_run = BashOperator(
        task_id="dbt_run",
        bash_command=(
            f"cd {DBT_PROJECT_DIR} && "
            f"dbt deps --profiles-dir {DBT_PROFILES_DIR} && "
            f"dbt run --profiles-dir {DBT_PROFILES_DIR}"
        ),
    )

    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command=(
            f"cd {DBT_PROJECT_DIR} && "
            f"dbt test --profiles-dir {DBT_PROFILES_DIR}"
        ),
    )

    dbt_run >> dbt_test
