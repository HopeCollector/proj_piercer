"""
Tests for WireGuard Parser
"""

import pytest
from datetime import date
from pathlib import Path
import tempfile

from piercer.core.wg_parser import (
    WgParser,
    WgPeer,
    PEER_PATTERN,
    generate_client_config_template,
)


# 测试用的配置文件内容
SAMPLE_WG_CONFIG = """[Interface]
PrivateKey = SERVER_PRIVATE_KEY
Address = 10.8.0.1/24
ListenPort = 51820
PostUp = iptables -A FORWARD -i wg0 -j ACCEPT
PostDown = iptables -D FORWARD -i wg0 -j ACCEPT

# ==========================================
# ClientName: macbook-pro
# AddedAt: 2026-01-27
# ==========================================
[Peer]
PublicKey = CLIENT1_PUBLIC_KEY
AllowedIPs = 10.8.0.5/32

# ==========================================
# ClientName: home-nas
# AddedAt: 2026-01-27
# ==========================================
[Peer]
PublicKey = CLIENT2_PUBLIC_KEY
AllowedIPs = 10.8.0.6/32
Endpoint = nas.myhome.com:51820

# ==========================================
# ClientName: phone-android
# AddedAt: 2026-01-28
# ==========================================
[Peer]
PublicKey = CLIENT3_PUBLIC_KEY
AllowedIPs = 10.8.0.7/32
PresharedKey = PRESHARED_KEY_VALUE
"""


@pytest.fixture
def temp_config_file():
    """创建临时配置文件"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
        f.write(SAMPLE_WG_CONFIG)
        f.flush()
        yield f.name
    Path(f.name).unlink(missing_ok=True)


@pytest.fixture
def parser(temp_config_file):
    """创建解析器实例"""
    return WgParser(temp_config_file)


class TestPeerPattern:
    """测试正则表达式"""
    
    def test_pattern_matches_peers(self):
        matches = list(PEER_PATTERN.finditer(SAMPLE_WG_CONFIG))
        assert len(matches) == 3
    
    def test_pattern_extracts_name(self):
        matches = list(PEER_PATTERN.finditer(SAMPLE_WG_CONFIG))
        names = [m.group(1).strip() for m in matches]
        assert names == ["macbook-pro", "home-nas", "phone-android"]
    
    def test_pattern_extracts_date(self):
        matches = list(PEER_PATTERN.finditer(SAMPLE_WG_CONFIG))
        dates = [m.group(2).strip() for m in matches]
        assert dates == ["2026-01-27", "2026-01-27", "2026-01-28"]


class TestWgParser:
    """测试 WgParser 类"""
    
    def test_parse_peers(self, parser):
        peers = parser.parse_peers()
        assert len(peers) == 3
        
        # 检查第一个 Peer
        assert peers[0].name == "macbook-pro"
        assert peers[0].public_key == "CLIENT1_PUBLIC_KEY"
        assert peers[0].allowed_ips == "10.8.0.5/32"
        assert peers[0].endpoint is None
    
    def test_parse_peer_with_endpoint(self, parser):
        peers = parser.parse_peers()
        nas_peer = next(p for p in peers if p.name == "home-nas")
        
        assert nas_peer.endpoint == "nas.myhome.com:51820"
    
    def test_parse_peer_with_preshared_key(self, parser):
        peers = parser.parse_peers()
        phone_peer = next(p for p in peers if p.name == "phone-android")
        
        assert phone_peer.preshared_key == "PRESHARED_KEY_VALUE"
    
    def test_get_used_ips(self, parser):
        used_ips = parser.get_used_ips()
        
        # 应包含服务器 IP 和三个客户端 IP
        assert len(used_ips) == 4
        from ipaddress import IPv4Address
        assert IPv4Address("10.8.0.1") in used_ips
        assert IPv4Address("10.8.0.5") in used_ips
        assert IPv4Address("10.8.0.6") in used_ips
        assert IPv4Address("10.8.0.7") in used_ips
    
    def test_get_next_available_ip(self, parser):
        next_ip = parser.get_next_available_ip()
        
        # 应该返回 10.8.0.2 (第一个未使用的)
        from ipaddress import IPv4Address
        assert next_ip == IPv4Address("10.8.0.2")
    
    def test_check_ip_conflict(self, parser):
        assert parser.check_ip_conflict("10.8.0.5") is True
        assert parser.check_ip_conflict("10.8.0.2") is False
    
    def test_check_name_conflict(self, parser):
        assert parser.check_name_conflict("macbook-pro") is True
        assert parser.check_name_conflict("new-device") is False
    
    def test_get_p2p_candidates(self, parser):
        candidates = parser.get_p2p_candidates()
        
        assert len(candidates) == 1
        assert candidates[0].name == "home-nas"
        assert candidates[0].endpoint == "nas.myhome.com:51820"
    
    def test_generate_peer_block(self, parser):
        block = parser.generate_peer_block(
            name="test-device",
            public_key="TEST_PUBLIC_KEY",
            assigned_ip="10.8.0.10",
            added_at="2026-01-28",
            endpoint="test.example.com:51820",
        )
        
        assert "ClientName: test-device" in block
        assert "AddedAt: 2026-01-28" in block
        assert "PublicKey = TEST_PUBLIC_KEY" in block
        assert "AllowedIPs = 10.8.0.10/32" in block
        assert "Endpoint = test.example.com:51820" in block
    
    def test_add_peer(self, parser):
        parser.add_peer(
            name="new-device",
            public_key="NEW_PUBLIC_KEY",
            assigned_ip="10.8.0.10",
            added_at="2026-01-28",
        )
        
        # 重新解析
        peers = parser.parse_peers()
        assert len(peers) == 4
        
        new_peer = next(p for p in peers if p.name == "new-device")
        assert new_peer.public_key == "NEW_PUBLIC_KEY"
    
    def test_add_peer_name_conflict(self, parser):
        with pytest.raises(ValueError, match="设备名称已存在"):
            parser.add_peer(
                name="macbook-pro",
                public_key="ANOTHER_KEY",
                assigned_ip="10.8.0.10",
                added_at="2026-01-28",
            )
    
    def test_add_peer_ip_conflict(self, parser):
        with pytest.raises(ValueError, match="IP 地址已被占用"):
            parser.add_peer(
                name="another-device",
                public_key="ANOTHER_KEY",
                assigned_ip="10.8.0.5",
                added_at="2026-01-28",
            )
    
    def test_remove_peer(self, parser):
        result = parser.remove_peer("macbook-pro")
        assert result is True
        
        peers = parser.parse_peers()
        assert len(peers) == 2
        assert not any(p.name == "macbook-pro" for p in peers)
    
    def test_remove_peer_not_found(self, parser):
        result = parser.remove_peer("nonexistent")
        assert result is False


class TestClientConfigTemplate:
    """测试客户端配置模板生成"""
    
    def test_generate_template(self):
        template = generate_client_config_template(
            server_public_key="SERVER_PUBLIC_KEY",
            server_endpoint="vpn.example.com:51820",
            assigned_ip="10.8.0.10",
        )
        
        assert "SERVER_PUBLIC_KEY" in template
        assert "vpn.example.com:51820" in template
        assert "10.8.0.10/24" in template
        assert "<YOUR_PRIVATE_KEY>" in template
