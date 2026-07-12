FROM codercom/code-server:latest

USER root

# ── dbt-core + Python tooling ──
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip \
    python3-venv \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install dbt-core globally for the code-server user
RUN pip3 install --no-cache-dir "dbt-core==2.0.0a4"

# Pre-install VS Code extensions for dbt + Python
RUN code-server --install-extension ms-python.python \
    && code-server --install-extension innoverio.vscode-dbt-power-user \
    && code-server --install-extension redhat.vscode-yaml

USER 1000:1000

WORKDIR /workspace