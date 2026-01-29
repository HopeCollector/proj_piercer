"""
Application Configuration

支持环境变量覆盖的配置管理。
"""

import os
from dataclasses import dataclass


@dataclass
class Settings:
    """应用配置"""
    
    # WireGuard 配置文件路径
    wg_config_path: str = os.getenv("PIERCER_WG_CONFIG", "/etc/wireguard/wg0.conf")
    
    # Clash 配置文件路径
    clash_config_path: str = os.getenv("PIERCER_CLASH_CONFIG", "data/uploaded_clash.yaml")
    
    # 服务器 Endpoint (供客户端连接) - 必须通过环境变量配置
    server_endpoint: str = os.getenv("PIERCER_SERVER_ENDPOINT", "")
    
    # 是否启用 WireGuard 热重载
    enable_wg_reload: bool = os.getenv("PIERCER_ENABLE_WG_RELOAD", "false").lower() == "true"
    
    # DNS 服务器监听地址
    dns_listen_address: str = os.getenv("PIERCER_DNS_LISTEN", "10.8.0.1")
    dns_listen_port: int = int(os.getenv("PIERCER_DNS_PORT", "53"))
    
    # DNS 域名后缀 - 建议通过环境变量配置
    dns_domain_suffix: str = os.getenv("PIERCER_DNS_DOMAIN", ".vpn.example.com")
    
    # API 监听配置
    api_host: str = os.getenv("PIERCER_API_HOST", "10.8.0.1")
    api_port: int = int(os.getenv("PIERCER_API_PORT", "8000"))
    
    def is_server_endpoint_configured(self) -> bool:
        """检查服务器 Endpoint 是否已配置"""
        return bool(self.server_endpoint and self.server_endpoint.strip())


# 全局配置实例
settings = Settings()
