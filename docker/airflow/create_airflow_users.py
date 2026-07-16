#!/usr/bin/env python3
"""Create 3 system accounts per Airflow instance.

Called after `airflow db migrate` in the docker-compose init flow.
Uses Airflow CLI: `airflow users create` via subprocess.

Environment variables for passwords (with fallback defaults):
  AIRFLOW_DW_ADMIN_PASSWORD   → data-warehouse admin password
  AIRFLOW_DW_DEV_PASSWORD     → data-warehouse dev password
  AIRFLOW_DW_VIEWER_PASSWORD  → data-warehouse viewer password
  AIRFLOW_MKTG_ADMIN_PASSWORD → marketing admin password
  AIRFLOW_MKTG_DEV_PASSWORD   → marketing dev password
  AIRFLOW_MKTG_VIEWER_PASSWORD → marketing viewer password
"""

from __future__ import annotations

import os
import subprocess
import sys

# Project definitions
AIRFLOW_INSTANCES: dict[str, dict[str, str]] = {
    "data-warehouse": {
        "env_prefix": "DW",
    },
    "marketing": {
        "env_prefix": "MKTG",
    },
}

SYSTEM_USERS: list[dict[str, str]] = [
    {"username_suffix": "_admin", "role": "Admin", "first": "System", "last": "Admin"},
    {"username_suffix": "_dev", "role": "User", "first": "System", "last": "Developer"},
    {"username_suffix": "_viewer", "role": "Viewer", "first": "System", "last": "Viewer"},
]


def create_users(project_filter: str | None = None) -> None:
    """Create system users for one or all Airflow instances.

    Args:
        project_filter: If provided, only create users for this project.
                        Otherwise create for all instances.
    Non-zero exits are printed as warnings.
    """
    errors = 0

    for project, config in AIRFLOW_INSTANCES.items():
        if project_filter is not None and project != project_filter:
            continue

        env_prefix = config["env_prefix"]

        for user_def in SYSTEM_USERS:
            username = f"{project}{user_def['username_suffix']}"
            password = os.environ.get(
                f"AIRFLOW_{env_prefix}_{user_def['username_suffix'].upper().lstrip('_')}_PASSWORD",
                f"{project}_{user_def['username_suffix'].lstrip('_')}",
            )

            result = subprocess.run(
                [
                    "airflow", "users", "create",
                    "--username", username,
                    "--password", password,
                    "--firstname", user_def["first"],
                    "--lastname", user_def["last"],
                    "--role", user_def["role"],
                    "--email", f"{username}@conductor.local",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                stderr_line = result.stderr.strip().split("\n")[-1] if result.stderr else "unknown error"
                print(f"WARNING: Failed to create {username}: {stderr_line}", file=sys.stderr)
                errors += 1
            else:
                print(f"Created user: {username} ({user_def['role']})")

    if errors > 0:
        print(f"\n{errors} user(s) failed to create (may already exist — this is OK on re-run)", file=sys.stderr)


if __name__ == "__main__":
    project = sys.argv[1] if len(sys.argv) > 1 else None
    create_users(project_filter=project)