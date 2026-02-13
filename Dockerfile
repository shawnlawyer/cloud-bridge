FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml .
COPY bridge ./bridge
COPY examples ./examples
COPY README.md .

RUN pip install --upgrade pip && \
    pip install -e ".[api]"

EXPOSE 8080

CMD ["uvicorn", "bridge.api.app:app", "--host", "0.0.0.0", "--port", "8080"]
