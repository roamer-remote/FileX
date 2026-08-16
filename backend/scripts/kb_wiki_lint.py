# Copyright (c) 2026 徐泽宇
"""CLI: python -m scripts.kb_wiki_lint [--user-id N] [--workspace-id W] [--dry-run]

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import argparse
import json
import sys

from database import SessionLocal, register_models
from models.user import User
from services.wiki_lint_service import lint_user_wiki

register_models()


def main() -> int:
    parser = argparse.ArgumentParser(description="Wiki 互链体检")
    parser.add_argument("--user-id", type=int, default=None)
    parser.add_argument("--workspace-id", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    db = SessionLocal()
    try:
        if args.user_id is None:
            print("须指定 --user-id", file=sys.stderr)
            return 2
        user = db.query(User).filter(User.id == args.user_id).first()
        if not user:
            print("用户不存在", file=sys.stderr)
            return 1
        report = lint_user_wiki(db, user, args.workspace_id)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if args.dry_run:
            return 0
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
