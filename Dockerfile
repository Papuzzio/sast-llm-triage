# syntax=docker/dockerfile:1
# TriageGPT container image.
# - Two stages: dependencies are built in "builder", only the venv + app code ship.
# - Runs as an unprivileged UID with no shell login and a read-only root filesystem
#   (the Kubernetes manifest mounts an emptyDir at /tmp for Streamlit's scratch files).
# - Semgrep is NOT installed: the app only reads Semgrep JSON that users upload.

ARG PYTHON_IMAGE=python:3.12-slim-bookworm

FROM ${PYTHON_IMAGE} AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
COPY requirements-app.txt .
RUN pip install --require-virtualenv -r requirements-app.txt \
 && python -m pip uninstall -y pip setuptools wheel

# checkov:skip=CKV_DOCKER_7:base is pinned through the PYTHON_IMAGE build arg (python:3.12-slim-bookworm)
FROM ${PYTHON_IMAGE}
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/tmp \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    STREAMLIT_SERVER_HEADLESS=true
# Patch OS packages the base image hasn't picked up yet, and remove the bundled
# pip/setuptools: the runtime image has no package installer.
RUN apt-get update \
 && apt-get upgrade -y --no-install-recommends \
 && rm -rf /var/lib/apt/lists/* \
 && python -m pip uninstall -y pip setuptools wheel \
 && groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --chown=root:root app ./app
COPY --chown=root:root src ./src
COPY --chown=root:root data/semgrep_juiceshop.json ./data/semgrep_juiceshop.json
COPY --chown=root:root data/juice-shop-src ./data/juice-shop-src
USER 10001:10001
EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=4).status == 200 else 1)"
ENTRYPOINT ["streamlit", "run", "app/triage_app.py", "--server.port=8501", "--server.address=0.0.0.0"]
