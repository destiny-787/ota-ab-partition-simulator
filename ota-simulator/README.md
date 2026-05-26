# OTA A/B 分区升级模拟器

模拟智能硬件 OTA 固件升级的 A/B 分区流程：**版本检查 → 下载 → 校验 → 写入 → 切换 → 失败回滚**。

C/S 架构，后端 Python FastAPI，提供 CLI 命令行工具和 Web 可视化界面两种交互方式。

## 快速开始

```bash
# 1. 克隆项目
git clone https://github.com/destiny-787/ota-ab-partition-simulator.git
cd ota-ab-partition-simulator/ota-simulator

# 2. 安装依赖
pip install -r requirements.txt

# 3. 启动服务端
python -m server.main

# 4. CLI 客户端（新开终端）
python client-cli/cli.py check       # 查看设备状态
python client-cli/cli.py firmware    # 列出可用固件
python client-cli/cli.py download 2.0.0  # 下载固件
python client-cli/cli.py verify      # 校验固件
python client-cli/cli.py upgrade 2.0.0  # 执行升级
python client-cli/cli.py upgrade 2.0.0 --fail  # 模拟失败升级
python client-cli/cli.py rollback    # 手动回滚

# 5. Web 客户端
# 浏览器打开 http://localhost:8001
```

## 项目结构

```
ota-simulator/
├── server/
│   ├── main.py              # FastAPI 入口 + CORS + 静态文件
│   ├── api.py               # REST API (6 个端点)
│   ├── ws.py                # WebSocket 实时进度推送
│   ├── ota_core.py          # 核心逻辑：下载/校验/升级/回滚
│   ├── models.py            # Pydantic 数据模型
│   └── firmware/
│       ├── repo/            # 固件仓库 (v1.0.0 / v2.0.0)
│       ├── partition_a/     # A 分区
│       ├── partition_b/     # B 分区
│       └── state.json       # 设备状态
├── client-cli/
│   └── cli.py               # CLI 客户端 (Rich 美化)
├── client-web/
│   └── index.html           # Web SPA 客户端
└── requirements.txt
```

## 技术栈

| 层次 | 技术 |
|------|------|
| 后端框架 | Python 3.11+ / FastAPI + uvicorn |
| 通信协议 | REST API + WebSocket |
| CLI 客户端 | Python + Rich |
| Web 客户端 | 纯 HTML/CSS/JS (SPA) |
| 状态持久化 | JSON 文件 |

## API 接口

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/api/version` | 查询当前分区状态、版本、升级历史 |
| GET | `/api/firmware` | 获取可用固件版本列表 |
| POST | `/api/download` | 下载固件到非激活分区 |
| POST | `/api/verify` | SHA256+MD5 双重校验 |
| POST | `/api/upgrade` | 执行升级，支持模拟失败 |
| POST | `/api/rollback` | 手动回滚到备用分区 |
| WS | `/ws/progress` | 实时推送升级进度 |

## 升级流程

```
下载固件 ──→ SHA256+MD5 校验 ──→ 写入非激活分区 ──→ 切换激活分区
                                        │
                                        ├── 写入成功 → 升级完成
                                        └── 写入失败 → 自动回滚到原分区
```

## Web 界面

- 顶部状态栏：当前激活分区 + 版本号
- 左侧面板：固件选择 + 操作按钮（下载/校验/升级/回滚）
- 右侧卡片：A/B 分区可视化（当前分区蓝色高亮）
- 历史区域：可折叠升级历史，点击展开详情
- 底部日志：持久化操作日志 + WebSocket 实时进度条

## CLI 命令参考

| 命令 | 功能 |
|------|------|
| `cli.py check` | 查看设备当前分区状态和版本 |
| `cli.py firmware` | 列出固件仓库中可用版本 |
| `cli.py download <ver>` | 下载指定版本到非激活分区 |
| `cli.py verify` | 校验已下载固件的 SHA256+MD5 |
| `cli.py upgrade <ver>` | 执行 OTA 升级 |
| `cli.py upgrade <ver> --fail` | 执行升级（模拟写入失败） |
| `cli.py rollback` | 手动回滚到备用分区 |
