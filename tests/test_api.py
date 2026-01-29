"""
Tests for API Endpoints
"""

import pytest
from fastapi.testclient import TestClient
from pathlib import Path
import tempfile
import os
from unittest.mock import patch


SAMPLE_WG_CONFIG = """[Interface]
PrivateKey = SERVER_PRIVATE_KEY
Address = 10.8.0.1/24
ListenPort = 51820

# ==========================================
# ClientName: test-device
# AddedAt: 2026-01-27
# ==========================================
[Peer]
PublicKey = TEST_PUBLIC_KEY
AllowedIPs = 10.8.0.5/32
"""


@pytest.fixture
def temp_wg_config():
    """创建临时 WG 配置文件"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
        f.write(SAMPLE_WG_CONFIG)
        f.flush()
        yield f.name
    Path(f.name).unlink(missing_ok=True)


@pytest.fixture
def temp_clash_dir():
    """创建临时 Clash 配置目录"""
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def client(temp_wg_config, temp_clash_dir):
    """创建测试客户端"""
    # 创建新的 Settings 实例并 patch
    from piercer.config import Settings
    
    test_settings = Settings()
    test_settings.wg_config_path = temp_wg_config
    test_settings.clash_config_path = f"{temp_clash_dir}/clash.yaml"
    test_settings.enable_wg_reload = False
    
    with patch("piercer.routers.wg.settings", test_settings), \
         patch("piercer.routers.clash.settings", test_settings):
        from piercer.main import app
        yield TestClient(app)


class TestHealthEndpoints:
    """测试健康检查端点"""
    
    def test_root(self, client):
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Piercer"
        assert data["status"] == "running"
    
    def test_health(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


class TestWgEndpoints:
    """测试 WireGuard API"""
    
    def test_get_config_template(self, client):
        response = client.get("/api/wg/config/template")
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] is True
        assert data["assigned_ip"] == "10.8.0.2"  # 下一个可用 IP
        assert "config_template" in data
        assert "instructions" in data
    
    def test_list_peers(self, client):
        response = client.get("/api/wg/peer/list")
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] is True
        assert data["count"] == 1
        assert data["peers"][0]["name"] == "test-device"
    
    def test_get_p2p_candidates(self, client):
        response = client.get("/api/wg/peer/p2p_candidates")
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] is True
        assert data["count"] == 0  # 测试配置中没有 Endpoint
    
    def test_add_peer(self, client):
        response = client.post("/api/wg/peer/add", json={
            "name": "new-device",
            "public_key": "NEW_PUBLIC_KEY",
            "assigned_ip": "10.8.0.10",
        })
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] is True
        assert "new-device" in data["message"]
    
    def test_add_peer_conflict(self, client):
        response = client.post("/api/wg/peer/add", json={
            "name": "test-device",
            "public_key": "ANOTHER_KEY",
            "assigned_ip": "10.8.0.10",
        })
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] is False
        assert "已存在" in data["message"]
    
    def test_delete_peer(self, client):
        response = client.post("/api/wg/peer/del", json={
            "name": "test-device",
        })
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] is True
    
    def test_delete_peer_not_found(self, client):
        response = client.post("/api/wg/peer/del", json={
            "name": "nonexistent",
        })
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] is False


class TestClashEndpoints:
    """测试 Clash API"""
    
    def test_upload_config(self, client):
        config_content = """
port: 7890
proxy-providers:
  test-2026-02-15:
    type: http
    url: "https://example.com/sub"
"""
        response = client.post(
            "/api/clash/config/upload",
            content=config_content,
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] is True
    
    def test_download_config_not_found(self, client, temp_clash_dir):
        # 确保使用一个不存在的路径
        from piercer.config import Settings
        from unittest.mock import patch
        
        test_settings = Settings()
        test_settings.clash_config_path = f"{temp_clash_dir}/nonexistent.yaml"
        
        with patch("piercer.routers.clash.settings", test_settings):
            from piercer.main import app
            test_client = TestClient(app)
            response = test_client.get("/api/clash/config/download")
            assert response.status_code == 404
    
    def test_download_config_after_upload(self, client):
        # 先上传
        config_content = "port: 7890\n"
        client.post("/api/clash/config/upload", content=config_content)
        
        # 再下载
        response = client.get("/api/clash/config/download")
        assert response.status_code == 200
        assert "port: 7890" in response.text
    
    def test_subscription_status_empty(self, client):
        response = client.get("/api/clash/subscription/status")
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] is True
        assert data["total"] == 0
    
    def test_subscription_status_with_data(self, client):
        config_content = """
port: 7890
proxy-providers:
  provider-a-2026-02-15:
    type: http
    url: "https://example.com/sub"
"""
        client.post("/api/clash/config/upload", content=config_content)
        
        response = client.get("/api/clash/subscription/status")
        assert response.status_code == 200
        
        data = response.json()
        assert data["total"] == 1
        assert data["subscriptions"][0]["name"] == "provider-a"
