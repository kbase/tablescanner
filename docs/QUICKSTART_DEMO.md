# Quickstart Demo

This guide walks you through running the TableScanner demo locally.

## Prerequisites

- Python 3.9+
- KBase Auth Token (for accessing workspace objects)

## Setup

1. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Start the Service**
   ```bash
   uv run fastapi dev app/main.py
   ```
   Server will start at `http://localhost:8000`.

## Running the Demo

1. Open the [Viewer](http://localhost:8000/static/viewer.html) in your browser.

2. **Configuration:**
   - **Environment**: Select `AppDev` (or appropriate env).
   - **Auth Token**: Enter your KBase token.

3. **Load Data:**
   - **BERDL Table ID**: Enter `76990/ADP1Test`. 
   - Click the **Search** icon.

4. **Explore:**
   - Since `76990/ADP1Test` contains only one pangenome, it will be **auto-selected**.
   - Tables will load automatically.
   - Select a table (e.g., "Genome attributes") to view data.
   - Hover over cells with IDs (UniProt, KEGG, etc.) to see tooltips.
   - Click IDs to visit external databases.

## Multi-Pangenome Demo

To test loading multiple identifiers:

1. **BERDL Table ID**: Enter `76990/ADP1Test, 76990/ADP1Test` (simulating two sources).
2. Click **Search**.
3. The **Pangenome** dropdown will appear.
4. Options will show as: `ADP1 [76990/ADP1Test]`.
5. Select different options to toggle between datasets (if they were different).
