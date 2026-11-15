"""按邮箱开通 / 取消专业版（无限计算额度）。

用法：
    python scripts/grant_premium.py --email user@example.com
    python scripts/grant_premium.py --email user@example.com --revoke
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from backend.app.database import SessionLocal, init_db  # noqa: E402
from backend.app.models import User  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="开通或取消专业版账号")
    parser.add_argument("--email", required=True, help="账号邮箱")
    parser.add_argument("--revoke", action="store_true", help="取消专业版，恢复免费额度")
    args = parser.parse_args()

    init_db()
    with SessionLocal() as db:
        user = db.execute(select(User).where(User.email == args.email.strip().lower())).scalar_one_or_none()
        if user is None:
            print(f"未找到用户：{args.email}")
            return 1
        user.is_premium = not args.revoke
        db.commit()
        state = "专业版（无限次）" if user.is_premium else "免费版（每日限额）"
        print(f"{user.email} 已设置为 {state}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
