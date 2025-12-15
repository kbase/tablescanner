"""
Pydantic models for request/response schemas.
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel


class SearchRequest(BaseModel):
    """Search request with query parameters."""
    pangenome_id: str
    table_name: str
    limit: Optional[int] = None
    order_by: Optional[List[Dict[str, str]]] = None
    filters: Optional[List[Dict[str, Any]]] = None