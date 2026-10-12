# Sprint 1 数据库接口交接

业务使用 `booking/repository.py` 的 `Repository` Protocol 和 `booking/domain.py` 的实体。数据库负责人实现适配器，通过 `REPOSITORY_FACTORY` 接入；附件继续通过 `FILE_STORAGE_FACTORY` 接入私有存储。当前提供内存适配器用于联调，本次未增加 ORM 模型或数据库迁移。

## 客户补充要求对应字段

| 实体 | 字段 | 持久化约定 |
| --- | --- | --- |
| Principal | `university_email: str` | 必填；正式环境由可信 SSO／身份记录提供。与 zID、姓名一起返回用户接口。不要据此推断角色或资格 |
| Resource | `pending_hold_minutes: int` | 必填整数 1–20160；默认 1440（24 小时）。含义是 Admin 审批期限（列名保留不改）。Manager 修改时持久化并记录审计 |
| Resource | `status: str`、`status_reason: str \| None` | `status` 取值 `AVAILABLE`／`MAINTENANCE`／`CLOSED`，默认 `AVAILABLE`；`status_reason` 可空，最长 500 字符。与 `active` 不同：`active=false` 表示资源下架不显示，`status` 是 Manager 随时切换的运营状态 |
| Booking | `hold_until: datetime \| None`、`review_due_at: datetime \| None` | 可空、带时区。进入 `PENDING_APPROVAL` 时两者写同一个值：`min(start, 当时 + pending_hold_minutes)`，不随资源规则变化重算 |
| Booking | `revision: int` | 改期功能新增，默认 1，每次改期加 1 |
| Booking | `status` | 新增 `WAITLISTED`（候补），需要放宽状态字段的取值约束 |
| OutlookSyncRecord | `booking_revision`、`ical_uid`、`last_success_at` | 改期同步新增，均需持久化 |

`hold_active`、`blocks_slot`、`waitlist_position` 是 API 根据状态、提交顺序和服务端时间计算的响应字段，不需要持久化。申请状态取值仍是七种：`WAITING_QUALIFICATION`、`PENDING_APPROVAL`、`WAITLISTED`、`APPROVED`、`REJECTED`、`CANCELLED`、`EXPIRED`。`WAITING_QUALIFICATION` 只为兼容旧数据保留，新流程不再产生（只有 induction 已通过的学生才能提交）。

Manager 可以通过 `POST admin/users/managers/` 新建 Manager 账号（`save_principal`，zID 唯一、小写保存，写 `MANAGER_CREATED` 审计；这是创建 Manager 的唯一方式），通过 `PATCH admin/users/{id}/` 在 Student／Admin 之间调整 `role`（学生升 Admin 前检查每项 induction 的最新提交都已通过且未过期，用到 `list_requirements` 和 `list_submissions`）和修改 `active`，业务层调用 `save_principal` 保存，并在同一事务里写入 `USER_UPDATED` 审计记录；`atomic` 会同时锁住所有 Manager 和被修改的用户，防止并发操作导致系统里没有启用的 Manager。演示用户可以直接写进数据库，`role` 只能是 `STUDENT`／`ADMIN`／`MANAGER`，至少要有一个启用的 Manager。

`Principal` 构造器现在要求邮箱参数；认证适配器和数据库映射必须同步更新。演示注册使用 EmailField 校验格式，尚未验证邮箱所有权或学校域名，不能当作正式认证证明。管理员／Manager 角色只由受信任来源或系统所有者指定，不能从学生注册请求接收。

## 新增仓储查询

```python
def list_blocking_bookings(
    self,
    resource_id: str,
    start: datetime,
    end: datetime,
    at: datetime,
    exclude_id: str | None = None,
) -> list[Booking]: ...
```

返回与 `[start,end)` 重叠且当前阻挡时段的预约。`at` 来自后端时钟，不能由浏览器指定。查询条件示意如下，字段名可按 ORM 模型映射：

```sql
WHERE resource_id = :resource_id
  AND start < :end AND "end" > :start
  AND (:exclude_id IS NULL OR id <> :exclude_id)
  AND (
    status = 'APPROVED'
    OR (
      status IN ('WAITING_QUALIFICATION', 'PENDING_APPROVAL')
      AND hold_until > :server_now
    )
  )
```

审批自己的请求时，仅排除该预约 ID；不能排除该学生的其他预约。相邻区间不冲突，房间和单台设备独立查询。

## 审批流程（客户确认版）

- 只有 induction 已审核通过且在有效期内的学生／Admin 才能提交；否则业务层返回 403 `QUALIFICATION_REQUIRED`，不写任何预约记录。
- 时段空闲的申请一律进入 `PENDING_APPROVAL`（`reason_code=AWAITING_REVIEW`），写入 `hold_until = review_due_at = min(start, 提交时间 + pending_hold_minutes)`，在期限内阻挡重叠时段。有阻挡记录的申请为 `WAITLISTED`，`hold_until=None`，**不阻挡任何时段**。`list_blocking_bookings` 的查询条件不用改。
- Admin／Manager 在期限内批准（`APPROVED`）或拒绝（`REJECTED`）。Admin 不能审批自己的申请。
- 期限到了仍未决：`process_due_requests` 在资源锁内重查规则，仍符合（资格有效、资源可用、无冲突）则 `APPROVED`（`reason_code=AUTO_APPROVED_AFTER_REVIEW_WINDOW`），否则 `REJECTED`（`AUTO_REJECTED_QUALIFICATION`／`AUTO_REJECTED_RESOURCE_UNAVAILABLE`／`AUTO_REJECTED_CONFLICT`）；`reviewed_by='SYSTEM'`，写审计。自动批准同样生成 Outlook 同步待办。
- 预约开始时仍未决的申请（含候补）改为 `EXPIRED`。取消、拒绝、过期立即失去阻挡效力；`hold_until` 保留供追溯。
- 学生的 induction 被拒绝时，其未决申请（`PENDING_APPROVAL`／`WAITLISTED`）一并 `REJECTED`（`QUALIFICATION_REJECTED`）。induction 通过不会自动批准任何预约。
- 已删除：`auto_approve_max_minutes`、120 分钟内自动批准、资料审核中先预约、30 分钟占位、`HOLD_EXPIRED`、未验证学生的未决申请数量限制。

## 等待名单与自动递补

业务层的 `_promote_waitlist(resource_id)` 在**同一事务、持有该资源锁**时运行，处理该资源全部 `WAITLISTED` 预约：

1. 按 `(created_at, id)` 升序遍历。**顺序就是先到先得的依据**，`created_at` 需保存到微秒；如有条件，建议加一个单调递增的序号列作为最终排序依据，避免同一时刻提交时顺序不确定。
2. 已过开始时间的候补改为 `EXPIRED`；仍有阻挡记录的跳过；资源不可用时跳过；否则资格有效的改为 `PENDING_APPROVAL`（`reason_code=PROMOTED_FROM_WAITLIST`，重新计算 `hold_until`／`review_due_at`），资格失效的改为 `REJECTED`（`QUALIFICATION_REQUIRED`）。同时写审计 `BOOKING_PROMOTED`／`BOOKING_REJECTED`（actor 为 `SYSTEM`）。递补不会直接获批，仍要走审批期限。
3. 触发时机：取消、拒绝、过期、改期、自动拒绝，以及资源恢复 `AVAILABLE`。

递补会修改**其他学生**的预约，但只持有资源锁。这是可以的，因为所有会改变同一资源占用情况的写操作（创建、审批、取消、改期、资料审核、时间推进）都会先锁住该资源。数据库适配器必须保证：`atomic` 嵌套调用时复用外层事务（或使用 savepoint），并且不会在已持有资源锁的情况下，再按不同顺序去锁其他资源。

建议索引：`(resource_id, status, created_at)` 用于读取候补队列，`(status, review_due_at)` 用于找出审批期限已到的申请，`(student_id, status)` 用于重复预约检查和资料被拒时的级联拒绝。

## 事务和并发要求

`atomic(resource_ids, student_ids)` 必须实现真实数据库事务和一致顺序的资源／学生锁。创建申请、人工批准、期限到期后的自动决定、资料被拒时的级联拒绝以及规则修改必须遵循业务服务传入的锁约定。在同一事务内重读资源规则、资格及阻挡预约，然后保存预约和审计；失败完整回滚。

数据库索引可覆盖资源、时间区间、状态和占位截止时间。仅对 APPROVED 建区间排斥约束无法防止跨状态的占位冲突，仍需资源锁和事务内重查。可用性接口只提供快照，不能代替写入事务中的校验。实际适配器需验证两个并发请求只会产生一个占位／获批预约，且错误能回滚全部关联写入。

同一资源／学生锁内还必须检查该学生是否已经有与新时段重叠的有效申请（状态为 `PENDING_APPROVAL`、`WAITLISTED` 或 `APPROVED`；旧数据中的 `WAITING_QUALIFICATION` 也算）。存在时业务层返回 `DUPLICATE_BOOKING`，不能再创建一条候补记录。终态记录不阻止重新申请；不同资源同一时间不属于重复预约。

规则更新写入 `RESOURCE_BOOKING_POLICY_UPDATED` 审计，保存前后分钟数。身份、资料、资格有效期、审批与取消的现有字段及审计继续持久化。`QualificationSubmission.valid_until` 在 VERIFIED 时由业务服务设定（审核时间加 `QUALIFICATION_VALIDITY_DAYS`），PENDING／REJECTED 为空；`QUALIFICATION_VERIFIED` 审计的 details 带 `valid_until`。审计查询接口 `GET admin/audit/` 目前在业务层对 `list_audit()` 的结果做筛选和分页；数据量变大后，数据库适配器应为审计表的 `at`、`entity_type`＋`entity_id`、`actor_id`、`action` 建索引，必要时再把筛选下推到查询中（结果需与现有测试一致）。审计记录只追加，不修改、不删除。每个资源目前关联一项 `required_qualification_id`，不同资源可以不同；不要改成用户全局 inducted 布尔值。未来多项前置资格需单独扩展关系和接口。

## 接入／迁移建议

- 既有用户邮箱应从可信身份数据补齐；不要编造正式用户邮箱。
- 既有资源设置 `pending_hold_minutes=1440`（默认 24 小时），或使用客户确认的初始值。删除 `auto_approve_max_minutes` 列（如已建）。环境变量 `DEFAULT_PENDING_HOLD_MINUTES` 仅用于创建演示种子数据，不能覆盖数据库中的 Manager 配置。
- 既有 Pending 预约若 `review_due_at` 为空，可按迁移时间 + `pending_hold_minutes` 补齐（不晚于开始时间）；既有 `WAITING_QUALIFICATION` 记录可人工处理或改为 `REJECTED`。既有 APPROVED 继续占用，终态继续释放。
- 时间字段使用带时区存储；API 输出 UTC，开放时间规则使用资源时区。
- `save_booking`、`save_resource`、`save_principal` 必须读写上述新增字段；替换适配器后保留原 API 结构。

Outlook 继续使用 `OutlookSyncRecord` 和 `get_outlook_sync`／`list_outlook_sync`／`save_outlook_sync`。预约、审计和同步待办同事务提交；网络调用在事务外。Pending 申请不创建 Outlook 事件；人工或自动批准后才同步。适配器完成后才能使用多进程后端及独立后台处理命令；内存演示不共享或持久化数据。
