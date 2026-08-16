# Copyright (c) 2026 徐泽宇
"""059 P3 T-23：迁移 resource_grants → folder_acl（含 file WARN 报告）。

Usage (from backend/):
  python -m scripts.rbac_migrate_resource_grants [--workspace-id N] [--dry-run] [--actor-user-id N]
"""

from __future__ import annotations

import argparse
import json
import sys

from database import SessionLocal, register_models
from services.rbac_migration_service import migrate_resource_grants


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Migrate legacy resource_grants to folder_acl with WARN report",
    )
    parser.add_argument("--workspace-id", type=int, default=None, help="仅迁移指定共享空间")
    parser.add_argument("--dry-run", action="store_true", help="演练：不写库")
    parser.add_argument(
        "--actor-user-id",
        type=int,
        default=1,
        help="folder_acl audit 字段用的管理员 user_id",
    )
    args = parser.parse_args()

    register_models()
    db = SessionLocal()
    try:
        report = migrate_resource_grants(
            db,
            workspace_id=args.workspace_id,
            dry_run=args.dry_run,
            actor_user_id=args.actor_user_id,
        )
        if not args.dry_run:
            db.commit()
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        db.rollback()
        print(f"迁移失败: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
