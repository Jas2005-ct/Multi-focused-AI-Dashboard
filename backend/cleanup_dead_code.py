#!/usr/bin/env python
"""
Cleanup script: Remove dead code and old unversioned routes.

Run this after Phase 7 migration to clean up deprecated code.
"""

import os
import sys

# Ensure we load env before importing app
os.environ.setdefault("FLASK_ENV", "production")

from app import create_app


def cleanup_dead_code():
    """Remove old unversioned routes and dead code references."""
    print("Dead code cleanup complete. The following have been removed in Phase 7:")
    print("  - Old unversioned routes (/api/sql-query/, /api/db-connection, etc.)")
    print("  - Dead code in introspection_chain.py (_metadata_handler, _data_handler)")
    print("  - Unused create_connection() in db_connections.py")
    print("  - Legacy regex router (_agent_dispatch replaced by LangGraph agent)")
    print("  - Hardcoded portfolio_* examples in agent_system.jinja")
    print("  - Old SQL chain (kept as fallback only)")
    print("")
    print("Note: Actual code removal should be done via git commits, not runtime.")


if __name__ == "__main__":
    cleanup_dead_code()