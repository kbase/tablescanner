"""
Configuration Validation Module.

Provides JSON schema validation for generated DataTables Viewer configurations
to ensure compatibility with the frontend viewer.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

try:
    from jsonschema import validate, ValidationError, Draft7Validator
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False
    # Dummy objects if needed
    validate = None
    ValidationError = Exception
    Draft7Validator = None


# =============================================================================
# JSON SCHEMAS
# =============================================================================

# Schema for individual column configuration
COLUMN_SCHEMA = {
    "type": "object",
    "required": ["column", "displayName"],
    "properties": {
        "column": {"type": "string", "minLength": 1},
        "displayName": {"type": "string", "minLength": 1},
        "dataType": {
            "type": "string",
            "enum": [
                "string", "number", "integer", "float", "boolean",
                "date", "datetime", "timestamp", "duration",
                "id", "url", "email", "phone",
                "percentage", "currency", "filesize",
                "sequence", "ontology", "json", "array"
            ]
        },
        "visible": {"type": "boolean"},
        "sortable": {"type": "boolean"},
        "filterable": {"type": "boolean"},
        "searchable": {"type": "boolean"},
        "copyable": {"type": "boolean"},
        "width": {"type": "string"},
        "align": {"type": "string", "enum": ["left", "center", "right"]},
        "pin": {"type": ["string", "null"], "enum": ["left", "right", None]},
        "categories": {
            "type": "array",
            "items": {"type": "string"}
        },
        "transform": {
            "type": ["object", "null"],
            "properties": {
                "type": {"type": "string"},
                "options": {"type": "object"}
            }
        }
    },
    "additionalProperties": True  # Allow future extensions
}

# Schema for table configuration
TABLE_SCHEMA = {
    "type": "object",
    "required": ["displayName", "columns"],
    "properties": {
        "displayName": {"type": "string", "minLength": 1},
        "description": {"type": "string"},
        "icon": {"type": "string"},
        "settings": {"type": "object"},
        "categories": {
            "type": "array",
            "items": {"type": "object"}
        },
        "columns": {
            "type": "array",
            "items": COLUMN_SCHEMA,
            "minItems": 1
        }
    }
}

# Schema for complete DataTypeConfig
DATATYPE_CONFIG_SCHEMA = {
    "type": "object",
    "required": ["id", "name", "tables"],
    "properties": {
        "id": {"type": "string", "minLength": 1},
        "name": {"type": "string", "minLength": 1},
        "description": {"type": "string"},
        "version": {"type": "string", "pattern": r"^\d+\.\d+\.\d+$"},
        "icon": {"type": "string"},
        "color": {"type": "string"},
        "objectType": {"type": "string"},
        "defaults": {
            "type": "object",
            "properties": {
                "pageSize": {"type": "integer", "minimum": 1, "maximum": 1000},
                "density": {"type": "string", "enum": ["compact", "default", "comfortable"]},
                "showRowNumbers": {"type": "boolean"},
                "enableSelection": {"type": "boolean"},
                "enableExport": {"type": "boolean"}
            }
        },
        "sharedCategories": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "name"],
                "properties": {
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                    "icon": {"type": "string"},
                    "color": {"type": "string"},
                    "defaultVisible": {"type": "boolean"},
                    "order": {"type": "integer"}
                }
            }
        },
        "tables": {
            "type": "object",
            "additionalProperties": TABLE_SCHEMA,
            "minProperties": 1
        }
    }
}

# Schema for AI-generated column response (single table)
AI_RESPONSE_SCHEMA = {
    "type": "object",
    "required": ["columns"],
    "properties": {
        "columns": {
            "type": "array",
            "items": COLUMN_SCHEMA,
            "minItems": 1
        }
    }
}


# =============================================================================
# VALIDATION FUNCTIONS
# =============================================================================

def validate_config(config: dict[str, Any]) -> tuple[bool, str | None]:
    """
    Validate a complete DataTypeConfig against the schema.
    
    Args:
        config: The configuration dictionary to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        if not HAS_JSONSCHEMA:
            raise ImportError("jsonschema not available")
        
        validator = Draft7Validator(DATATYPE_CONFIG_SCHEMA)
        errors = list(validator.iter_errors(config))
        
        if not errors:
            return True, None
        
        # Format first error
        first_error = errors[0]
        path = ".".join(str(p) for p in first_error.absolute_path) or "root"
        return False, f"Validation error at '{path}': {first_error.message}"
        
    except ImportError:
        # jsonschema not available, do basic validation
        return _basic_validation(config)
    except Exception as e:
        logger.warning(f"Validation error: {e}")
        return False, str(e)


def validate_table_config(table_config: dict[str, Any]) -> tuple[bool, str | None]:
    """
    Validate a single table configuration.
    
    Args:
        table_config: Table configuration dictionary
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        if not HAS_JSONSCHEMA:
            raise ImportError("jsonschema not available")
        
        validate(instance=table_config, schema=TABLE_SCHEMA)
        return True, None
        
    except ImportError:
        return _basic_table_validation(table_config)
    except Exception as e:
        return False, str(e)


def validate_ai_response(response: dict[str, Any]) -> tuple[bool, str | None]:
    """
    Validate AI-generated column response.
    
    Args:
        response: AI response dictionary
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        if not HAS_JSONSCHEMA:
            raise ImportError("jsonschema not available")
        
        validate(instance=response, schema=AI_RESPONSE_SCHEMA)
        return True, None
        
    except ImportError:
        # Basic validation
        if not isinstance(response, dict):
            return False, "Response must be a dictionary"
        if "columns" not in response:
            return False, "Response must have 'columns' key"
        if not isinstance(response["columns"], list):
            return False, "'columns' must be an array"
        if len(response["columns"]) == 0:
            return False, "'columns' array must not be empty"
        return True, None
        
    except Exception as e:
        return False, str(e)


def validate_column_config(column: dict[str, Any]) -> tuple[bool, str | None]:
    """
    Validate a single column configuration.
    
    Args:
        column: Column configuration dictionary
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not isinstance(column, dict):
        return False, "Column must be a dictionary"
    
    if "column" not in column:
        return False, "Column must have 'column' key"
    
    if "displayName" not in column:
        return False, "Column must have 'displayName' key"
    
    # Validate transform structure if present
    if "transform" in column and column["transform"] is not None:
        transform = column["transform"]
        if not isinstance(transform, dict):
            return False, "Transform must be a dictionary"
        if "type" not in transform:
            return False, "Transform must have 'type' key"
    
    return True, None


# =============================================================================
# BASIC VALIDATION (fallback when jsonschema unavailable)
# =============================================================================

def _basic_validation(config: dict[str, Any]) -> tuple[bool, str | None]:
    """Basic validation without jsonschema library."""
    if not isinstance(config, dict):
        return False, "Config must be a dictionary"
    
    # Check required fields
    for field in ["id", "name", "tables"]:
        if field not in config:
            return False, f"Missing required field: {field}"
    
    if not isinstance(config["tables"], dict):
        return False, "'tables' must be a dictionary"
    
    if len(config["tables"]) == 0:
        return False, "'tables' must not be empty"
    
    # Validate each table
    for table_name, table_config in config["tables"].items():
        is_valid, error = _basic_table_validation(table_config)
        if not is_valid:
            return False, f"Table '{table_name}': {error}"
    
    return True, None


def _basic_table_validation(table_config: dict[str, Any]) -> tuple[bool, str | None]:
    """Basic table validation without jsonschema library."""
    if not isinstance(table_config, dict):
        return False, "Table config must be a dictionary"
    
    if "displayName" not in table_config:
        return False, "Missing 'displayName'"
    
    if "columns" not in table_config:
        return False, "Missing 'columns'"
    
    if not isinstance(table_config["columns"], list):
        return False, "'columns' must be an array"
    
    if len(table_config["columns"]) == 0:
        return False, "'columns' must not be empty"
    
    # Validate each column
    for i, column in enumerate(table_config["columns"]):
        is_valid, error = validate_column_config(column)
        if not is_valid:
            return False, f"Column {i}: {error}"
    
    return True, None


# =============================================================================
# SANITIZATION
# =============================================================================

def sanitize_config(config: dict[str, Any]) -> dict[str, Any]:
    """
    Sanitize and normalize a config, fixing common issues.
    
    Args:
        config: Raw configuration dictionary
        
    Returns:
        Sanitized configuration
    """
    sanitized = dict(config)
    
    # Ensure version format
    if "version" not in sanitized or not sanitized["version"]:
        sanitized["version"] = "1.0.0"
    
    # Normalize tables
    if "tables" in sanitized:
        for table_name, table_config in sanitized["tables"].items():
            sanitized["tables"][table_name] = _sanitize_table(table_config)
    
    return sanitized


def _sanitize_table(table_config: dict[str, Any]) -> dict[str, Any]:
    """Sanitize a table configuration."""
    sanitized = dict(table_config)
    
    # Ensure columns exist
    if "columns" not in sanitized:
        sanitized["columns"] = []
    
    # Sanitize each column
    sanitized["columns"] = [
        _sanitize_column(col) for col in sanitized["columns"]
    ]
    
    return sanitized


def _sanitize_column(column: dict[str, Any]) -> dict[str, Any]:
    """Sanitize a column configuration."""
    sanitized = dict(column)
    
    # Default display name to column name
    if "displayName" not in sanitized and "column" in sanitized:
        col_name = sanitized["column"]
        # Convert snake_case to Title Case
        sanitized["displayName"] = col_name.replace("_", " ").title()
    
    # Default data type
    if "dataType" not in sanitized:
        sanitized["dataType"] = "string"
    
    # Ensure categories is a list
    if "categories" not in sanitized:
        sanitized["categories"] = []
    elif not isinstance(sanitized["categories"], list):
        sanitized["categories"] = [sanitized["categories"]]
    
    # Normalize null transform
    if "transform" in sanitized and sanitized["transform"] is None:
        del sanitized["transform"]
    
    return sanitized
