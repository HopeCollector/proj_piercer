# Piercer

极简、无头 (Headless) 的网络边界管理中枢。

## 功能

- **对抗 GFW**：作为 Clash 订阅的中转站与分发点
- **对抗 NAT**：作为 WireGuard 的 P2P 交换中心与信令服务

## 快速开始

### 环境要求

- Python 3.10+
- uv (Python 包管理器)
- WireGuard (生产环境)

### 安装

```bash
# 创建虚拟环境并安装依赖
uv sync
```

### 配置

复制环境变量示例文件并修改：

```bash
cp .env.example .env
# 编辑 .env，至少配置 PIERCER_SERVER_ENDPOINT
```

**必须配置的环境变量：**
- `PIERCER_SERVER_ENDPOINT`: 服务器公网地址 (如 `your.server.ip:51820`)

**可选配置：**
- `PIERCER_DNS_DOMAIN`: DNS 域名后缀 (默认 `.vpn.example.com`)
- `PIERCER_ENABLE_WG_RELOAD`: 启用 WireGuard 热重载 (生产环境设为 `true`)

详见 `.env.example` 文件。

### 运行

```bash
# 开发模式
uv run uvicorn piercer.main:app --reload --host 10.8.0.1 --port 8000

# 本地测试模式 (绑定 localhost)
uv run uvicorn piercer.main:app --reload --host 127.0.0.1 --port 8000
```

### API 文档

启动服务后访问：
- OpenAPI JSON: `http://127.0.0.1:8000/openapi.json`
- Swagger UI: `http://127.0.0.1:8000/docs`

## 架构

```
piercer/
├── core/
│   ├── wg_parser.py      # WireGuard 配置解析器
│   └── clash_parser.py   # Clash 配置解析器
├── routers/
│   ├── wg.py             # /api/wg 路由
│   └── clash.py          # /api/clash 路由
├── dns_server.py         # 内部 DNS 服务
└── main.py               # FastAPI 入口
```

## 端口说明

| 服务 | 协议 | 端口 | 可见性 |
|------|------|------|--------|
| WireGuard | UDP | 51820 | 公网 |
| Management API | TCP | 8000 | VPN 内网 |
| Internal DNS | UDP | 53 | VPN 内网 |
