"""FastAPI 应用入口。"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import APP_NAME, APP_VERSION, FRONTEND_DIR
from .database import init_db
from .routers import auth, calculators, history
from .routers import exporting_routes as export_routes

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("semirel")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("数据库已就绪，前端目录：%s", FRONTEND_DIR)
    yield


app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description="半导体可靠性计算工具：MTBF、Duane 可靠性增长、试验样本量，含用户认证、历史记录与导出。",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["认证"])
app.include_router(calculators.router, prefix="/api", tags=["计算器"])
app.include_router(history.router, prefix="/api/history", tags=["历史记录"])
app.include_router(export_routes.router, prefix="/api/export", tags=["导出"])


@app.get("/api/health", tags=["系统"])
def health():
    return {"status": "ok", "app": APP_NAME, "version": APP_VERSION}


if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(FRONTEND_DIR / "index.html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.app.main:app", host="127.0.0.1", port=8000, reload=True)
