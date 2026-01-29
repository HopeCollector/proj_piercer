# Project Piercer 开发计划书 (Final Version)

## 1. 项目愿景 (Executive Summary)

Piercer 是一个极简、无头 (Headless) 的网络边界管理中枢。 它的核心使命是打破局域网的限制：

- 对抗 GFW：作为 Clash 订阅的中转站与分发点。
- 对抗 NAT：作为 WireGuard 的 P2P 交换中心与信令服。

它不提供图形界面，只提供 OpenAPI (RPC 风格)，专为 AI Agent (智能体) 操控而生。

## 2. 系统架构 (System Architecture)

### 2.1 运行环境

* **OS**: Linux (Ubuntu/Debian/CentOS), Systemd 托管。
* **Runtime**: Python 3.10+。
* **Network Stack**: 隧道内仅 IPv4 (降低路由复杂度)，物理连接支持 IPv4/IPv6。

### 2.2 端口与监听策略

| 服务组件 | 协议 | 端口 | 绑定地址 | 可见性 | 用途 |
| --- | --- | --- | --- | --- | --- |
| **WireGuard** | UDP | **51820** | `0.0.0.0` | **公网** | VPN 数据隧道。 |
| **Management API** | TCP | **8000** | `10.8.0.1` | **内网** | Agent 调用的管理接口 (仅限 VPN 内部)。 |
| **Internal DNS** | UDP | **53** | `10.8.0.1` | **内网** | 仅解析 `*.vpn.example.com`。 |

## 3. 数据存储规范 (Data Specification)

### 3.1 WireGuard 配置 (`/etc/wireguard/wg0.conf`)

**存储逻辑**：

* **元数据** (Name, Date)：存储于标准化的**注释块**。
* **P2P 属性** (Endpoint)：直接使用 INI 标准字段 `Endpoint`。
* **IP 地址**：标准 `AllowedIPs` 字段。

**文件内容范例**：

```ini
[Interface]
# Server 自身配置...
ListenPort = 51820

# ==========================================
# ClientName: macbook-pro
# AddedAt: 2026-01-27
# ==========================================
[Peer]
PublicKey = <Base64_Key>
AllowedIPs = 10.8.0.5/32
# 漫游设备：无 Endpoint 字段

# ==========================================
# ClientName: home-nas
# AddedAt: 2026-01-27
# ==========================================
[Peer]
PublicKey = <Base64_Key>
AllowedIPs = 10.8.0.6/32
Endpoint = nas.myhome.com:51820
# 固定设备：有 Endpoint 字段，Server 可主动连接，也可作为 P2P 对象

```

### 3.2 Clash 配置 (`data/uploaded_clash.yaml`)

**存储逻辑**：

* **文件处理**：用户上传整个文件，Server 原样保存，不做任何修改。
* **订阅分析**：只读解析 `proxy-providers` 字段，提取 Key 名进行日期分析。

## 4. API 接口规范 (RPC Specification)

所有响应状态码为 `200 OK`，业务逻辑结果见 JSON Body。

### 4.1 WireGuard 模块 (`/api/wg`)

|**方法**|**路径**|**功能描述**|**核心逻辑**|
|---|---|---|---|
|**GET**|`/config/template`|**获取填空模板**|1. 扫描 `wg0.conf` 计算下一个空闲 IPv4 (Set Difference)。<br><br>  <br><br>2. 提取 Server 公钥。<br><br>  <br><br>3. 返回包含指引注释的 Config 文本。|
|**GET**|`/peer/list`|**查询状态**|1. 解析 `wg0.conf` 注释获取 Name。<br><br>  <br><br>2. 运行 `wg show wg0 dump` 获取握手/流量。<br><br>  <br><br>3. 合并返回。|
|**GET**|`/peer/p2p_candidates`|**获取直连节点**|1. 扫描 `wg0.conf`。<br><br>  <br><br>2. 筛选出所有**拥有 `Endpoint` 字段**的 Peer。<br><br>  <br><br>3. 返回列表，供客户端配置 Site-to-Site。|
|**POST**|`/peer/add`|**注册设备**|**参数**: `{name, public_key, assigned_ip, endpoint(可选)}`<br><br>  <br><br>1. 校验 IP 冲突。<br><br>  <br><br>2. 组装 INI 块 (含注释)。<br><br>  <br><br>3. 若有 `endpoint` 则写入该行。<br><br>  <br><br>4. 追加写入文件 -> `wg syncconf`。|
|**POST**|`/peer/del`|**移除设备**|**参数**: `{name}`<br><br>  <br><br>1. 正则定位注释块+Peer块。<br><br>  <br><br>2. 内存删除 -> 覆写文件 -> `wg syncconf`。|

### 4.2 Clash 模块 (`/api/clash`)

|**方法**|**路径**|**功能描述**|**核心逻辑**|
|---|---|---|---|
|**POST**|`/config/upload`|**上传配置**|接收 Body 文本，覆盖写入 `uploaded_clash.yaml`。|
|**GET**|`/config/download`|**下载配置**|读取并返回 `uploaded_clash.yaml` 内容。|
|**GET**|`/subscription/status`|**订阅看板**|1. 解析 YAML 的 `proxy-providers`。<br><br>  <br><br>2. 正则匹配 Key: `^(.+)-(\d{4})-(\d{2})-(\d{2})$`。<br><br>  <br><br>3. 返回过期天数与状态告警。|

### 4.3 内部 DNS (`UDP Only`)

* **不提供 HTTP API**。
* **逻辑**：
* 监听 `10.8.0.1:53`。
* 收到 A 记录查询 -> 解析 `wg0.conf` (Name -> AllowedIPs)。
* 匹配 `*.vpn.example.com` 则返回对应 IP。
* 不匹配则 NXDOMAIN。



---

## 5. 关键业务逻辑实现细节

### 5.1 正则提取器 (The Metadata Extractor)

为了准确提取带注释的 Block，将使用以下 Regex 逻辑：

```python
# 匹配模式：注释头 + Peer块内容 (直到下一个注释头或文件结束)
# Group 1: Name, Group 2: Date, Group 3: Block Content
PATTERN = r"^# ClientName: (.+?)\n# AddedAt: (.+?)\n\[Peer\]\n(.*?)(?=\n# ClientName|\Z)"

# 提取 Endpoint 的子模式 (在 Group 3 中查找)
ENDPOINT_PATTERN = r"Endpoint\s*=\s*(.+)"

```

### 5.2 热重载 (Hot Reload)

保证不中断现有连接的操作链：

```python
def reload_wg():
    # 1. Strip: 生成仅含 Peer 的纯净配置
    subprocess.run("wg-quick strip wg0 > /tmp/wg0.strip", shell=True)
    # 2. Sync: 仅同步差异部分
    subprocess.run("wg syncconf wg0 /tmp/wg0.strip", shell=True)
    # 3. Cleanup
    os.remove("/tmp/wg0.strip")

```

---

## 6. 用户指引 (Agent System Prompt)

Agent 在回复用户时，必须包含以下标准化指导：

> **[密钥生成指南]**
> Server 已为您分配 IP: `{assigned_ip}`。请在您的本地设备生成密钥：
> 1. **生成密钥对**: `wg genkey | tee private.key | wg pubkey > public.key`
> 2. **生成预共享密钥**: `wg genpsk > preshared.key`
> 
> 
> **请仅提交 `public.key` 和 `preshared.key` 给 Agent。不要泄露 `private.key`。**

---

## 7. 实施路线图 (Roadmap)

1. **Phase 1: 核心库开发 (`core/`)**
* 编写 `wg_parser.py`: 实现 `wg0.conf` 的正则读写、IP 冲突检测。
* 编写 `clash_parser.py`: 实现 YAML 日期提取。


2. **Phase 2: API 开发 (`main.py`)**
* 构建 FastAPI 骨架。
* 实现 RPC 接口逻辑。
* **自测**: 使用 Postman 模拟 Agent 添加/删除 Peer。


3. **Phase 3: 系统集成**
* 编写 `dns_server.py` (UDP Thread)。
* 编写 `systemd` 单元文件。
* 在 Linux 环境下实测 `wg` 命令调用。


4. **Phase 4: Agent 对接**
* 生成 `openapi.json`。
* 配置 Dify/GPTs Action。
