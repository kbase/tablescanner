FROM ghcr.io/astral-sh/uv:python3.14-alpine

# Install Base Packages
RUN apk --no-cache add bash curl

# Set working directory
WORKDIR /app

# Copy requirements file
COPY requirements.txt ./

# Install dependencies using uv
RUN uv pip install --system -r requirements.txt

# Copy application files
COPY app ./app

# Expose FastAPI port
EXPOSE 8000

# Run FastAPI application with uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
