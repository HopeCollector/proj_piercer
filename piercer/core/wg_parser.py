"""
WireGuard Configuration Parser

解析和操作 wg0.conf 配置文件，支持元数据注释块。
"""

import re
import subprocess
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from ipaddress import IPv4Address, IPv4Network

# 匹配模式：注释头 + Peer块内容 (直到下一个注释头或文件结束)
# Group 1: Name, Group 2: Date, Group 3: Block Content
PEER_PATTERN = re.compile(
    r"^# =+\n# ClientName: (.+?)\n# AddedAt: (.+?)\n# =+\n\[Peer\]\n(.*?)(?=\n# =+|\Z)",
    re.MULTILINE | re.DOTALL
)

# 提取 Endpoint 的子模式 (在 Block Content 中查找)
ENDPOINT_PATTERN = re.compile(r"Endpoint\s*=\s*(.+)")

# 提取 PublicKey
PUBKEY_PATTERN = re.compile(r"PublicKey\s*=\s*(.+)")

# 提取 AllowedIPs
ALLOWED_IPS_PATTERN = re.compile(r"AllowedIPs\s*=\s*(.+)")

# 提取 PresharedKey
PRESHARED_KEY_PATTERN = re.compile(r"PresharedKey\s*=\s*(.+)")

# VPN 网段配置
VPN_NETWORK = IPv4Network("10.8.0.0/24")
SERVER_IP = IPv4Address("10.8.0.1")


@dataclass
class WgPeer:
    """WireGuard Peer 数据模型"""
    name: str
    public_key: str
    allowed_ips: str
    added_at: str
    endpoint: Optional[str] = None
    preshared_key: Optional[str] = None
    # 运行时状态 (来自 wg show)
    latest_handshake: Optional[int] = None
    transfer_rx: Optional[int] = None
    transfer_tx: Optional[int] = None


@dataclass
class WgInterface:
    """WireGuard Interface 配置"""
    private_key: str
    address: str
    listen_port: int = 51820
    post_up: Optional[str] = None
    post_down: Optional[str] = None


@dataclass
class WgConfig:
    """完整的 WireGuard 配置"""
    interface: WgInterface
    peers: list[WgPeer] = field(default_factory=list)


class WgParser:
    """WireGuard 配置文件解析器"""
    
    def __init__(self, config_path: str = "/etc/wireguard/wg0.conf"):
        self.config_path = Path(config_path)
    
    def read_config(self) -> str:
        """读取配置文件内容"""
        if not self.config_path.exists():
            raise FileNotFoundError(f"配置文件不存在: {self.config_path}")
        return self.config_path.read_text(encoding="utf-8")
    
    def write_config(self, content: str) -> None:
        """写入配置文件"""
        self.config_path.write_text(content, encoding="utf-8")
    
    def parse_peers(self, content: Optional[str] = None) -> list[WgPeer]:
        """解析所有 Peer 配置"""
        if content is None:
            content = self.read_config()
        
        peers = []
        for match in PEER_PATTERN.finditer(content):
            name = match.group(1).strip()
            added_at = match.group(2).strip()
            block = match.group(3)
            
            # 提取各字段
            pubkey_match = PUBKEY_PATTERN.search(block)
            allowed_ips_match = ALLOWED_IPS_PATTERN.search(block)
            endpoint_match = ENDPOINT_PATTERN.search(block)
            psk_match = PRESHARED_KEY_PATTERN.search(block)
            
            if pubkey_match and allowed_ips_match:
                peer = WgPeer(
                    name=name,
                    public_key=pubkey_match.group(1).strip(),
                    allowed_ips=allowed_ips_match.group(1).strip(),
                    added_at=added_at,
                    endpoint=endpoint_match.group(1).strip() if endpoint_match else None,
                    preshared_key=psk_match.group(1).strip() if psk_match else None,
                )
                peers.append(peer)
        
        return peers
    
    def get_used_ips(self, content: Optional[str] = None) -> set[IPv4Address]:
        """获取已使用的 IP 地址集合"""
        peers = self.parse_peers(content)
        used_ips = {SERVER_IP}  # 服务器 IP 始终被占用
        
        for peer in peers:
            # 从 AllowedIPs 提取 IP (格式: 10.8.0.x/32)
            ip_str = peer.allowed_ips.split("/")[0]
            try:
                used_ips.add(IPv4Address(ip_str))
            except ValueError:
                continue
        
        return used_ips
    
    def get_next_available_ip(self, content: Optional[str] = None) -> IPv4Address:
        """计算下一个可用的 IP 地址"""
        used_ips = self.get_used_ips(content)
        
        # 从 .2 开始分配 (.1 是服务器, .0 是网络地址, .255 是广播)
        for i in range(2, 255):
            candidate = IPv4Address(f"10.8.0.{i}")
            if candidate not in used_ips:
                return candidate
        
        raise RuntimeError("IP 地址池已耗尽")
    
    def check_ip_conflict(self, ip: str, content: Optional[str] = None) -> bool:
        """检查 IP 是否已被占用"""
        try:
            target_ip = IPv4Address(ip.split("/")[0])
        except ValueError:
            raise ValueError(f"无效的 IP 地址: {ip}")
        
        used_ips = self.get_used_ips(content)
        return target_ip in used_ips
    
    def check_name_conflict(self, name: str, content: Optional[str] = None) -> bool:
        """检查名称是否已存在"""
        peers = self.parse_peers(content)
        return any(p.name == name for p in peers)
    
    def get_server_public_key(self) -> str:
        """获取服务器公钥 (通过 wg 命令)"""
        try:
            result = subprocess.run(
                ["wg", "show", "wg0", "public-key"],
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            # 如果 wg 命令不可用，返回占位符
            return "<SERVER_PUBLIC_KEY>"
        except FileNotFoundError:
            return "<SERVER_PUBLIC_KEY>"
    
    def generate_peer_block(
        self,
        name: str,
        public_key: str,
        assigned_ip: str,
        added_at: str,
        endpoint: Optional[str] = None,
        preshared_key: Optional[str] = None,
    ) -> str:
        """生成 Peer 配置块 (含注释)"""
        lines = [
            "",
            "# ==========================================",
            f"# ClientName: {name}",
            f"# AddedAt: {added_at}",
            "# ==========================================",
            "[Peer]",
            f"PublicKey = {public_key}",
            f"AllowedIPs = {assigned_ip}/32",
        ]
        
        if preshared_key:
            lines.append(f"PresharedKey = {preshared_key}")
        
        if endpoint:
            lines.append(f"Endpoint = {endpoint}")
        
        return "\n".join(lines)
    
    def add_peer(
        self,
        name: str,
        public_key: str,
        assigned_ip: str,
        added_at: str,
        endpoint: Optional[str] = None,
        preshared_key: Optional[str] = None,
    ) -> None:
        """添加新 Peer 到配置文件"""
        content = self.read_config()
        
        # 冲突检查
        if self.check_name_conflict(name, content):
            raise ValueError(f"设备名称已存在: {name}")
        if self.check_ip_conflict(assigned_ip, content):
            raise ValueError(f"IP 地址已被占用: {assigned_ip}")
        
        # 生成并追加配置块
        peer_block = self.generate_peer_block(
            name=name,
            public_key=public_key,
            assigned_ip=assigned_ip,
            added_at=added_at,
            endpoint=endpoint,
            preshared_key=preshared_key,
        )
        
        new_content = content.rstrip() + "\n" + peer_block + "\n"
        self.write_config(new_content)
    
    def remove_peer(self, name: str) -> bool:
        """从配置文件中移除指定 Peer"""
        content = self.read_config()
        
        # 构建匹配特定 name 的模式
        pattern = re.compile(
            rf"\n?# =+\n# ClientName: {re.escape(name)}\n# AddedAt: .+?\n# =+\n\[Peer\]\n.*?(?=\n# =+|\Z)",
            re.MULTILINE | re.DOTALL
        )
        
        new_content, count = pattern.subn("", content)
        
        if count == 0:
            return False
        
        self.write_config(new_content)
        return True
    
    def get_p2p_candidates(self, content: Optional[str] = None) -> list[WgPeer]:
        """获取所有具有 Endpoint 的 Peer (可作为 P2P 直连目标)"""
        peers = self.parse_peers(content)
        return [p for p in peers if p.endpoint is not None]
    
    def get_runtime_status(self) -> dict[str, dict]:
        """通过 wg show 获取运行时状态"""
        try:
            result = subprocess.run(
                ["wg", "show", "wg0", "dump"],
                capture_output=True,
                text=True,
                check=True
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            return {}
        
        status = {}
        lines = result.stdout.strip().split("\n")
        
        # 第一行是 interface 信息，跳过
        for line in lines[1:]:
            parts = line.split("\t")
            if len(parts) >= 8:
                public_key = parts[0]
                status[public_key] = {
                    "preshared_key": parts[1] if parts[1] != "(none)" else None,
                    "endpoint": parts[2] if parts[2] != "(none)" else None,
                    "allowed_ips": parts[3],
                    "latest_handshake": int(parts[4]) if parts[4] != "0" else None,
                    "transfer_rx": int(parts[5]),
                    "transfer_tx": int(parts[6]),
                    "persistent_keepalive": parts[7] if parts[7] != "off" else None,
                }
        
        return status
    
    def get_peers_with_status(self) -> list[WgPeer]:
        """获取带有运行时状态的 Peer 列表"""
        peers = self.parse_peers()
        runtime = self.get_runtime_status()
        
        for peer in peers:
            if peer.public_key in runtime:
                info = runtime[peer.public_key]
                peer.latest_handshake = info.get("latest_handshake")
                peer.transfer_rx = info.get("transfer_rx")
                peer.transfer_tx = info.get("transfer_tx")
        
        return peers


def reload_wg(interface: str = "wg0") -> bool:
    """热重载 WireGuard 配置 (不中断现有连接)"""
    try:
        # 1. Strip: 生成仅含 Peer 的纯净配置
        strip_result = subprocess.run(
            f"wg-quick strip {interface}",
            shell=True,
            capture_output=True,
            text=True,
            check=True
        )
        
        strip_path = f"/tmp/{interface}.strip"
        Path(strip_path).write_text(strip_result.stdout)
        
        # 2. Sync: 仅同步差异部分
        subprocess.run(
            f"wg syncconf {interface} {strip_path}",
            shell=True,
            check=True
        )
        
        # 3. Cleanup
        os.remove(strip_path)
        
        return True
    except subprocess.CalledProcessError as e:
        print(f"热重载失败: {e}")
        return False
    except FileNotFoundError:
        print("wg 命令不可用")
        return False


def generate_client_config_template(
    server_public_key: str,
    server_endpoint: str,
    assigned_ip: str,
) -> str:
    """生成客户端配置模板 (供用户填空)"""
    return f"""[Interface]
# === 请填写您生成的私钥 ===
PrivateKey = <YOUR_PRIVATE_KEY>
Address = {assigned_ip}/24

[Peer]
PublicKey = {server_public_key}
# === 如果您生成了预共享密钥，请填写 ===
# PresharedKey = <YOUR_PRESHARED_KEY>
Endpoint = {server_endpoint}
AllowedIPs = 10.8.0.0/24
PersistentKeepalive = 25
"""
