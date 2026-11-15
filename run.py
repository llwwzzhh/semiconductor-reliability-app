"""本地启动脚本。

用法：
    python run.py                 # 127.0.0.1:8000
    python run.py --port 9000     # 指定端口
    python run.py --reload        # 开发模式热重载
"""

from __future__ import annotations

import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="启动半导体可靠性计算平台")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true", help="开发模式热重载")
    args = parser.parse_args()

    uvicorn.run("backend.app.main:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
