# TableScanner

**High-Performance Tabular Data Microservice for KBase**

TableScanner is a professional-grade FastAPI application designed to provide lightning-fast, filtered, and paginated access to massive datasets stored within KBase. By leveraging local SQLite caching and automatic indexing, it transforms slow object retrievals into instantaneous API responses.

---

## 🚀 Key Features

-   **Instant Queries**: Query millions of rows with sub-second response times.
-   **Intelligent Caching**: Automatic local caching of KBase blobs for repeated access.
-   **Dynamic Indexing**: Automatically optimizes database performance on first-access.
-   **Dual-API Support**: Choose between a flexible **Flat POST** for scripts or a hierarchical **RESTful Path** for web apps.
-   **Zero Memory Overhead**: Handles massive datasets without loading them into RAM.

---

## 🛠️ Architecture Overview

TableScanner acts as a high-speed bridge between KBase's persistent storage and your application.

1.  **KBase Blobstore**: Raw data is stored as SQLite databases.
2.  **TableScanner Cache**: Downloads and indexes the database locally.
3.  **FastAPI Layer**: Provides a clean, modern interface for selective data retrieval.

For a deep dive into the service internals, see [ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## 📖 Quick Start

### 1. Run via Docker (Production)

```bash
docker compose up --build -d
```
The service will be available at `http://localhost:8000`. 
Interactive documentation is at `/docs`.

### 2. Local Development

```bash
# Setup environment
cp .env.example .env
# Start dev server
bash scripts/dev.sh
```

---

## 🔌 API Usage Styles

TableScanner provides two primary ways to interact with your data.

### A. Flat POST (Recommended for Scripts)
Everything you need in a single JSON body. Ideal for Python scripts and complex filters.

```python
import requests
payload = {
    "berdl_table_id": "76990/7/2",
    "table_name": "Genes",
    "limit": 100
}
response = requests.post("http://localhost:8000/table-data", json=payload)
```

### B. Path-based REST (Recommended for Web Apps)
Clean, hierarchical URLs that mirror your data structure.

```bash
# List all tables in a KBase object
GET /object/76990/7/2/tables

# Get specific table data
GET /object/76990/7/2/tables/Genes/data?limit=100
```

---

## 📈 Use Cases

-   **High-Throughput Analytics**: Powering large-scale pangenome comparisons.
-   **Interactive Dashboards**: Real-time filtering for community structure visualizations.
-   **CLI Tools**: Integrating KBase data into local bioinformatics pipelines.

---

## 👨‍💻 Development

### Project Structure
-   `app/`: Core logic and FastAPI routes.
-   `app/utils/`: Caching, SQLite, and Workspace integration.
-   `docs/`: Detailed technical documentation.
-   `scripts/`: Demo clients and deployment scripts.

---

## ⚖️ License

Distributed under the MIT License. See `LICENSE` for more information.
