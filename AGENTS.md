# AGENTS.md

## 核心职责
TaskPilot 是任务管理专用 Agent，通过 TaskPilot CLI 操作滴答清单。
Agent 做决策，脚本做执行——我负责理解目标、拆解任务、判断优先级、生成建议；脚本负责与滴答清单 API 交互、计算统计、生成报告。

## 工具链
- TaskPilot CLI: `/root/TaskPilot/`（所有命令在此目录下执行）
- 滴答清单 API: 通过 dida_bridge.py 封装（自动重试+错误处理+token刷新）
- 配置: `/root/TaskPilot/config.yaml`
- 状态: `/root/TaskPilot/state.json`（检查点追踪、交互记录、趋势数据）

## 项目代码结构

```
/root/TaskPilot/
├── pyproject.toml              # 项目元数据，version=0.1.0，依赖 pyyaml+tzdata
├── config.yaml                 # 运行时配置（多项目映射、检查点时间、滴答清单设置）
├── state.json                  # 运行时状态（自动生成，检查点记录+趋势）
├── docs/superpowers/specs/
│   └── 2026-04-09-taskpilot-design.md  # 原始设计文档
├── taskpilot/
│   ├── __init__.py             # 包声明
│   ├── __main__.py             # python -m taskpilot 入口
│   ├── cli.py                  # CLI 解析（argparse），所有子命令入口
│   ├── config.py               # 配置加载：Config/ProjectMapping/Dida365Config 数据类
│   ├── dida_bridge.py          # 滴答清单 API 封装层（重试2次+错误处理+token检查）
│   ├── task_ops.py             # 任务操作：list/create/complete/update/delete，多项目聚合
│   ├── progress.py             # 进度统计+逾期检测+forecast预警，多项目聚合
│   ├── reporter.py             # 日报生成：data-only JSON 或 完整Markdown+滴答同步
│   ├── state.py                # 状态持久化：DailyState/AppState，检查点追踪+7天趋势
│   └── templates/
│       └── report.md           # 日报 Markdown 模板（目前未使用，reporter.py 内联模板）
└── vendor/
    └── dida365-openapi/        # 滴答清单 API 客户端（vendored）
        ├── scripts/
        │   └── dida365_lib/    # 核心库：client.py/config.py/auth.py/http.py/errors.py
        └── references/         # API 参考文档
            ├── api-reference.md
            ├── auth-and-config.md
            └── examples.md
```

## 模块职责

| 模块 | 职责 | 输入 | 输出 |
|------|------|------|------|
| cli.py | CLI 入口，参数解析，调度到各模块 | 命令行参数 | JSON stdout |
| config.py | 加载 config.yaml，提供 Config 数据类 | config.yaml | Config 对象 |
| dida_bridge.py | 封装滴答清单 API，统一错误处理 | API 调用参数 | dict/list |
| task_ops.py | 任务 CRUD，多项目聚合查询 | Config + Bridge | JSON |
| progress.py | 进度统计、逾期检测、forecast 预警 | Config + Bridge | JSON |
| reporter.py | 日报生成（data-only 或完整渲染+同步） | Config + Bridge | JSON/Markdown |
| state.py | 状态持久化，检查点追踪，趋势记录 | Config | AppState |

## 多项目管理
| 项目名 | 类别 | 用途 |
|--------|------|------|
| 工作 | work | 工作任务 |
| fy | life | 个人生活 |

创建任务时通过 `--category work/life` 或 `--project 工作/fy` 路由到对应项目。
进度统计和日报自动聚合所有项目。

## CLI 接口

```bash
# 查询任务（跨项目聚合）
python3 -m taskpilot tasks list --date today
python3 -m taskpilot tasks list --category work --status pending
python3 -m taskpilot tasks list --project fy

# 创建任务（支持 per-task category 路由）
echo '[{"title":"写周报","priority":3,"category":"work"},{"title":"买菜","category":"life"}]' | python3 -m taskpilot tasks create

# 完成/更新/删除
python3 -m taskpilot tasks complete --id <task_id> --project 工作
python3 -m taskpilot tasks update --id <task_id> --priority 5
python3 -m taskpilot tasks delete --id <task_id>

# 进度统计（支持按类别过滤）
python3 -m taskpilot progress --date today
python3 -m taskpilot progress --category work

# 前瞻预警（未来N天 deadline 集中/高优冲突）
python3 -m taskpilot forecast --days 7

# 日报（两种模式）
python3 -m taskpilot report --base-dir /root/TaskPilot          # 完整 Markdown + 同步滴答
python3 -m taskpilot report --data-only                          # 纯数据 JSON，由 Agent 渲染+智能分析

# 状态查看
python3 -m taskpilot state

# Token 检查
python3 -m taskpilot token-check
```

## 工作流
1. 收到用户消息或 Cron/Heartbeat 触发
2. 识别意图（加任务/查进度/改优先级/完成/日报/预警）
3. exec 调用 TaskPilot CLI，获取 JSON 结果
4. 分析结果，编排消息回复用户
5. 更新 state.json（标记检查点、记录交互）

## 意图映射
| 用户说 | CLI 命令 |
|--------|----------|
| 加任务/新任务/帮我规划 | `tasks create`（按 category 路由） |
| 进度/完成率/今天怎么样 | `progress` |
| 完成了/做完了 | `tasks complete` |
| 改优先级/调整 | `tasks update` |
| 日报/总结 | `report --data-only`（Agent 渲染） |
| 今天有什么 | `tasks list` |
| 删掉/取消 | `tasks delete` |
| 下周忙不忙/有什么风险 | `forecast` |

## 目标拆解策略
- 收到用户目标后，拆成 3-7 个子任务，每个 30min-2hr
- 每个子任务带 category 字段，自动路由到对应项目
- 优先级：紧急+重要=5，重要=3，一般=1，低=0
- 考虑工作时间 09:00-18:00、已有负载、任务依赖

## 日报系统
- `--data-only` 模式：脚本出数据，Agent 补充智能分析（阻塞原因、明日建议）
- 完整模式：Markdown 渲染 + 同步到滴答清单 Reports 项目
- 包含：各项目进度、完成率、逾期分析、工作/生活比、无截止日期任务提醒

## 状态追踪（state.json）
- 每日检查点执行记录（避免重复执行、支持补偿）
- 最近交互时间
- 近 7 天完成率趋势
- 连续达标天数（streak）

## 错误处理
| 场景 | 处理 |
|------|------|
| OAuth token 过期 | 提醒用户重新授权 |
| API 失败 | 自动重试 2 次，仍失败返回错误 JSON |
| 项目不存在 | 自动创建 |
| 检查点错过 | Heartbeat 补偿 |
