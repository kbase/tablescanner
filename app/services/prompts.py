"""
Prompt Engineering Module for AI-Powered Config Generation.

Provides structured prompts for Argo AI to analyze pre-computed schema data
and generate DataTables Viewer configurations. Argo cannot execute SQL
commands, so all analysis must be pre-computed before prompt generation.
"""

from __future__ import annotations

import json
from typing import Any


# =============================================================================
# SYSTEM PROMPT - Argo-Optimized
# =============================================================================

SYSTEM_PROMPT = """You are a Senior Bioinformatics Data Engineer creating DataTables Viewer configurations.

## Your Role
Analyze the PRE-COMPUTED schema analysis and sample values provided below to generate
optimal column configurations for scientific data visualization. You CANNOT run SQL 
commands - all data analysis has been pre-computed and provided to you.

## Column Configuration Rules

### Data Type Detection (analyze provided samples)
| Pattern | data_type | Transform |
|---------|-----------|-----------|
| UniRef IDs with prefix (e.g., "UniRef:UniRef90_...") | id | chain: replace prefix → link |
| GO terms (GO:0008150) | ontology | ontology with AmiGO URL |
| KEGG IDs (K00001, ko:K00001) | id | link to KEGG |
| Pfam IDs (PF00001, pfam:PF00001) | id | link to InterPro |
| NCBI IDs (numeric or NP_/WP_) | id | link to NCBI |
| DNA sequences (20+ chars of ATCG) | sequence | sequence transformer |
| Protein sequences (20+ amino acids) | sequence | sequence transformer |
| URLs (http://...) | url | link transformer |
| Email addresses | email | null |
| Numeric with high precision | float | number with decimals |
| Integer values | integer | null or number |
| +/- or strand indicators | string | badge with color mapping |
| Boolean (true/false, yes/no, 1/0) | boolean | boolean transformer |
| P-values, FDR (scientific notation) | float | number with scientific notation |
| Log2 fold change | float | heatmap (diverging, min:-4 max:4) |

### Category Assignment Rules
| Column Pattern | Category |
|----------------|----------|
| Primary ID column (usually first) | core |
| Names (gene_name, organism, etc.) | core |
| Products, functions, descriptions | functional |
| UniRef, UniProt, NCBI, KEGG refs | external |
| GO, Pfam, COG annotations | ontology |
| DNA/AA sequence columns | sequence |
| Scores, p-values, fold changes | statistics |
| Coordinates (start, end, strand) | core |
| System columns, timestamps | metadata |

### Width Guidelines
| Type | Width |
|------|-------|
| ID columns | 100-140px |
| Short strings | 120-180px |
| Long text (descriptions) | 250-400px |
| Numbers | 80-120px |
| Sequences | 150px |
| Boolean | 80px |

### Essential Transform Examples

**UniRef with prefix stripping:**
```json
{"type": "chain", "options": {"transforms": [
  {"type": "replace", "options": {"find": "UniRef:", "replace": ""}},
  {"type": "link", "options": {"urlTemplate": "https://www.uniprot.org/uniref/{value}", "icon": "bi-link-45deg"}}
]}}
```

**GO term ontology:**
```json
{"type": "ontology", "options": {"prefix": "GO", "urlTemplate": "https://amigo.geneontology.org/amigo/term/{value}", "style": "badge"}}
```

**KEGG ID link:**
```json
{"type": "link", "options": {"urlTemplate": "https://www.genome.jp/entry/{value}", "target": "_blank"}}
```

**Strand badge:**
```json
{"type": "badge", "options": {"colorMap": {"+": {"color": "#22c55e", "bgColor": "#dcfce7"}, "-": {"color": "#ef4444", "bgColor": "#fee2e2"}}}}
```

**Heatmap for fold change:**
```json
{"type": "heatmap", "options": {"min": -4, "max": 4, "colorScale": "diverging", "showValue": true, "decimals": 2}}
```

**Scientific notation for p-values:**
```json
{"type": "number", "options": {"notation": "scientific", "decimals": 2}}
```

## Output Format
Return ONLY valid JSON with this exact structure. No markdown, no explanation.

```json
{
  "columns": [
    {
      "column": "exact_sql_column_name",
      "displayName": "Human Readable Name",
      "dataType": "string|number|integer|float|boolean|date|id|sequence|ontology|url",
      "categories": ["core|functional|external|ontology|sequence|statistics|metadata"],
      "sortable": true,
      "filterable": true,
      "copyable": false,
      "width": "auto",
      "pin": null,
      "transform": null
    }
  ]
}
```

## Critical Rules
1. Column names MUST exactly match the SQL schema - case sensitive
2. Pin the primary identifier column to "left"  
3. Set copyable: true for IDs and sequences
4. Right-align numeric columns (handled by viewer based on dataType)
5. Detect prefixes in sample values that need stripping (UniRef:, GO:, ko:, etc.)
6. If samples show patterns like "UniRef:UniRef90_..." always use chain transform
7. For columns with many nulls, still provide full config based on non-null samples"""


# =============================================================================
# PROMPT BUILDERS
# =============================================================================

def build_table_config_prompt(
    table_name: str,
    schema_info: list[dict[str, Any]],
    sample_values: dict[str, list[Any]],
    detected_patterns: dict[str, list[str]],
    statistics: dict[str, dict[str, Any]],
    row_count: int = 0,
) -> str:
    """
    Build a complete prompt for Argo to generate table configuration.
    
    All data must be pre-computed before calling this function since
    Argo cannot execute SQL commands.
    
    Args:
        table_name: Name of the table being configured
        schema_info: Pre-computed from PRAGMA table_info (list of column defs)
        sample_values: Pre-computed samples per column (10-20 non-null values each)
        detected_patterns: Pre-detected patterns like prefixes, URLs, sequences
        statistics: Pre-computed min/max/avg for numeric columns
        row_count: Total rows in table for context
        
    Returns:
        Complete prompt string for Argo
    """
    # Format schema as readable list
    schema_summary = []
    for col in schema_info:
        col_info = f"- {col['name']} ({col.get('type', 'TEXT')})"
        if col.get('pk'):
            col_info += " [PRIMARY KEY]"
        if col.get('notnull'):
            col_info += " [NOT NULL]"
        schema_summary.append(col_info)
    
    prompt = f"""{SYSTEM_PROMPT}

---
## Analysis Data for Table: `{table_name}`
Row Count: {row_count:,}

### Schema Definition
{chr(10).join(schema_summary)}

### Sample Values (10 non-null per column)
{json.dumps(sample_values, indent=2, default=str)}

### Detected Patterns
{json.dumps(detected_patterns, indent=2)}

### Numeric Statistics (min/max/avg)
{json.dumps(statistics, indent=2)}

---
## Task
Generate complete column configurations for table `{table_name}`.
Return ONLY the JSON object with "columns" array. No markdown code fences."""

    return prompt


def build_multi_table_prompt(
    tables: dict[str, dict[str, Any]],
    database_name: str = "database",
) -> str:
    """
    Build prompt for configuring multiple tables at once.
    
    Args:
        tables: Dict mapping table names to their analysis data
        database_name: Name for the overall config
        
    Returns:
        Complete prompt for multi-table config generation
    """
    tables_section = []
    
    for table_name, data in tables.items():
        table_block = f"""
### Table: `{table_name}` ({data.get('row_count', 0):,} rows)

**Schema:**
{json.dumps(data.get('schema', []), indent=2)}

**Sample Values:**
{json.dumps(data.get('samples', {}), indent=2)}

**Detected Patterns:**
{json.dumps(data.get('patterns', {}), indent=2)}
"""
        tables_section.append(table_block)
    
    prompt = f"""{SYSTEM_PROMPT}

---
## Database: {database_name}
Tables: {', '.join(tables.keys())}

{chr(10).join(tables_section)}

---
## Task
Generate configurations for ALL tables. Return JSON with this structure:
{{"tables": {{"table_name": {{"displayName": "...", "columns": [...]}}}}}}

Return ONLY the JSON. No markdown."""

    return prompt


# =============================================================================
# PATTERN DETECTION HELPERS
# =============================================================================

def detect_value_patterns(values: list[Any]) -> list[str]:
    """
    Detect patterns in sample values for prompt enhancement.
    
    Args:
        values: List of sample values from a column
        
    Returns:
        List of detected pattern descriptions
    """
    import re
    
    patterns = []
    str_values = [str(v) for v in values if v is not None and str(v).strip()]
    
    if not str_values:
        return ["all_null"]
    
    # Check for common prefixes
    prefixes = {
        "UniRef:": "UniRef prefix (needs stripping)",
        "GO:": "GO term format",
        "ko:": "KEGG orthology prefix",
        "pfam:": "Pfam prefix",
        "PF": "Pfam ID format",
        "K0": "KEGG K number",
        "http": "URL format",
        "NP_": "NCBI RefSeq protein",
        "WP_": "NCBI protein",
    }
    
    for prefix, desc in prefixes.items():
        if any(v.startswith(prefix) for v in str_values[:5]):
            patterns.append(desc)
    
    # Check for sequences
    seq_pattern = re.compile(r'^[ATCGU]{20,}$', re.IGNORECASE)
    protein_pattern = re.compile(r'^[ACDEFGHIKLMNPQRSTVWY]{15,}$', re.IGNORECASE)
    
    for v in str_values[:3]:
        if seq_pattern.match(v):
            patterns.append("DNA/RNA sequence")
            break
        if protein_pattern.match(v):
            patterns.append("Protein sequence")
            break
    
    # Check value characteristics
    if all(v in ('+', '-', '.') for v in str_values):
        patterns.append("Strand indicator (+/-)")
    
    if len(set(str_values)) <= 5 and len(str_values) > 3:
        patterns.append(f"Categorical ({len(set(str_values))} unique values)")
    
    return patterns if patterns else ["no_special_pattern"]


def compute_numeric_stats(values: list[Any]) -> dict[str, Any] | None:
    """
    Compute statistics for numeric columns.
    
    Args:
        values: List of values from a column
        
    Returns:
        Dict with min, max, avg, or None if not numeric
    """
    numeric_values = []
    for v in values:
        if v is None:
            continue
        try:
            numeric_values.append(float(v))
        except (ValueError, TypeError):
            return None
    
    if not numeric_values:
        return None
    
    return {
        "min": min(numeric_values),
        "max": max(numeric_values),
        "avg": sum(numeric_values) / len(numeric_values),
        "count": len(numeric_values),
        "has_decimals": any(v != int(v) for v in numeric_values if v == v),
    }
