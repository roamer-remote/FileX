# Copyright (c) 2026 徐泽宇
"""Refresh kb_chunks.text_search with current FTS config (008 zhparser).

Does not re-embed vectors. Usage (from backend/):
  python -m scripts.kb_refresh_text_search [--user-id N] [--dry-run] [--batch-size 500]

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import func

from database import SessionLocal, register_models
from models.kb_chunk import KbChunk
from services.kb_fts_service import get_effective_fts_config


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh kb_chunks.text_search for all chunks")
    parser.add_argument("--user-id", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args()

    register_models()
    db = SessionLocal()
    try:
        fts_config = get_effective_fts_config(db)
        base_q = db.query(KbChunk)
        if args.user_id is not None:
            base_q = base_q.filter(KbChunk.user_id == args.user_id)
        total = base_q.count()
        print(f"FTS config={fts_config} chunks={total} dry_run={args.dry_run}")
        if args.dry_run:
            return 0

        updated = 0
        last_id = 0
        while True:
            batch = (
                base_q.filter(KbChunk.id > last_id)
                .order_by(KbChunk.id)
                .limit(args.batch_size)
                .all()
            )
            if not batch:
                break
            for ch in batch:
                ch.text_search = func.to_tsvector(fts_config, ch.text)
                last_id = ch.id
            db.commit()
            updated += len(batch)
            print(f"updated {updated}/{total}", flush=True)
        print(f"done: {updated} chunks")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
