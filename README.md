# TaskPilot — 智能任务规划助手

> Agent 做决策，脚本做执行。

TaskPilot 是基于 OpenClaw Agent 的智能任务管理系统，通过 Python 脚本层与滴答清单「Dida365」集成，实现目标拆解、进度跟踪和每日报告。

## 系统架构

```mermaid
graph TB
    subgraph User["用户"]
        U[用户目标/指令]
    end

    subgraph OpenClaw["OpenClaw Agent「Ubuntu」"]
        SKILL[SKILL.md<br/>任务规划智能]
        CRON[Cron Jobs ×3<br/>早/午/晚检查点]
        HB[HEARTBEAT.md<br/>灵活补偿]
        MEM[持久记忆<br/>memory/]
    end

    subgraph TaskPilot["TaskPilot CLI「Python 脚本层」"]
        CLI[cli.py<br/>统一入口]
        TASK[task_ops.py<br/>任务 CRUD]
        PROG[progress.py<br/>进度统计]
        RPT[reporter.py<br/>日报生成]
        CFG[config.py<br/>配置加载]
        BRIDGE[dida_bridge.py<br/>API 桥接 + 重试]
    end

    subgraph Dida["dida365-openapi"]
        CLIENT[Dida365Client<br/>HTTP 客户端]
        AUTH[OAuth2<br/>Token 管理]
    end

    subgraph External["外部服务"]
        API[滴答清单 API<br/>api.dida365.com]
        APP[滴答清单 App<br/>任务存储]
    end

    subgraph Output["输出"]
        MD[Markdown 日报<br/>reports/YYYY-MM-DD.md]
        DIDA_NOTE[滴答清单笔记<br/>Reports 项目]
    end

    U -->|对话| SKILL
    SKILL -->|决策: 拆解任务| CLI
    CRON -->|定时触发| CLI
    HB -->|补偿触发| CLI

    CLI --> TASK
    CLI --> PROG
    CLI --> RPT
    CLI --> CFG

    TASK --> BRIDGE
    PROG --> BRIDGE
    RPT --> BRIDGE
    RPT --> MD
    RPT --> DIDA_NOTE

    BRIDGE --> CLIENT
    CLIENT --> AUTH
    CLIENT -->|HTTPS| API
    API --> APP

    style User fill:#fff3bf,stroke:#f59e0b
    style OpenClaw fill:#dbe4ff,stroke:#3b82f6
    style TaskPilot fill:#e5dbff,stroke:#7c3aed
    style Dida fill:#d3f9d8,stroke:#15803d
    style External fill:#ffc9c9,stroke:#dc2626
    style Output fill:#c3fae8,stroke:#0d9488
```

## 核心数据流

```mermaid
sequenceDiagram
    participant U as 用户
    participant A as OpenClaw Agent
    participant T as TaskPilot CLI
    participant D as dida365-openapi
    participant API as 滴答清单 API

    Note over U,API: 任务规划流程
    U->>A: "帮我规划下周产品发布"
    A->>A: 拆解为 5 个子任务「JSON」
    A->>T: echo '[...]' | taskpilot tasks create
    T->>D: bridge.create_task()
    D->>API: POST /open/v1/task
    API-->>D: {id, title, ...}
    D-->>T: 结构化响应
    T-->>A: {"created": 5, "items": [...]}
    A-->>U: "已创建 5 个子任务"

    Note over U,API: 进度检查流程
    A->>T: taskpilot progress --date today
    T->>D: bridge.filter_tasks() + list_completed_tasks()
    D->>API: POST /open/v1/task/filter
    API-->>D: 任务列表
    D-->>T: 任务数据
    T-->>A: {"total":8, "completed":3, "rate":"37.5", ...}
    A-->>U: "完成率 37.5%，有 1 个逾期任务"
```

## 检查点调度

```mermaid
graph LR
    subgraph Morning["早晨 08:30"]
        M1[查询今日任务] --> M2[计算进度]
        M2 --> M3[建议执行顺序]
    end

    subgraph Afternoon["下午 14:00"]
        A1[检查进度] --> A2[标记阻塞项]
        A2 --> A3[建议调整]
    end

    subgraph Evening["晚间 20:00"]
        E1[生成日报] --> E2[保存 Markdown]
        E2 --> E3[同步滴答清单]
        E3 --> E4[分析 + 明日建议]
    end

    Morning -->|用户执行任务| Afternoon
    Afternoon -->|继续工作| Evening

    style Morning fill:#fff3bf,stroke:#f59e0b
    style Afternoon fill:#a5d8ff,stroke:#3b82f6
    style Evening fill:#d0bfff,stroke:#7c3aed
```

## 模块依赖关系

```mermaid
graph TD
    CLI[cli.py] --> CFG[config.py]
    CLI --> BRIDGE[dida_bridge.py]
    CLI --> TASK[task_ops.py]
    CLI --> PROG[progress.py]
    CLI --> RPT[reporter.py]

    TASK --> BRIDGE
    TASK --> CFG
    PROG --> BRIDGE
    PROG --> CFG
    PROG --> TASK
    RPT --> BRIDGE
    RPT --> CFG
    RPT --> PROG
    RPT --> TASK

    BRIDGE --> VENDOR[dida365_lib<br/>vendor/dida365-openapi]

    style CLI fill:#ffd8a8,stroke:#f59e0b
    style BRIDGE fill:#ffc9c9,stroke:#dc2626
    style VENDOR fill:#d3f9d8,stroke:#15803d
```

## 项目结构

```
TaskPilot/
├── SKILL.md                    # OpenClaw 技能定义
├── README.md                   # 本文件
├── config.yaml                 # 用户配置
├── pyproject.toml              # Python 依赖
├── taskpilot/
│   ├── __init__.py
│   ├── __main__.py             # python -m taskpilot 入口
│   ├── cli.py                  # CLI 统一入口「argparse」
│   ├── config.py               # 配置加载「YAML + 环境变量」
│   ├── dida_bridge.py          # dida365 API 桥接「重试 + 错误处理」
│   ├── task_ops.py             # 任务操作「list/create/complete」
│   ├── progress.py             # 进度统计「完成率/逾期/阻塞」
│   ├── reporter.py             # 日报生成「Markdown + 滴答同步」
│   └── templates/
│       └── report.md           # 日报模板
├── vendor/
│   └── dida365-openapi/        # 滴答清单 API 封装
├── reports/                    # 日报归档
└── docs/
    └── superpowers/specs/      # 设计文档
```

## CLI 命令速查

| 命令 | 用途 | 输出 |
|------|------|------|
| `taskpilot token-check` | 检查 OAuth 连通性 | `{"valid": true}` |
| `taskpilot tasks list --date today` | 查询今日任务 | 任务列表 JSON |
| `echo '[...]' \| taskpilot tasks create` | 批量创建任务 | 创建结果 JSON |
| `taskpilot tasks complete --id X --project-id Y` | 完成任务 | `{"ok": true}` |
| `taskpilot progress --date today` | 进度统计 | 完成率/阻塞 JSON |
| `taskpilot report` | 生成日报 | 报告路径 + 同步状态 |

## 错误处理流程

```mermaid
flowchart TD
    REQ[API 请求] --> CHECK{状态码?}
    CHECK -->|200| OK[返回数据]
    CHECK -->|401| EXPIRED[Token 过期]
    CHECK -->|5xx| RETRY{重试次数 < 2?}
    CHECK -->|其他| ERR[返回错误 JSON]

    RETRY -->|是| WAIT[等待 1-2s] --> REQ
    RETRY -->|否| ERR

    EXPIRED --> HINT[提示重新认证]

    NETWORK[网络错误] --> RETRY

    style OK fill:#b2f2bb,stroke:#15803d
    style ERR fill:#ffc9c9,stroke:#dc2626
    style EXPIRED fill:#ffd8a8,stroke:#f59e0b
```

## 部署「Ubuntu」

```bash
# 1. 克隆项目
git clone <repo> ~/.openclaw/skills/taskpilot
cd ~/.openclaw/skills/taskpilot

# 2. 安装依赖
pip install -e .

# 3. 设置环境变量
export DIDA365_CLIENT_ID="your_client_id"
export DIDA365_CLIENT_SECRET="your_client_secret"
export DIDA365_LIB_PATH="$HOME/.openclaw/skills/dida365-openapi/scripts"

# 4. OAuth 认证
python -m taskpilot token-check

# 5. 验证
echo '[{"title":"测试任务","priority":1}]' | python -m taskpilot tasks create
```
