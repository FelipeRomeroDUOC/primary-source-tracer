FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    MCP_HOST=0.0.0.0

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY primary_source_tracer ./primary_source_tracer
COPY skills ./skills

RUN pip install --no-cache-dir ".[all]" \
    && useradd --create-home --shell /bin/bash appuser

USER appuser

EXPOSE 8000

CMD ["primary-source-tracer-mcp", "--http"]
