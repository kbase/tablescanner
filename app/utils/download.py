"""
Handle/Blobstore utilities for downloading files.
"""

import requests


def download_from_handle(handle_url: str, auth_token: str) -> bytes:
    """
    Download binary file from KBase Handle/Blobstore service.

    Args:
        handle_url: URL to the handle/blobstore service
        auth_token: KBase authentication token

    Returns:
        Binary data

    Raises:
        requests.HTTPError: If download fails
    """
    headers = {"Authorization": auth_token}
    response = requests.get(handle_url, headers=headers)
    response.raise_for_status()
    return response.content
