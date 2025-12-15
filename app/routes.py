"""
TableScanner API Routes

Contains all API endpoint definitions.
"""

from fastapi import APIRouter, Query

router = APIRouter()


@router.get("/")
async def root():
    """Root endpoint returning service information."""
    return {
        "service": "TableScanner",
        "version": "1.0.0",
        "status": "running"
    }


@router.get("/search")
async def search(id: str = Query(..., description="ID to search for")):
    """
    Search endpoint that takes an ID parameter.
    
    Args:
        id: The ID to search for (required)
        
    Returns:
        A dictionary with search results
    """
    return {
        "query_id": id,
        "status": "success",
        "message": f"Search completed for ID: {id}"
    }
