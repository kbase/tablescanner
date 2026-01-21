FROM ghcr.io/astral-sh/uv:python3.13-alpine
RUN apk --no-cache add curl git
WORKDIR /app

# Clone KBUtilLib (required external dependency)
# This creates /app/lib/KBUtilLib/ which is referenced by app/utils/workspace.py
RUN mkdir -p lib && \
    cd lib && \
    git clone https://github.com/cshenry/KBUtilLib.git && \
    cd ..

# Add KBUtilLib to PYTHONPATH so it can be imported
ENV PYTHONPATH=/app/lib/KBUtilLib/src:${PYTHONPATH}

# Copy application code and dependencies
COPY app ./app
COPY pyproject.toml /app/pyproject.toml
RUN uv sync

EXPOSE 8000
CMD ["uv", "run",  "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
