# Copyright (c) 2026 徐泽宇
"""Backfill files.index_pipeline_fingerprint for ready indexed files.

Usage (from backend/): python -m scripts.kb_backfill_fingerprint
"""

from __future__ import annotations

import argparse
import sys

from database import SessionLocal, register_models
from services.kb_backfill_fingerprint import backfill


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill KB index pipeline fingerprints")
    parser.parse_args()
    register_models()
    db = SessionLocal()
    try:
        result = backfill(db)
        db.commit()
        print(f"updated={result['updated']} skipped={result['skipped']}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
