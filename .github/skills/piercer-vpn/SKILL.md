---
name: piercer-vpn
description: 管理 Piercer VPN 服务 - 一个无头的网络边界管理中枢。可以添加/删除 WireGuard Peer 设备、查询 VPN 连接状态、获取客户端配置模板、管理 Clash 订阅。当用户需要管理 VPN 设备、查看 VPN 状态、添加新设备到 VPN 网络时使用此技能。
---

# Piercer VPN 管理技能

Piercer 是一个极简、无头 (Headless) 的网络边界管理中枢，专为 AI Agent 操控而生。

## ⚠️ 前置条件

**必须先接入 VPN 网络才能访问 API。** 所有 API 仅在 VPN 内网 `10.8.0.1:8000` 可访问。

## 服务信息

- **API 基础地址**: `http://10.8.0.1:8000` (仅 VPN 内部可访问)
- **服务器 Endpoint**: 通过 `/api/wg/config/template` 获取
- **服务器公钥**: 通过 `/api/wg/config/template` 获取
- **OpenAPI 文档**: `GET /openapi.json` - 获取完整的 API 规范
- **Swagger UI**: `GET /docs` - 交互式文档

## 首先获取 API 规范

在执行任何操作前，先获取完整的 OpenAPI 规范：

```bash
curl -s http://10.8.0.1:8000/openapi.json
```

这将返回所有可用的 API 端点、参数和响应格式。

## 核心功能

### 1. WireGuard VPN 管理

#### 查询所有设备
```bash
curl -s http://10.8.0.1:8000/api/wg/peer/list
```

返回所有已注册的 VPN 设备，包括：
- 设备名称、公钥、分配的 IP
- 最后握手时间、流量统计

#### 获取新设备配置模板
```bash
curl -s http://10.8.0.1:8000/api/wg/config/template
```

返回：
- 下一个可用的 IP 地址
- 服务器公钥
- 客户端配置文件模板
- 密钥生成指南

#### 添加新设备
```bash
curl -X POST http://10.8.0.1:8000/api/wg/peer/add \
  -H "Content-Type: application/json" \
  -d '{"name":"设备名称","public_key":"Base64公钥","assigned_ip":"10.8.0.x"}'
```

可选参数：
- `endpoint`: 固定设备的公网地址 (如 `nas.home.com:51820`)
- `preshared_key`: 预共享密钥

#### 删除设备
```bash
curl -X POST http://10.8.0.1:8000/api/wg/peer/del \
  -H "Content-Type: application/json" \
  -d '{"name":"设备名称"}'
```

#### 获取 P2P 直连候选
```bash
curl -s http://10.8.0.1:8000/api/wg/peer/p2p_candidates
```

返回所有具有固定 Endpoint 的设备，可用于 Site-to-Site 配置。

### 2. Clash 订阅管理

#### 上传配置
```bash
curl -X POST http://10.8.0.1:8000/api/clash/config/upload \
  -d '配置文件内容'
```

#### 下载配置
```bash
curl -s http://10.8.0.1:8000/api/clash/config/download
```

#### 查看订阅状态
```bash
curl -s http://10.8.0.1:8000/api/clash/subscription/status
```

返回所有 proxy-provider 的过期状态和剩余天数。

## 用户添加新设备的标准流程

当用户想要添加新设备到 VPN 时，按以下步骤操作：

### 步骤 1: 获取配置模板
调用 `/api/wg/config/template` 获取分配的 IP 和服务器信息。

### 步骤 2: 指导用户生成密钥
告知用户在其设备上执行：
```bash
# 生成密钥对
wg genkey | tee private.key | wg pubkey > public.key

# 生成预共享密钥 (可选)
wg genpsk > preshared.key
```

**重要提醒**: 用户只需提交 `public.key` 和 `preshared.key` 的内容，绝不要索取 `private.key`。

### 步骤 3: 注册设备
收到用户的公钥后，调用 `/api/wg/peer/add` 注册设备。

### 步骤 4: 提供客户端配置
将模板中的配置文件提供给用户，指导其填入私钥。

## 内部 DNS

VPN 内部提供 DNS 服务 (10.8.0.1:53)，支持解析：
- `{设备名}.vpn.example.com` → 设备的 VPN IP
- `server.vpn.example.com` → 10.8.0.1
- `gateway.vpn.example.com` → 10.8.0.1

> 域名后缀可通过 `PIERCER_DNS_DOMAIN` 环境变量配置

## 网络拓扑

```
VPN 网段: 10.8.0.0/24
服务器 IP: 10.8.0.1
客户端 IP: 10.8.0.2 ~ 10.8.0.254
```

## 注意事项

1. **必须接入 VPN** 才能访问 API (`10.8.0.1:8000`)
2. 所有 API 响应的 `success` 字段表示操作是否成功
3. 添加/删除设备后会自动热重载 WireGuard，不中断现有连接
4. IP 地址和设备名称不能重复
4. 服务仅在 VPN 内网 (10.8.0.1:8000) 可访问
