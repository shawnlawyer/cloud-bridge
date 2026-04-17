FROM node:25-slim AS node_runtime

FROM python:3.11-slim

WORKDIR /app

COPY --from=node_runtime /usr/local /usr/local

RUN apt-get update && \
    apt-get install -y --no-install-recommends libatomic1 && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY bridge ./bridge
COPY examples ./examples
COPY README.md .

RUN pip install --upgrade pip && \
    pip install -e ".[api]"

EXPOSE 8080

ENV CLOUD_BRIDGE_HOST=127.0.0.1
ENV CLOUD_BRIDGE_PORT=8080

CMD ["sh", "-c", "uvicorn bridge.api.app:app --host ${CLOUD_BRIDGE_HOST} --port ${CLOUD_BRIDGE_PORT}"]
