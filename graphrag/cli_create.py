#!/usr/bin/env python3
"""CLI wrapper to run graph_create outside of MCP (e.g., from git hooks)."""
import os

# Prevent OpenMP segfault on macOS during cleanup (pthread_mutex_init crash)
os.environ.setdefault("OMP_NUM_THREADS", "1")

import asyncio
import sys

# Load .env from this script's directory
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

from repo_graphrag.graph_storage_creator import create_graph_storage


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <repo_path> [storage_name]")
        sys.exit(1)

    read_dir = os.path.abspath(sys.argv[1])
    storage_name = sys.argv[2] if len(sys.argv) > 2 else "storage"
    server_dir = os.path.dirname(os.path.abspath(__file__))
    storage_dir = os.path.join(server_dir, storage_name)

    print(f"[repo-graphrag] Updating graph: {read_dir} → {storage_dir}")
    asyncio.run(create_graph_storage(read_dir, storage_dir))
    print("[repo-graphrag] Graph updated.")


if __name__ == "__main__":
    main()
