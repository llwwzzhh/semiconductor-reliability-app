"""运行时配置，全部通过环境变量覆盖。"""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]  # 仓库根目录
FRONTEND_DIR = BASE_DIR / "frontend"


def _default_data_dir() -> Path:
    if os.getenv("VERCEL"):
        return Path("/tmp/semirel-data")
    return BASE_DIR / "data"


DATA_DIR = Path(os.getenv("SEMIREL_DATA_DIR", _default_data_dir()))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{(DATA_DIR / 'reliability.db').as_posix()}")

SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production-use-32-bytes-or-more")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "720"))
FREE_DAILY_QUOTA = int(os.getenv("FREE_DAILY_QUOTA", "20"))
ANONYMOUS_DAILY_QUOTA = int(os.getenv("ANONYMOUS_DAILY_QUOTA", "5"))
APP_NAME = "半导体可靠性计算平台"
APP_VERSION = "2.0.0"
