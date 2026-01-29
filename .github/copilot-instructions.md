# Project Environment & Context

## Platform Details
- **OS:** Windows 11 (x64)
- **Shell:** PowerShell
- **Python Environment:** 
  - Managed strictly by `uv`.
  - No system Python interpreter available.
  - Always use `uv venv` and `uv pip` for package management.

## Network Configuration
- **Local Network:** Standard Home Broadband.
- **Remote Target (SSH):**
  - **Host Alias:** `srlab-routor`
  - **Network Constraints:** Remote is on a metered IPv4 network.
  - **Connection Strategy:** ALWAYS prefer direct IPv6 connection to avoid metering charges.
  - **Data Transfer:** Avoid large IPv4 file transfers.

## Communication
- **Language:** Always use Chinese when reporting or chatting.

## Git Commit Convention
- **格式**: `动作(范围): 言简意赅的概括`
- **动作类型**: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `style`
- **单行原则**: 每个 commit 只做一件事，用一行描述
- **复杂变更处理**:
  - (优先) 拆分为多个 commit，每个保持单行描述
  - (备选) 首行概括 + 空行 + 两空格缩进的详细说明
- **示例**:
  ```
  feat(wg): 添加 peer 热重载功能
  
  fix(dns): 修复域名解析大小写敏感问题
  
  refactor(config): 敏感信息改用环境变量注入
    - server_endpoint 移除硬编码默认值
    - 添加 is_server_endpoint_configured() 检查方法
    - 更新 systemd 服务配置模板
  ```