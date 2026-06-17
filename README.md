# astrbot-plugin-mcsm-status

AstrBot MCSManager 服务器状态查询与管理插件 / A plugin for querying and managing MCSManager servers via AstrBot

> [!NOTE]
> 灵感来自 koishi-plugin-mcsm-status以及astrbot_plugin_mcsmanager加上根据个人需求而来，基于 AstrBot 插件系统重新实现。
>
> [AstrBot](https://github.com/AstrBotDevs/AstrBot) 是一个支持多平台的智能对话助手，可部署在 QQ、Telegram、飞书、钉钉、Discord 等主流即时通讯平台。本插件为其提供 MCSManager 游戏服务器面板的查询与管理能力。

## ✨ 功能

- 🔍 查询 MCSManager 面板中所有实例的运行状态（CPU、内存、玩家数、运行时长等）
- 📋 列出面板中所有实例及其当前状态
- ▶️ 远程启动、停止、重启、强制终止实例
- ⌨️ 向运行中的实例发送控制台命令
- 🖼️ 生成可视化状态面板图片，支持自定义背景图轮询
- 🔒 三级权限控制（超级管理员 / 管理员 / 成员），可按角色分配命令权限
- 🛡️ 群聊白名单，限制仅指定群聊可使用
- 🖧 多节点支持，自动遍历所有守护进程节点

## 📦 安装

1. 将本仓库克隆或下载到 AstrBot 的插件目录：
data/plugins/astrbot_plugin_mcsm_status/

text
2. 安装依赖：
2. 安装依赖：
pip install -r requirements.txt

text
3. 在 AstrBot WebUI 的插件管理中加载或重载插件。
4. 在插件配置页面填写 MCSManager 面板地址和 API Key。

## ⚙️ 配置项

### 连接配置

| 配置项 | 说明 |
| --- | --- |
| `base_url` | MCSManager 面板地址，例如 `http://127.0.0.1:23333` |
| `api_key` | MCSManager API Key，在面板 → 用户设置 → API 接口中生成 |
| `timeout` | HTTP 请求超时时间（秒），默认 `10` |

### 权限配置

| 配置项 | 说明 |
| --- | --- |
| `super_admin_ids` | 超级管理员用户 ID 列表，拥有所有命令权限 |
| `admin_ids` | 管理员用户 ID 列表，可使用下方配置的命令 |
| `admin_commands` | 管理员可用命令列表，默认全部 |
| `member_ids` | 普通成员用户 ID 列表，可使用下方配置的命令 |
| `member_commands` | 成员可用命令列表，默认仅查询类命令 |
| `group_whitelist` | 群聊白名单（群号列表），为空则所有群聊均可使用 |

### 可视化面板配置

| 配置项 | 说明 |
| --- | --- |
| `background_urls` | 面板背景图 URL 列表，支持多张轮询，为空则使用默认深色背景。推荐尺寸 680×400 像素。背景图会缓存到插件目录的 `backgrounds/` 文件夹，URL 移除后缓存自动清理。 |

## 🎮 命令

| 命令 | 说明 |
| --- | --- |
| `/mcsm status [名称]` | 查看指定实例状态，不指定则显示所有实例概览 |
| `/mcsm list` | 列出所有实例及其状态 |
| `/mcsm start [名称]` | 启动指定实例 |
| `/mcsm stop [名称]` | 停止指定实例 |
| `/mcsm restart [名称]` | 重启指定实例 |
| `/mcsm kill [名称]` | 强制终止指定实例 |
| `/mcsm cmd [实例名] <命令>` | 向运行中的实例发送控制台命令 |
| `/mcsm panel` | 生成并发送状态面板图片 |
| `/mcsm help` | 显示帮助信息 |

支持的命令别名：`mcsm` / `mcs`、`status` / `状态` / `s`、`list` / `列表` / `ls` 等中英文别名。

实例匹配支持名称模糊匹配，精确匹配优先。

## 📂 文件结构
3. 在 AstrBot WebUI 的插件管理中加载或重载插件。
4. 在插件配置页面填写 MCSManager 面板地址和 API Key。

## ⚙️ 配置项

### 连接配置

| 配置项 | 说明 |
| --- | --- |
| `base_url` | MCSManager 面板地址，例如 `http://127.0.0.1:23333` |
| `api_key` | MCSManager API Key，在面板 → 用户设置 → API 接口中生成 |
| `timeout` | HTTP 请求超时时间（秒），默认 `10` |

### 权限配置

| 配置项 | 说明 |
| --- | --- |
| `super_admin_ids` | 超级管理员用户 ID 列表，拥有所有命令权限 |
| `admin_ids` | 管理员用户 ID 列表，可使用下方配置的命令 |
| `admin_commands` | 管理员可用命令列表，默认全部 |
| `member_ids` | 普通成员用户 ID 列表，可使用下方配置的命令 |
| `member_commands` | 成员可用命令列表，默认仅查询类命令 |
| `group_whitelist` | 群聊白名单（群号列表），为空则所有群聊均可使用 |

### 可视化面板配置

| 配置项 | 说明 |
| --- | --- |
| `background_urls` | 面板背景图 URL 列表，支持多张轮询，为空则使用默认深色背景。推荐尺寸 680×400 像素。背景图会缓存到插件目录的 `backgrounds/` 文件夹，URL 移除后缓存自动清理。 |

## 🎮 命令

| 命令 | 说明 |
| --- | --- |
| `/mcsm status [名称]` | 查看指定实例状态，不指定则显示所有实例概览 |
| `/mcsm list` | 列出所有实例及其状态 |
| `/mcsm start [名称]` | 启动指定实例 |
| `/mcsm stop [名称]` | 停止指定实例 |
| `/mcsm restart [名称]` | 重启指定实例 |
| `/mcsm kill [名称]` | 强制终止指定实例 |
| `/mcsm cmd [实例名] <命令>` | 向运行中的实例发送控制台命令 |
| `/mcsm panel` | 生成并发送状态面板图片 |
| `/mcsm help` | 显示帮助信息 |

支持的命令别名：`mcsm` / `mcs`、`status` / `状态` / `s`、`list` / `列表` / `ls` 等中英文别名。

实例匹配支持名称模糊匹配，精确匹配优先。

## 📂 文件结构
astrbot_plugin_mcsm_status/
├── init.py # 入口文件
├── main.py # 插件主体（命令分发、权限检查、业务逻辑）
├── api.py # MCSManager API 客户端
├── draw.py # 面板图片渲染器（Pillow）
├── _conf_schema.json # 配置面板定义
├── metadata.yaml # 插件元数据
├── requirements.txt # Python 依赖
└── backgrounds/ # 背景图缓存目录（自动创建）

text

## 📓 开发说明

- 本插件基于 MCSManager v10 Web API，节点系统级 CPU/内存数据通过 `/api/overview` 接口获取。
- 实例列表数据通过 `/api/service/remote_service_instances` 接口获取。
- 面板图片渲染依赖 Pillow，如未安装会自动提示。
- 背景图使用 URL 本地缓存机制，减少网络请求。
- 权限系统兼容 AstrBot 不同版本的事件对象接口。

## Supports

- [AstrBot Repo](https://github.com/AstrBotDevs/AstrBot)
- [MCSManager 官网](https://mcsmanager.com/)
- [MCSManager GitHub](https://github.com/MCSManager/MCSManager)
- [AstrBot 插件开发文档](https://docs.astrbot.app/dev/star/plugin-new.html)

---

> 由 MiMo-v2.5-pro 以及 DeepSeek 协助完成