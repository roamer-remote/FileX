# Copyright (c) 2026 徐泽宇
"""CLI: python -m scripts.issue_license --customer acme --expires 2027-12-31

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime

from utils.timezone import BEIJING_TZ
from services.license_service import build_license_key


def main() -> int:
    parser = argparse.ArgumentParser(description="签发 FileX FILEX1 License Key")
    parser.add_argument("--customer", required=True, help="customer_id")
    parser.add_argument("--expires", required=True, help="过期日 YYYY-MM-DD（北京时间末秒）")
    parser.add_argument("--edition", default="standard")
    args = parser.parse_args()

    try:
        y, m, d = (int(x) for x in args.expires.split("-"))
        expires_at = datetime(y, m, d, 23, 59, 59, tzinfo=BEIJING_TZ)
    except ValueError:
        print("expires 须为 YYYY-MM-DD", file=sys.stderr)
        return 2

    try:
        key = build_license_key(customer_id=args.customer, expires_at=expires_at, edition=args.edition)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1

    print(key)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
