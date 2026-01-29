"""
Clash API Router

提供 Clash 配置管理的 RPC 接口。
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from ..core.clash_parser import ClashParser
from ..config import settings

router = APIRouter(prefix="/api/clash", tags=["Clash"])


# === Response Models ===

class UploadResponse(BaseModel):
    """上传响应"""
    success: bool
    message: str


class SubscriptionStatus(BaseModel):
    """单个订阅状态"""
    key: str
    name: str
    expire_date: str | None
    days_remaining: int | None
    status: str


class StatusResponse(BaseModel):
    """订阅状态响应"""
    success: bool
    total: int
    expired: int
    expiring: int
    active: int
    unknown: int
    subscriptions: list[SubscriptionStatus]


# === API Endpoints ===

@router.post("/config/upload", response_model=UploadResponse)
async def upload_config(request: Request):
    """
    上传配置
    
    接收 Body 文本，覆盖写入 uploaded_clash.yaml
    """
    body = await request.body()
    content = body.decode("utf-8")
    
    if not content.strip():
        return UploadResponse(success=False, message="配置内容为空")
    
    parser = ClashParser(settings.clash_config_path)
    
    try:
        parser.write_config(content)
    except Exception as e:
        return UploadResponse(success=False, message=f"写入失败: {e}")
    
    return UploadResponse(success=True, message="配置已成功上传")


@router.get("/config/download", response_class=PlainTextResponse)
async def download_config():
    """
    下载配置
    
    读取并返回 uploaded_clash.yaml 内容
    """
    parser = ClashParser(settings.clash_config_path)
    
    try:
        content = parser.read_config()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="配置文件不存在，请先上传")
    
    return PlainTextResponse(content, media_type="text/yaml")


@router.get("/subscription/status", response_model=StatusResponse)
async def get_subscription_status():
    """
    订阅看板
    
    1. 解析 YAML 的 proxy-providers
    2. 正则匹配 Key: ^(.+)-(\\d{4})-(\\d{2})-(\\d{2})$
    3. 返回过期天数与状态告警
    """
    parser = ClashParser(settings.clash_config_path)
    
    if not parser.exists():
        return StatusResponse(
            success=True,
            total=0,
            expired=0,
            expiring=0,
            active=0,
            unknown=0,
            subscriptions=[],
        )
    
    try:
        summary = parser.get_status_summary()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"解析配置失败: {e}")
    
    return StatusResponse(
        success=True,
        total=summary["total"],
        expired=summary["expired"],
        expiring=summary["expiring"],
        active=summary["active"],
        unknown=summary["unknown"],
        subscriptions=[
            SubscriptionStatus(
                key=s["key"],
                name=s["name"],
                expire_date=s["expire_date"],
                days_remaining=s["days_remaining"],
                status=s["status"],
            )
            for s in summary["subscriptions"]
        ],
    )
