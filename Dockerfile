FROM ghcr.io/astral-sh/uv:python3.13-alpine
RUN apk --no-cache add curl git
WORKDIR /app

# Copy application code and dependencies
COPY app ./app
COPY pyproject.toml /app/pyproject.toml
RUN uv sync

EXPOSE 8000
CMD ["uv", "run",  "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]