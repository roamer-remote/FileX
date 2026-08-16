# Copyright (c) 2026 徐泽宇
"""Enqueue vector reindex for all indexable files.

Usage (from backend/): python -m scripts.kb_reindex_all [--user-id N] [--dry-run] [--force]

025 citation loc: run after A-tier (pdf/ppt/xlsx) reextract so sidecar has filex:loc markers.
See specs/_project/extract-index-pipeline.md §025. (--ext filter not implemented yet.)

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import argparse
import sys

from database import SessionLocal, register_models
from services.kb_reindex_all_service import enqueue_reindex_all_files


def main() -> int:
    parser = argparse.ArgumentParser(description="Enqueue KB reindex for all indexable files")
    parser.add_argument("--user-id", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true", help="Clear index_source_hash before enqueue")
    args = parser.parse_args()

    register_models()
    db = SessionLocal()
    try:
        if args.dry_run:
            from models.file import File as FileModel
            q = db.query(FileModel).filter(FileModel.has_md == True)  # noqa: E712
            if args.user_id is not None:
                q = q.filter(FileModel.user_id == args.user_id)
            count = q.count()
            print(f"待重索引: {count}")
            return 0
        result = enqueue_reindex_all_files(db, user_id=args.user_id, force=args.force)
        print(f"待重索引: {result['candidate_count']}")
        print(f"已入队 {result['enqueued_count']}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
