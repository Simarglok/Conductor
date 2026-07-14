FROM codercom/code-server:4.98.0

USER root

# ── dbt-core + Python tooling ──
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip \
    python3-venv \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install dbt-core in a venv (PEP 668 — Debian blocks system pip)
RUN python3 -m venv /opt/dbt-venv \
    && /opt/dbt-venv/bin/pip install --no-cache-dir "dbt-core==2.0.0a4" \
    && ln -s /opt/dbt-venv/bin/dbt /usr/local/bin/dbt

# Pre-install VS Code extensions for dbt + Python
RUN code-server --install-extension ms-python.python \
    && code-server --install-extension innoverio.vscode-dbt-power-user \
    && code-server --install-extension redhat.vscode-yaml

USER 1000:1000
WORKDIR /workspace