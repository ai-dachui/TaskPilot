# TaskPilot 设计文档

## 概述

TaskPilot 是一个基于 OpenClaw Agent 的智能任务管理助手。它通过 Python 脚本层处理确定性操作（任务增删改查、报告生成、进度统计），Agent 只负责高层决策（目标拆解、优先级判断、建议生成），从而在可靠性和智能性之间取得平衡。

**核心原则：Agent 做决策，脚本做执行。**

## 系统架构

```
用户 ←→ OpenClaw Agent (CLI 对话)
              │
              ├── SKILL.md          ← 教 Agent 如何做任务规划决策
              ├── config.yaml       ← 用户偏好（时区、工作时间、检查点）
              ├── cron jobs ×3      ← 早/午/晚 定时触发
              ├── HEARTBEAT.md      ← 补偿错过的检查点
              │
              └── Python 脚本层 (taskpilot CLI)
                    │
                    ├── taskpilot tasks list     ← 查询今日任务
                    ├── taskpilot tasks create   ← 批量创建子任务
                    ├── taskpilot progress       ← 计算完成率/阻塞项
                    ├── taskpilot report         ← 生成日报 + 同步滴答
                    └── taskpilot token-check    ← 检查 OAuth 状态
                          │
                          └── dida365-openapi (底层 API 调用)
                                │
                                └── 滴答清单 (数据存储)
```

## 核心模块

### 1. Python 脚本层 (`taskpilot/`)

脚本层是系统的执行引擎，封装所有与 dida365 的交互，提供确定性的 CLI 接口。

```
taskpilot/
  __init__.py
  cli.py                  # CLI 入口 (argparse)
  dida_bridge.py          # 封装 dida365-openapi，统一错误处理和 token 刷新
  task_ops.py             # 任务操作：list/create/update/complete/query
  progress.py             # 进度统计：完成率、逾期项、阻塞分析
  reporter.py             # 日报生成：查询数据 → Markdown → 同步滴答
  config.py               # 读取 config.yaml，提供默认值
  templates/
    report.md             # 日报 Markdown 模板
```

#### CLI 接口设计

```bash
# 查询任务
taskpilot tasks list --date today --status pending
taskpilot tasks list --date 2026-04-09 --tag work

# 批量创建子任务（接受 JSON stdin）
echo '[{"title":"写大纲","due":"2026-04-10","priority":3,"tag":"work"}]' | taskpilot tasks create --project TaskPilot

# 完成任务
taskpilot tasks complete --id <task_id>

# 进度统计
taskpilot progress --date today
# 输出: {"total":8,"completed":3,"pending":4,"overdue":1,"rate":"37.5%","blockers":["任务X已逾期2天"]}

# 生成日报
taskpilot report --date today
# 输出: 生成 reports/2026-04-09.md + 同步到滴答清单 Reports 项目

# 检查 OAuth 状态
taskpilot token-check
# 输出: {"valid":true,"expires_in":3600} 或 {"valid":false,"error":"token expired"}
```

所有命令输出结构化 JSON 到 stdout，错误输出到 stderr。Agent 解析 JSON 做决策，不需要理解 API 细节。

#### dida_bridge.py 关键职责

- 封装 dida365-openapi 的 Python 模块（直接 import，不走 subprocess）
- OAuth token 自动刷新：调用前检查 token 有效性，过期自动刷新
- 统一错误处理：API 失败时返回结构化错误 JSON，不抛异常
- 请求重试：网络错误自动重试 2 次

### 2. OpenClaw 技能配置

#### SKILL.md — 任务规划智能

教 Agent 如何做决策，不涉及具体 API 调用：

- **目标拆解策略**：收到用户目标后，拆成 3-7 个子任务，每个 30min-2hr
- **优先级判断**：紧急+重要=5，重要=3，一般=1，低=0
- **时间安排**：考虑用户工作时间、已有任务负载、任务间依赖
- **检查点行为**：
  - 早晨：调用 `taskpilot tasks list` + `taskpilot progress`，建议今日执行顺序
  - 下午：调用 `taskpilot progress`，标记阻塞项，建议调整
  - 晚上：调用 `taskpilot report`，分析问题，给出明日建议
- **Token 预算**：检查点使用精简 prompt，避免重复加载完整上下文

#### config.yaml — 用户配置

```yaml
timezone: "Asia/Shanghai"
work_hours:
  start: "09:00"
  end: "18:00"
checkpoints:
  morning: "08:30"
  afternoon: "14:00"
  evening: "20:00"
dida365:
  project_name: "TaskPilot"
  report_project: "Reports"
  tags:
    work: "work"
    life: "life"
reports_dir: "reports"
token_budget:
  checkpoint_max_tokens: 2000    # 每个检查点的 prompt token 上限
```

### 3. 调度系统

#### Cron Jobs（定时触发）

三个 cron job 写入 `~/.openclaw/cron/jobs.json`：

| 检查点 | 时间  | 触发 prompt                                                    |
| ------ | ----- | -------------------------------------------------------------- |
| 早晨   | 08:30 | 运行 `taskpilot tasks list` 和 `taskpilot progress`，规划今日  |
| 下午   | 14:00 | 运行 `taskpilot progress`，检查阻塞项                          |
| 晚上   | 20:00 | 运行 `taskpilot report`，生成日报并分析                        |

#### HEARTBEAT.md（灵活补偿）

- 如果某个检查点因用户离线而错过，下次心跳时补上
- 如果用户在对话中提到新目标，主动提议规划
- 检查是否有逾期任务需要提醒

### 4. 日报系统

#### 报告模板 (`templates/report.md`)

```markdown
# 日报: {date} ({weekday})

## 完成 ({completed_count}/{total_count})
{completed_tasks}

## 进行中
{in_progress_tasks}

## 未开始/逾期
{pending_tasks}

## 数据分析
- 完成率: {completion_rate}%
- 逾期任务: {overdue_count} 个
- 工作/生活比: {work_ratio}:{life_ratio}

## 问题与阻塞
{blockers_analysis}

## 明日建议
{tomorrow_suggestions}
```

#### 报告生成流程

1. `reporter.py` 调用 `dida_bridge` 查询当日所有任务（完成+未完成）
2. 按模板填充数据，计算统计指标
3. 写入 `reports/YYYY-MM-DD.md`
4. 调用 `dida_bridge` 在 Reports 项目创建笔记任务，内容为报告摘要
5. 输出报告路径和同步状态的 JSON

### 5. 错误处理策略

| 场景               | 处理方式                                          |
| ------------------ | ------------------------------------------------- |
| OAuth token 过期   | `dida_bridge` 自动刷新，刷新失败时提示用户重新授权 |
| API 调用失败       | 重试 2 次，仍失败则写本地日志 + 返回错误 JSON      |
| 检查点错过         | HEARTBEAT 补偿，下次心跳执行                       |
| 滴答清单项目不存在 | 首次运行时自动创建 TaskPilot 和 Reports 项目       |

## 数据流

```
用户: "帮我规划下周的产品发布"
  │
  ▼
Agent 决策: 拆解为 5 个子任务 (JSON)
  │
  ▼
echo '[...]' | taskpilot tasks create --project TaskPilot
  │
  ▼
dida_bridge → dida365 API → 滴答清单
  │
  ▼
返回: {"created": 5, "ids": [...]}
  │
  ▼
Agent: "已创建 5 个子任务，最早的截止明天..."
```

## 渐进式启用计划

1. **Phase 1**: 实现脚本层 + 晚间报告（验证 dida365 集成可靠性）
2. **Phase 2**: 加入早晨规划检查点
3. **Phase 3**: 加入下午进度检查 + HEARTBEAT 补偿
4. **Phase 4**: 优化 token 消耗，调整 prompt 精简度

## 验证方式

1. 手动运行 `taskpilot token-check` 确认 OAuth 连通
2. 手动运行 `taskpilot tasks create` 创建测试任务，在滴答清单中验证
3. 手动运行 `taskpilot report --date today` 生成报告，检查 Markdown 和滴答同步
4. 配置一个晚间 cron job，观察 Agent 是否正确触发并生成报告
5. 逐步启用其他检查点，观察 token 消耗是否在预算内
