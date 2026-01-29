"""
WireGuard API Router

提供 WireGuard 配置管理的 RPC 接口。
"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..core.wg_parser import (
    WgParser,
    reload_wg,
    generate_client_config_template,
)
from ..config import settings

router = APIRouter(prefix="/api/wg", tags=["WireGuard"])


# === Request/Response Models ===

class PeerAddRequest(BaseModel):
    """添加 Peer 请求"""
    name: str = Field(..., description="设备名称", examples=["macbook-pro"])
    public_key: str = Field(..., description="设备公钥 (Base64)")
    assigned_ip: str = Field(..., description="分配的 IP 地址", examples=["10.8.0.5"])
    endpoint: Optional[str] = Field(None, description="固定设备的 Endpoint", examples=["nas.home.com:51820"])
    preshared_key: Optional[str] = Field(None, description="预共享密钥 (可选)")


class PeerDelRequest(BaseModel):
    """删除 Peer 请求"""
    name: str = Field(..., description="设备名称")


class PeerInfo(BaseModel):
    """Peer 信息"""
    name: str
    public_key: str
    allowed_ips: str
    added_at: str
    endpoint: Optional[str] = None
    latest_handshake: Optional[int] = None
    transfer_rx: Optional[int] = None
    transfer_tx: Optional[int] = None


class ConfigTemplateResponse(BaseModel):
    """配置模板响应"""
    success: bool
    assigned_ip: str
    server_public_key: str
    server_endpoint: str
    config_template: str
    instructions: str


class PeerListResponse(BaseModel):
    """Peer 列表响应"""
    success: bool
    count: int
    peers: list[PeerInfo]


class P2PCandidatesResponse(BaseModel):
    """P2P 候选节点响应"""
    success: bool
    count: int
    candidates: list[PeerInfo]


class OperationResponse(BaseModel):
    """操作结果响应"""
    success: bool
    message: str


# === API Endpoints ===

@router.get("/config/template", response_model=ConfigTemplateResponse)
async def get_config_template():
    """
    获取填空模板
    
    1. 扫描 wg0.conf 计算下一个空闲 IPv4
    2. 提取 Server 公钥
    3. 返回包含指引注释的 Config 文本
    """
    parser = WgParser(settings.wg_config_path)
    
    try:
        next_ip = parser.get_next_available_ip()
        assigned_ip = str(next_ip)
    except FileNotFoundError:
        # 如果配置文件不存在，从 .2 开始
        assigned_ip = "10.8.0.2"
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    
    server_public_key = parser.get_server_public_key()
    
    # 检查 server_endpoint 是否已配置
    if not settings.is_server_endpoint_configured():
        server_endpoint_display = "<未配置 - 请设置 PIERCER_SERVER_ENDPOINT 环境变量>"
    else:
        server_endpoint_display = settings.server_endpoint
    
    config_template = generate_client_config_template(
        server_public_key=server_public_key,
        server_endpoint=server_endpoint_display,
        assigned_ip=assigned_ip,
    )
    
    instructions = f"""**[密钥生成指南]**
Server 已为您分配 IP: `{assigned_ip}`。请在您的本地设备生成密钥：
1. **生成密钥对**: `wg genkey | tee private.key | wg pubkey > public.key`
2. **生成预共享密钥**: `wg genpsk > preshared.key`

**请仅提交 `public.key` 和 `preshared.key` 给 Agent。不要泄露 `private.key`。**"""
    
    return ConfigTemplateResponse(
        success=True,
        assigned_ip=assigned_ip,
        server_public_key=server_public_key,
        server_endpoint=server_endpoint_display,
        config_template=config_template,
        instructions=instructions,
    )


@router.get("/peer/list", response_model=PeerListResponse)
async def list_peers():
    """
    查询所有 Peer 状态
    
    1. 解析 wg0.conf 注释获取 Name
    2. 运行 wg show wg0 dump 获取握手/流量
    3. 合并返回
    """
    parser = WgParser(settings.wg_config_path)
    
    try:
        peers = parser.get_peers_with_status()
    except FileNotFoundError:
        return PeerListResponse(success=True, count=0, peers=[])
    
    peer_infos = [
        PeerInfo(
            name=p.name,
            public_key=p.public_key,
            allowed_ips=p.allowed_ips,
            added_at=p.added_at,
            endpoint=p.endpoint,
            latest_handshake=p.latest_handshake,
            transfer_rx=p.transfer_rx,
            transfer_tx=p.transfer_tx,
        )
        for p in peers
    ]
    
    return PeerListResponse(
        success=True,
        count=len(peer_infos),
        peers=peer_infos,
    )


@router.get("/peer/p2p_candidates", response_model=P2PCandidatesResponse)
async def get_p2p_candidates():
    """
    获取直连节点
    
    1. 扫描 wg0.conf
    2. 筛选出所有拥有 Endpoint 字段的 Peer
    3. 返回列表，供客户端配置 Site-to-Site
    """
    parser = WgParser(settings.wg_config_path)
    
    try:
        candidates = parser.get_p2p_candidates()
    except FileNotFoundError:
        return P2PCandidatesResponse(success=True, count=0, candidates=[])
    
    candidate_infos = [
        PeerInfo(
            name=p.name,
            public_key=p.public_key,
            allowed_ips=p.allowed_ips,
            added_at=p.added_at,
            endpoint=p.endpoint,
        )
        for p in candidates
    ]
    
    return P2PCandidatesResponse(
        success=True,
        count=len(candidate_infos),
        candidates=candidate_infos,
    )


@router.post("/peer/add", response_model=OperationResponse)
async def add_peer(req: PeerAddRequest):
    """
    注册设备
    
    1. 校验 IP 冲突
    2. 组装 INI 块 (含注释)
    3. 若有 endpoint 则写入该行
    4. 追加写入文件 -> wg syncconf
    """
    parser = WgParser(settings.wg_config_path)
    today = date.today().isoformat()
    
    try:
        parser.add_peer(
            name=req.name,
            public_key=req.public_key,
            assigned_ip=req.assigned_ip,
            added_at=today,
            endpoint=req.endpoint,
            preshared_key=req.preshared_key,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="WireGuard 配置文件不存在")
    except ValueError as e:
        return OperationResponse(success=False, message=str(e))
    
    # 热重载配置
    if settings.enable_wg_reload:
        reload_wg()
    
    return OperationResponse(
        success=True,
        message=f"设备 '{req.name}' 已成功添加，IP: {req.assigned_ip}",
    )


@router.post("/peer/del", response_model=OperationResponse)
async def delete_peer(req: PeerDelRequest):
    """
    移除设备
    
    1. 正则定位注释块+Peer块
    2. 内存删除 -> 覆写文件 -> wg syncconf
    """
    parser = WgParser(settings.wg_config_path)
    
    try:
        removed = parser.remove_peer(req.name)
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="WireGuard 配置文件不存在")
    
    if not removed:
        return OperationResponse(
            success=False,
            message=f"未找到设备: {req.name}",
        )
    
    # 热重载配置
    if settings.enable_wg_reload:
        reload_wg()
    
    return OperationResponse(
        success=True,
        message=f"设备 '{req.name}' 已成功移除",
    )
