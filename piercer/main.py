"""
Piercer - Headless Network Boundary Management Hub

FastAPI 主入口
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import wg, clash
from . import __version__

app = FastAPI(
    title="Piercer",
    description="极简、无头 (Headless) 的网络边界管理中枢，专为 AI Agent 操控而生。",
    version=__version__,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# CORS 中间件 (仅限 VPN 内部使用，按需配置)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(wg.router)
app.include_router(clash.router)


@app.get("/", tags=["Health"])
async def root():
    """健康检查"""
    return {
        "name": "Piercer",
        "version": __version__,
        "status": "running",
    }


@app.get("/health", tags=["Health"])
async def health_check():
    """健康检查端点"""
    return {"status": "healthy"}
