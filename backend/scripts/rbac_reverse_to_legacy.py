# Copyright (c) 2026 徐泽宇
"""059 P3 T-26：S3 反向迁移 — WUR + legacy-mappable folder_acl → 旧表。

切回 S1 前须先执行本脚本，再设置 enterprise_rbac_enabled=false。
不可仅关开关回滚（spec §S3）。

Usage (from backend/):
  python -m scripts.rbac_reverse_to_legacy [--workspace-id N] [--dry-run] [--actor-user-id N]
"""

from __future__ import annotations

import argparse
import json
import sys

from database import SessionLocal, register_models
from services.rbac_reverse_to_legacy_service import reverse_to_legacy


def main() -> int:
    parser = argparse.ArgumentParser(description="Reverse RBAC data to legacy tables for S1 rollback")
    parser.add_argument("--workspace-id", type=int, default=None, help="仅处理指定共享空间")
    parser.add_argument("--dry-run", action="store_true", help="演练：不写库")
    parser.add_argument(
        "--actor-user-id",
        type=int,
        default=1,
        help="resource_grants created_by 用的管理员 user_id",
    )
    args = parser.parse_args()

    register_models()
    db = SessionLocal()
    try:
        report = reverse_to_legacy(
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
        print(f"反向迁移失败: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
