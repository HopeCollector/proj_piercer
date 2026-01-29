#!/bin/bash
# 清理和重置 Piercer 服务
# ⚠️ 使用前请修改下方变量

set -e

# ↓↓↓ 请修改为实际部署路径和服务器公网 IP ↓↓↓
PIERCER_DIR="/opt/piercer"
SERVER_ENDPOINT="your.server.ip:51820"

echo "=== 停止服务 ==="
pkill -f uvicorn 2>/dev/null || true

echo "=== 清理测试文件 ==="
rm -f "$PIERCER_DIR/test_dns.py"
rm -f "$PIERCER_DIR/server.log"
rm -rf "$PIERCER_DIR/data/"

echo "=== 生成新的 WireGuard 配置 ==="
NEW_KEY=$(wg genkey)
NEW_PUB=$(echo $NEW_KEY | wg pubkey)

cat > /etc/wireguard/wg0.conf << EOF
[Interface]
Address = 10.8.0.1/24
ListenPort = 51820
PrivateKey = $NEW_KEY
PostUp = iptables -A INPUT -p udp --dport 51820 -j ACCEPT; iptables -A FORWARD -i %i -j ACCEPT; iptables -A FORWARD -o %i -j ACCEPT; iptables -t nat -A POSTROUTING -s 10.8.0.0/24 -o eth0 -j MASQUERADE
PostDown = iptables -D INPUT -p udp --dport 51820 -j ACCEPT; iptables -D FORWARD -i %i -j ACCEPT; iptables -D FORWARD -o %i -j ACCEPT; iptables -t nat -D POSTROUTING -s 10.8.0.0/24 -o eth0 -j MASQUERADE
EOF

chmod 600 /etc/wireguard/wg0.conf

echo "=== 启动 WireGuard ==="
wg-quick up wg0

echo "=== 启动 Piercer API (后台运行) ==="
# ↓↓↓ 请根据实际部署路径修改 ↓↓↓
cd /opt/piercer
PIERCER_ENABLE_WG_RELOAD=true PIERCER_SERVER_ENDPOINT="$SERVER_ENDPOINT" nohup uv run uvicorn piercer.main:app --host 10.8.0.1 --port 8000 > server.log 2>&1 &

sleep 2

echo ""
echo "=== 完成 ==="
echo "服务器公钥: $NEW_PUB"
echo "WireGuard 状态:"
wg show wg0
echo ""
echo "API 状态:"
curl -s http://10.8.0.1:8000/ || echo "API 未就绪"
