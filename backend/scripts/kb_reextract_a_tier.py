# Copyright (c) 2026 徐泽宇
"""Enqueue reextract for A-tier files (025 citation loc markers).

Usage (from backend/):
  python -m scripts.kb_reextract_a_tier [--dry-run] [--user-id N] [--ext pdf,pptx,xlsx]
  python -m scripts.kb_reextract_a_tier --include-marked   # reextract even if sidecar has filex:loc

See specs/_project/extract-index-pipeline.md §025 — follow with kb_reindex_all after extract queue drains.
"""

from __future__ import annotations

import argparse
import sys

from database import SessionLocal, register_models
from services.kb_reextract_a_tier_service import (
    enqueue_reextract_a_tier_files,
    list_a_tier_reextract_candidates,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Enqueue KB reextract for A-tier files (025 loc markers)")
    parser.add_argument("--user-id", type=int, default=None)
    parser.add_argument("--ext", type=str, default=None, help="Comma-separated: pdf,ppt,pptx,xls,xlsx")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--include-marked",
        action="store_true",
        help="Also reextract sidecars that already contain filex:loc",
    )
    args = parser.parse_args()

    register_models()
    db = SessionLocal()
    try:
        skip_marked = not args.include_marked
        if args.dry_run:
            files = list_a_tier_reextract_candidates(
                db,
                user_id=args.user_id,
                ext_filter=args.ext,
                skip_marked=skip_marked,
            )
            print(f"待 reextract: {len(files)}")
            for f in files[:20]:
                print(f"  id={f.id} user={f.user_id} {f.original_name}")
            if len(files) > 20:
                print(f"  ... 共 {len(files)} 个")
            return 0
        result = enqueue_reextract_a_tier_files(
            db,
            user_id=args.user_id,
            ext_filter=args.ext,
            skip_marked=skip_marked,
            force=True,
        )
        print(f"A 档候选: {result['candidate_count']}")
        print(f"已有 marker 跳过: {result['skipped_marked']}")
        print(f"已入队 reextract: {result['enqueued_count']}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
