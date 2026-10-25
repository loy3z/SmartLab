# Sprint 2：可演示的 MVP

> deepseek修改（Loy已审核），2026-10-25。
> 定位：Sprint 2 是下一次交付，目标是把已经实现的预约系统收拾到「能完整演示、能本地部署、能交付」，不再新增业务功能。
> 现状：1.10–1.17.1 的功能已经实现（代码里标 `Sprint 3`，那是团队内部命名）。Sprint 2 的重点是收口、文档和演示。

## 目标

一个人在本地 10 分钟内跑起来，5 分钟演示完主流程，不卡壳、不空白、不报错。

## 范围

| 编号 | 项 | 现状 | 要做到 | 验收 | 状态 |
| --- | --- | --- | --- | --- | --- |
| S2-1 | 演示主流程 | 功能齐 | 写一份 5 分钟演示脚本：学生登录 → 找资源 → 预约 → 审批 → 签到 → 日历订阅 → 冻结/解冻 | 按脚本走一遍不卡 | ○ |
| S2-2 | 模拟 SSO | 已有 `MockSsoPage`、`mock-sso.css`、`staff-sign-in` | 补说明文档，写明「这是模拟，不是学校真实 SSO」；覆盖学生、员工、Admin、Manager 四个入口 | 四个角色都能从登录页进入 | ◐ |
| S2-3 | 模拟 Outlook 日历 | `.ics` 订阅已有；主账号 Graph 单向已有 | 演示统一用 `.ics`（零授权、零合规风险）；页面说清「复制链接到 Outlook → 从 Internet 订阅」 | 学生在 Outlook 里订阅后能看到自己的预约 | ◐ |
| S2-4 | 流程收口 | 有已知缺陷 | 修：SlotPicker 换日期空白、17 处按钮忙碌跳版、5 处死代码（铃铛摆动、页面淡入两份、dialog 双层进场、reduced-motion 两条规则、未引用的 `App.css`） | 换日期有 `Loading times…` 提示；按钮忙碌时宽度不变；铃铛行为明确（要么摇，要么删干净） | ○ |
| S2-5 | 去 AI 味剩余 | 第一批（文案、字号、字体、命名）已完成 | 装饰换信息、演示数据换成像真的、按任务验收 | 对照 `claude/reports/2026-10-25-ai-flavor-sources.md` 第 4 节逐条核对 | ◐ |
| S2-6 | 本地部署 | `start-backend.ps1`（迁移 + 启动）、内存/PostgreSQL 双模式、前端 `npm run dev` | 补「零基础启动」文档：装什么、跑什么、种子数据、演示账号、常见错误 | 新机器照文档能跑起来并登录 | ◐ |
| S2-7 | 稳定 | 未知 | 跑一次全套 `claude-tools/check-local.sh`，修失败项 | env、backend、pg、openapi、unit、lint、build、e2e 全部 PASS 或写明 SKIP 原因 | ○ |

## 不在 Sprint 2 范围（明确不做）

- 真实 SSO、真实 Outlook OAuth：等客户确认账号类型和权限（见 `claude/reports/2026-10-25-outlook-personal-calendar.md`）。
- 云部署、压力测试：放进 Sprint 3。
- 图表类可视化（Usage statistics 加图、Today 图形、Room Management 时间轴、My Bookings 进度条）：放进 Sprint 3。

## 与代码的对应

| 项 | 代码位置 |
| --- | --- |
| 模拟 SSO | `frontend/src/features/auth/MockSsoPage.tsx`、`auth/mock-sso.css`；后端 `auth/staff-sign-in/`、`auth/demo-login/` |
| 日历订阅 | `backend/booking/ics.py`、`features/booking/CalendarSubscribe.tsx` |
| 主账号 Outlook | `backend/booking/outlook.py`、`calendar_sync.py`、`OUTLOOK_INVITE_MODE` |
| 本地启动 | `backend/start-backend.ps1`（本机文件，不进 git）、`frontend` 的 `npm run dev` |
| 测试 | `claude-tools/check-local.sh` |

## 验收

1. 按 S2-1 的脚本完整演示一遍，全程无报错、无空白页。
2. S2-7 的全套测试结果贴进本轮交付。
3. S2-2、S2-3 的说明文档写清「模拟」两个字，避免演示时被理解成真实接入。
