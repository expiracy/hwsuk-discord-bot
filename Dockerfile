# syntax=docker/dockerfile:1
ARG PYTHON_IMAGE=python:3.13-slim-bookworm
FROM ${PYTHON_IMAGE} AS dependencies
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
WORKDIR /build
COPY requirements.txt .
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --only-binary=:all: -r requirements.txt

FROM ${PYTHON_IMAGE} AS runtime
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LOGGING_FILENAME="" \
    BOT_HEALTH_FILE=/tmp/hwsuk-health.json
RUN groupadd --gid 10001 bot \
    && useradd --uid 10001 --gid bot --no-create-home --home-dir /tmp bot
WORKDIR /app
COPY --from=dependencies /opt/venv /opt/venv
COPY bot.py config.json ./
COPY unity_cogs ./unity_cogs
COPY unity_services ./unity_services
COPY unity_util ./unity_util
USER 10001:10001
STOPSIGNAL SIGINT
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 CMD ["python", "-m", "unity_util.health"]
CMD ["python", "bot.py"]

FROM runtime AS test
USER root
COPY requirements.txt requirements-dev.txt .
RUN pip install --only-binary=:all: -r requirements-dev.txt
COPY tests ./tests
COPY .coveragerc .
USER 10001:10001
CMD ["python", "-W", "error::RuntimeWarning", "-m", "unittest", "discover", "-v"]

FROM runtime AS production
