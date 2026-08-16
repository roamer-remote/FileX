# Copyright (c) 2026 徐泽宇
"""059 P3 T-26：S3 new_only 切档前生产就绪校验 CLI。

Usage (from backend/):
  python -m scripts.rbac_s3_validate [--workspace-id N]
"""

from __future__ import annotations

import argparse
import json
import sys

from database import SessionLocal, register_models
from services.rbac_s3_validate_service import validate_s3_readiness


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate S3 new_only readiness")
    parser.add_argument("--workspace-id", type=int, default=None, help="仅校验指定共享空间")
    args = parser.parse_args()

    register_models()
    db = SessionLocal()
    try:
        report = validate_s3_readiness(db, workspace_id=args.workspace_id)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ready_for_new_only"] else 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
