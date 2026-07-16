from __future__ import annotations

ROLE_ACCOUNT_MAP: dict[str, str] = {
    "super_admin": "admin",
    "project_admin": "admin",
    "maintainer": "dev",
    "developer": "dev",
    "viewer": "viewer",
}


def resolve_airflow_account(role_name: str) -> str:
    return ROLE_ACCOUNT_MAP.get(role_name, "viewer")