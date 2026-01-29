"""
Clash Configuration Parser

解析 Clash 配置文件，提取订阅状态信息。
"""

import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import yaml

# 匹配 proxy-provider key 中的日期: name-YYYY-MM-DD
DATE_PATTERN = re.compile(r"^(.+)-(\d{4})-(\d{2})-(\d{2})$")


@dataclass
class SubscriptionInfo:
    """订阅信息"""
    key: str
    name: str
    expire_date: Optional[date]
    days_remaining: Optional[int]
    status: str  # "active", "expiring", "expired", "unknown"
    url: Optional[str] = None


class ClashParser:
    """Clash 配置文件解析器"""
    
    def __init__(self, config_path: str = "data/uploaded_clash.yaml"):
        self.config_path = Path(config_path)
    
    def exists(self) -> bool:
        """检查配置文件是否存在"""
        return self.config_path.exists()
    
    def read_config(self) -> str:
        """读取配置文件原始内容"""
        if not self.config_path.exists():
            raise FileNotFoundError(f"配置文件不存在: {self.config_path}")
        return self.config_path.read_text(encoding="utf-8")
    
    def write_config(self, content: str) -> None:
        """写入配置文件"""
        # 确保目录存在
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(content, encoding="utf-8")
    
    def parse_yaml(self) -> dict:
        """解析 YAML 配置"""
        content = self.read_config()
        return yaml.safe_load(content)
    
    def get_proxy_providers(self) -> dict:
        """获取 proxy-providers 配置"""
        config = self.parse_yaml()
        return config.get("proxy-providers", {})
    
    def parse_subscription_date(self, key: str) -> tuple[str, Optional[date]]:
        """
        从 key 中解析订阅名称和过期日期
        
        格式: name-YYYY-MM-DD
        返回: (name, expire_date) 或 (key, None)
        """
        match = DATE_PATTERN.match(key)
        if match:
            name = match.group(1)
            year = int(match.group(2))
            month = int(match.group(3))
            day = int(match.group(4))
            try:
                expire_date = date(year, month, day)
                return name, expire_date
            except ValueError:
                pass
        return key, None
    
    def calculate_status(self, expire_date: Optional[date], today: Optional[date] = None) -> tuple[Optional[int], str]:
        """
        计算订阅状态
        
        返回: (days_remaining, status)
        """
        if expire_date is None:
            return None, "unknown"
        
        if today is None:
            today = date.today()
        
        days_remaining = (expire_date - today).days
        
        if days_remaining < 0:
            return days_remaining, "expired"
        elif days_remaining <= 7:
            return days_remaining, "expiring"
        else:
            return days_remaining, "active"
    
    def get_subscription_status(self, today: Optional[date] = None) -> list[SubscriptionInfo]:
        """
        获取所有订阅的状态信息
        
        返回订阅列表，包含过期天数和状态告警
        """
        if not self.exists():
            return []
        
        providers = self.get_proxy_providers()
        subscriptions = []
        
        for key, value in providers.items():
            name, expire_date = self.parse_subscription_date(key)
            days_remaining, status = self.calculate_status(expire_date, today)
            
            url = None
            if isinstance(value, dict):
                url = value.get("url")
            
            info = SubscriptionInfo(
                key=key,
                name=name,
                expire_date=expire_date,
                days_remaining=days_remaining,
                status=status,
                url=url,
            )
            subscriptions.append(info)
        
        # 按状态排序: expired > expiring > active > unknown
        status_order = {"expired": 0, "expiring": 1, "active": 2, "unknown": 3}
        subscriptions.sort(key=lambda x: (status_order.get(x.status, 4), x.days_remaining or 999))
        
        return subscriptions
    
    def get_status_summary(self, today: Optional[date] = None) -> dict:
        """
        获取订阅状态汇总
        
        返回格式:
        {
            "total": 3,
            "expired": 0,
            "expiring": 1,
            "active": 2,
            "unknown": 0,
            "subscriptions": [...]
        }
        """
        subscriptions = self.get_subscription_status(today)
        
        summary = {
            "total": len(subscriptions),
            "expired": sum(1 for s in subscriptions if s.status == "expired"),
            "expiring": sum(1 for s in subscriptions if s.status == "expiring"),
            "active": sum(1 for s in subscriptions if s.status == "active"),
            "unknown": sum(1 for s in subscriptions if s.status == "unknown"),
            "subscriptions": [
                {
                    "key": s.key,
                    "name": s.name,
                    "expire_date": s.expire_date.isoformat() if s.expire_date else None,
                    "days_remaining": s.days_remaining,
                    "status": s.status,
                }
                for s in subscriptions
            ],
        }
        
        return summary
