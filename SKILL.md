---
name: taskpilot
description: 智能任务规划与管理助手。将用户目标拆解为可执行的子任务，写入滴答清单（Dida365），定时检查进度，生成每日报告。依赖 dida365-openapi skill 进行 API 调用。Use when the agent needs to plan tasks, track progress, or generate daily reports through Dida365.
metadata:
  openclaw:
    requires:
      bins:
        - python
      env:
        - DIDA365_CLIENT_ID
        - DIDA365_CLIENT_SECRET
      skills:
        - dida365-openapi
---

# TaskPilot — 智能任务规划助手

## Overview

TaskPilot 是一个任务规划和管理层，运行在 dida365-openapi 之上。它提供：

1. **任务规划** — 将用户目标拆解为 3-7 个可执行子任务，写入滴答清单
2. **进度跟踪** — 查询任务完成率、逾期项、阻塞分析
3. **每日报告** — 生成 Markdown 日报 + 同步到滴答清单

核心原则：**你（Agent）做决策，脚本做执行。**

你负责理解用户目标、拆解任务、判断优先级、生成建议。
脚本负责与滴答清单 API 交互、计算统计、生成报告。

## 安装

TaskPilot 运行在 Ubuntu (Linux) 环境。确保 dida365-openapi 已安装并完成 OAuth 认证。

```bash
# 安装依赖
cd /path/to/taskpilot
pip install -e .

# 设置 dida365-openapi 库路径（如果不在 vendor/ 下）
export DIDA365_LIB_PATH=/path/to/dida365-openapi/scripts

# 验证 dida365 连通性
python -m taskpilot token-check

# 如果 token 无效，先通过 dida365-openapi 重新认证
python scripts/dida365.py auth login-local
```

dida365-openapi 的配置文件位于 `~/.config/dida365-openapi/`（config.json + token.json）。

## CLI 命令

所有命令输出结构化 JSON 到 stdout，错误输出到 stderr。

### 检查连通性

```bash
python -m taskpilot token-check
# 输出: {"valid": true} 或 {"valid": false, "error": "..."}
```

### 查询任务

```bash
# 今日所有任务
python -m taskpilot tasks list --date today

# 今日待办
python -m taskpilot tasks list --date today --status pending

# 按标签筛选
python -m taskpilot tasks list --tag work
```

输出格式：
```json
{
  "count": 5,
  "tasks": [
    {"id": "...", "title": "...", "status": "pending", "priority": 3, "due_date": "...", "tags": ["work"], "project_id": "..."}
  ]
}
```

### 批量创建任务

通过 stdin 传入 JSON 数组：

```bash
echo '[
  {"title": "写产品需求文档", "due": "2026-04-10T18:00:00+0800", "priority": 5, "tags": ["work"]},
  {"title": "预约牙医", "due": "2026-04-11T10:00:00+0800", "priority": 1, "tags": ["life"]}
]' | python -m taskpilot tasks create
```

任务字段：
- `title` (必填): 任务标题
- `due`: 截止时间，格式 `yyyy-MM-ddTHH:mm:ss+zzzz`
- `start`: 开始时间，同上格式
- `priority`: 0=无, 1=低, 3=中, 5=高
- `tags`: 标签数组，如 `["work"]` 或 `["life"]`
- `content`: 任务描述/备注
- `is_all_day`: 是否全天任务

输出格式：
```json
{"created": 2, "items": [{"id": "...", "title": "..."}], "errors": []}
```

### 完成任务

```bash
python -m taskpilot tasks complete --id <task_id> --project-id <project_id>
```

### 查看进度

```bash
python -m taskpilot progress --date today
```

输出格式：
```json
{
  "total": 8,
  "completed": 3,
  "pending": 5,
  "overdue": 1,
  "rate": "37.5",
  "blockers": ["逾期: 写文档 (超期 4.2h)", "高优先级未完成: 代码审查"],
  "work_count": 5,
  "life_count": 3,
  "overdue_tasks": [{"id": "...", "title": "...", "overdue_hours": 4.2}]
}
```

### 生成日报

```bash
python -m taskpilot report --date 2026-04-09 --base-dir /path/to/workspace
```

输出格式：
```json
{
  "report_path": "reports/2026-04-09.md",
  "date": "2026-04-09",
  "synced": true,
  "progress": { ... }
}
```

日报会：
1. 保存 Markdown 文件到 `reports/YYYY-MM-DD.md`
2. 在滴答清单 "Reports" 项目中创建一条笔记任务

## 任务规划指南

当用户给你一个目标时，按以下策略拆解：

### 拆解规则

1. 每个目标拆成 **3-7 个子任务**
2. 每个子任务应在 **30分钟 - 2小时** 内可完成
3. 子任务之间有清晰的先后顺序
4. 标题用动词开头，明确可执行（"写...", "调研...", "测试..."）

### 优先级映射

| 场景 | priority 值 | 含义 |
|------|------------|------|
| 紧急且重要 | 5 | 今天必须完成 |
| 重要不紧急 | 3 | 本周内完成 |
| 一般任务 | 1 | 有空再做 |
| 低优先级 | 0 | 可选/备忘 |

### 时间安排

- 预留 20% 缓冲时间
- 考虑上下文切换成本（连续的同类任务放一起）
- 高优先级任务安排在上午（精力充沛时段）
- 工作任务在工作时间内，生活任务在工作时间外
- 用 `#work` 和 `#life` 标签区分

### 示例

用户说："帮我规划下周的产品发布"

你应该：
1. 询问关键细节（发布什么？截止日期？有哪些依赖？）
2. 拆解为子任务
3. 调用 `taskpilot tasks create` 写入滴答清单

```bash
echo '[
  {"title": "整理发布 checklist", "due": "2026-04-13T10:00:00+0800", "priority": 5, "tags": ["work"]},
  {"title": "完成最终代码审查", "due": "2026-04-13T14:00:00+0800", "priority": 5, "tags": ["work"]},
  {"title": "更新用户文档", "due": "2026-04-14T12:00:00+0800", "priority": 3, "tags": ["work"]},
  {"title": "准备发布公告", "due": "2026-04-14T16:00:00+0800", "priority": 3, "tags": ["work"]},
  {"title": "执行发布流程", "due": "2026-04-15T10:00:00+0800", "priority": 5, "tags": ["work"]},
  {"title": "发布后监控和验证", "due": "2026-04-15T14:00:00+0800", "priority": 5, "tags": ["work"]}
]' | python -m taskpilot tasks create
```

## 检查点行为

### 早晨检查点（默认 08:30）

1. 运行 `python -m taskpilot tasks list --date today`
2. 运行 `python -m taskpilot progress --date today`
3. 根据结果向用户建议今日执行顺序
4. 高优先级任务排前面，考虑截止时间紧迫度

### 下午检查点（默认 14:00）

1. 运行 `python -m taskpilot progress --date today`
2. 检查 blockers 列表
3. 如果有逾期任务，提醒用户并建议调整
4. 如果完成率低于 30%，建议重新排优先级

### 晚间检查点（默认 20:00）

1. 运行 `python -m taskpilot report --base-dir <workspace_path>`
2. 读取生成的报告内容
3. 基于报告数据，生成明日建议：
   - 今天未完成的高优先级任务 → 明天优先处理
   - 分析完成率趋势
   - 如果工作/生活比失衡，建议调整

## 配置

配置文件 `config.yaml`：

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
```

可通过 `--config /path/to/config.yaml` 指定配置文件路径，或设置 `TASKPILOT_CONFIG` 环境变量。

## 错误处理

- 如果 `token-check` 返回 `{"valid": false}`，先运行 `python scripts/dida365.py auth login-local` 重新认证
- 如果创建任务失败，检查 `errors` 数组中的具体错误信息
- API 调用自动重试 2 次（仅限 5xx 错误和网络错误）
- 所有错误都是结构化 JSON，不会静默失败

## 环境变量

| 变量 | 用途 | 示例 |
|------|------|------|
| `TASKPILOT_CONFIG` | config.yaml 路径 | `/home/user/taskpilot/config.yaml` |
| `DIDA365_LIB_PATH` | dida365-openapi 的 scripts 目录路径 | `/home/user/.openclaw/skills/dida365-openapi/scripts` |
| `DIDA365_CLIENT_ID` | OAuth client_id | (从滴答清单开发者平台获取) |
| `DIDA365_CLIENT_SECRET` | OAuth client_secret | (从滴答清单开发者平台获取) |

## 部署说明 (Ubuntu)

```bash
# 典型目录结构
~/.openclaw/skills/taskpilot/          # 本技能
~/.openclaw/skills/dida365-openapi/    # 依赖技能
~/.config/dida365-openapi/             # OAuth 配置和 token（自动创建）
~/taskpilot-workspace/
  config.yaml                          # TaskPilot 配置
  reports/                             # 日报归档
```
