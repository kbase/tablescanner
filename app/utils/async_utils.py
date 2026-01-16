"""
Async utilities for standardized execution.
"""
import asyncio
from typing import TypeVar, Any, Callable

T = TypeVar("T")

async def run_sync_in_thread(func: Callable[..., T], *args: Any) -> T:
    """
    Run a synchronous function in a separate thread.
    
    Handles compatibility between Python 3.9+ (asyncio.to_thread) 
    and older versions (loop.run_in_executor).
    
    Args:
        func: The synchronous function to run
        *args: Arguments to pass to the function
        
    Returns:
        The result of the function call
    """
    if hasattr(asyncio, 'to_thread'):
        return await asyncio.to_thread(func, *args)
    
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, func, *args)
