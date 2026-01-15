#!/usr/bin/env python3
"""
Developer Config Sync Script

Syncs all developer-editable JSON configs to the Config Control Plane.
Run this after editing config files or pulling from git.

Usage:
    python scripts/sync_developer_configs.py [--auto-publish]
"""

import argparse
import logging
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.developer_config import get_developer_config_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Sync developer configs to Config Control Plane"
    )
    parser.add_argument(
        "--auto-publish",
        action="store_true",
        help="Auto-publish configs after syncing"
    )
    parser.add_argument(
        "--filename",
        help="Sync only this specific config file"
    )
    
    args = parser.parse_args()
    
    manager = get_developer_config_manager()
    
    try:
        if args.filename:
            # Sync single config
            logger.info(f"Syncing {args.filename}...")
            result = manager.sync_to_control_plane(
                args.filename,
                auto_publish=args.auto_publish
            )
            logger.info(f"Result: {result['status']} - {result['message']}")
            
            if result['status'] == 'synced':
                logger.info(f"Config ID: {result['config_id']}")
                logger.info(f"State: {result['state']}")
        else:
            # Sync all configs
            logger.info("Syncing all developer configs...")
            results = manager.sync_all_to_control_plane(
                auto_publish=args.auto_publish
            )
            
            synced = sum(1 for r in results.values() if r.get("status") == "synced")
            unchanged = sum(1 for r in results.values() if r.get("status") == "unchanged")
            errors = sum(1 for r in results.values() if r.get("status") == "error")
            
            logger.info(f"Sync complete:")
            logger.info(f"  Synced: {synced}")
            logger.info(f"  Unchanged: {unchanged}")
            logger.info(f"  Errors: {errors}")
            
            if errors > 0:
                logger.warning("Some configs failed to sync:")
                for filename, result in results.items():
                    if result.get("status") == "error":
                        logger.warning(f"  {filename}: {result.get('error')}")
        
        return 0
        
    except Exception as e:
        logger.error(f"Sync failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
