# Copyright (c) 2026 徐泽宇
"""059 P3 T-25：S2 关开关回滚演练 — 生成 non-mappable 变更报告。

Usage (from backend/):
  python -m scripts.rbac_s2_rollback_drill --workspace-id N
"""

from __future__ import annotations

import argparse
import json
import sys

from database import SessionLocal, register_models
from models.workspace import Workspace
from services.rbac_rollback_service import generate_s2_rollback_report


def main() -> int:
    parser = argparse.ArgumentParser(description="S2 rollback drill: list non-mappable changes")
    parser.add_argument("--workspace-id", type=int, required=True, help="共享知识空间 ID")
    args = parser.parse_args()

    register_models()
    db = SessionLocal()
    try:
        ws = db.query(Workspace).filter(Workspace.id == args.workspace_id).first()
        if not ws:
            print(f"空间不存在: {args.workspace_id}", file=sys.stderr)
            return 1
        report = generate_s2_rollback_report(db, workspace_id=args.workspace_id)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
