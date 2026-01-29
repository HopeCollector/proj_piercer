"""
Tests for Clash Parser
"""

import pytest
from datetime import date
from pathlib import Path
import tempfile

from piercer.core.clash_parser import ClashParser, SubscriptionInfo


# 测试用的配置文件内容
SAMPLE_CLASH_CONFIG = """
port: 7890
socks-port: 7891
allow-lan: true

proxy-providers:
  provider-a-2026-02-15:
    type: http
    url: "https://example.com/sub1"
    interval: 3600
    path: ./providers/provider-a.yaml
    
  provider-b-2026-01-20:
    type: http
    url: "https://example.com/sub2"
    interval: 3600
    path: ./providers/provider-b.yaml
    
  legacy-provider:
    type: http
    url: "https://example.com/sub3"
    interval: 3600
    path: ./providers/legacy.yaml

proxies: []

proxy-groups:
  - name: PROXY
    type: select
    use:
      - provider-a-2026-02-15
      - provider-b-2026-01-20

rules:
  - MATCH,PROXY
"""


@pytest.fixture
def temp_config_file():
    """创建临时配置文件"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(SAMPLE_CLASH_CONFIG)
        f.flush()
        yield f.name
    Path(f.name).unlink(missing_ok=True)


@pytest.fixture
def parser(temp_config_file):
    """创建解析器实例"""
    return ClashParser(temp_config_file)


class TestClashParser:
    """测试 ClashParser 类"""
    
    def test_exists(self, parser):
        assert parser.exists() is True
    
    def test_read_config(self, parser):
        content = parser.read_config()
        assert "proxy-providers" in content
    
    def test_parse_yaml(self, parser):
        config = parser.parse_yaml()
        assert "proxy-providers" in config
        assert len(config["proxy-providers"]) == 3
    
    def test_get_proxy_providers(self, parser):
        providers = parser.get_proxy_providers()
        assert len(providers) == 3
        assert "provider-a-2026-02-15" in providers
    
    def test_parse_subscription_date_valid(self, parser):
        name, expire_date = parser.parse_subscription_date("provider-a-2026-02-15")
        assert name == "provider-a"
        assert expire_date == date(2026, 2, 15)
    
    def test_parse_subscription_date_invalid(self, parser):
        name, expire_date = parser.parse_subscription_date("legacy-provider")
        assert name == "legacy-provider"
        assert expire_date is None
    
    def test_calculate_status_active(self, parser):
        test_date = date(2026, 1, 28)
        expire_date = date(2026, 2, 15)
        
        days, status = parser.calculate_status(expire_date, test_date)
        assert days == 18
        assert status == "active"
    
    def test_calculate_status_expiring(self, parser):
        test_date = date(2026, 2, 10)
        expire_date = date(2026, 2, 15)
        
        days, status = parser.calculate_status(expire_date, test_date)
        assert days == 5
        assert status == "expiring"
    
    def test_calculate_status_expired(self, parser):
        test_date = date(2026, 2, 20)
        expire_date = date(2026, 2, 15)
        
        days, status = parser.calculate_status(expire_date, test_date)
        assert days == -5
        assert status == "expired"
    
    def test_calculate_status_unknown(self, parser):
        days, status = parser.calculate_status(None)
        assert days is None
        assert status == "unknown"
    
    def test_get_subscription_status(self, parser):
        test_date = date(2026, 1, 28)
        subscriptions = parser.get_subscription_status(test_date)
        
        assert len(subscriptions) == 3
        
        # 检查排序 (expired/expiring first, then by days)
        # provider-b 过期了, legacy 是 unknown, provider-a 是 active
    
    def test_get_status_summary(self, parser):
        test_date = date(2026, 1, 28)
        summary = parser.get_status_summary(test_date)
        
        assert summary["total"] == 3
        assert "subscriptions" in summary
        assert len(summary["subscriptions"]) == 3


class TestClashParserNoFile:
    """测试文件不存在的情况"""
    
    def test_exists_false(self):
        parser = ClashParser("/nonexistent/path.yaml")
        assert parser.exists() is False
    
    def test_read_config_raises(self):
        parser = ClashParser("/nonexistent/path.yaml")
        with pytest.raises(FileNotFoundError):
            parser.read_config()
    
    def test_get_subscription_status_empty(self):
        parser = ClashParser("/nonexistent/path.yaml")
        subscriptions = parser.get_subscription_status()
        assert subscriptions == []
