# 数据库接口说明

业务使用 `booking/repository.py` 的 `Repository` Protocol 和 `booking/domain.py` 的实体。数据库适配器通过 `REPOSITORY_FACTORY` 接入；附件通过 `FILE_STORAGE_FACTORY` 接入私有存储。现有两种适配器：内存适配器（默认，用于演示和单元测试）和 PostgreSQL 适配器（`booking/postgres.py`，建表脚本和本地搭建步骤见 `database/README.md`，集成测试见 `booking/tests/test_postgres.py`）。项目不使用 Django ORM 模型或 Django 迁移；表结构改动要同时更新 `database/schema.sql`，并在 `database/migrations/` 里加一个可重复执行的升级脚本。

## 实体字段约定

下表列出需要特别注意的字段，完整字段以 `booking/domain.py` 为准。

| 实体 | 字段 | 持久化约定 |
| --- | --- | --- |
| Principal | `university_email: str` | 必填；正式环境由可信 SSO／身份记录提供。与 zID、姓名一起返回用户接口。不要据此推断角色或资格 |
| Resource | `pending_hold_minutes: int` | 必填整数 1–20160；默认 1440（24 小时）。含义是 Admin 审批期限（列名沿用）。Manager 修改时持久化并记录审计 |
| Resource | `status: str`、`status_reason: str \| None` | `status` 取值 `AVAILABLE`／`MAINTENANCE`／`CLOSED`，默认 `AVAILABLE`；`status_reason` 可空，最长 500 字符。与 `active` 不同：`active=false` 表示资源下架不显示，`status` 是 Manager 随时切换的运营状态 |
| Resource | `room_id: str \| None` | 设备所在房间（外键指向房间资源）；房间本身为空（检查约束 `room_id IS NULL OR kind='EQUIPMENT'`）。仅用于显示和分组，房间状态不影响设备 |
| Resource | `category: str \| None` | 设备类别，供预约页筛选；房间为空；1–60 个字符 |
| QualificationRequirement | `prerequisite_ids: tuple[str, ...]` | 列 `prerequisite_ids uuid[] NOT NULL DEFAULT '{}'`，不能包含自己；循环由业务层检查。演示数据：Advanced 的前置是 General |
| Booking | `student_id`、`created_by: str \| None` | `student_id` 是预约属于谁（检查他的 induction，锁和重复检查都按它）；`created_by` 是谁创建的，员工代别人预约时与 `student_id` 不同 |
| Booking | `urgent: bool`、`urgent_reason: str \| None` | 紧急申请标记和原因（≤500 字） |
| Booking | `hold_until`、`review_due_at: datetime \| None` | 可空、带时区。普通申请进入 `PENDING_APPROVAL` 时两者写同一个值：`min(start, 当时 + pending_hold_minutes)`，不随资源规则变化重算。紧急申请 `review_due_at` 为空、`hold_until=start` |
| Booking | `revision: int` | 默认 1，每次改期加 1 |
| Booking | `status` | 七种：`WAITING_QUALIFICATION`、`PENDING_APPROVAL`、`WAITLISTED`、`APPROVED`、`REJECTED`、`CANCELLED`、`EXPIRED`。`WAITING_QUALIFICATION` 只出现在早期数据中，现在的流程不会产生 |
| OutlookSyncRecord | `booking_revision`、`ical_uid`、`last_success_at` 等 | 事件对应关系、版本、重试和租约，均需持久化 |
| StaffCredential | `principal_id`、`password_hash`、`invite_code`、`updated_at` | 表 `staff_credential`（主键 `principal_id`，外键指向 `app_users`）。只有 Admin／Manager 有；`password_hash` 是 Django 密码哈希，激活前为空；`invite_code` 激活后为空。仓储方法 `get_credential(principal_id)`、`save_credential(credential)`。单独成表，避免密码哈希跟着用户对象被返回 |

`hold_active`、`blocks_slot`、`waitlist_position` 是 API 根据状态、提交顺序和服务端时间计算的响应字段，不需要持久化。

Student、Admin、Manager 是三种分开的账号，角色在创建时确定，之后不能互转；三种角色都可以预约，规则相同。Manager 通过 `POST admin/users/staff/` 新建 Admin 或 Manager 账号（`save_principal`，zID 唯一、小写保存，写 `ADMIN_CREATED`／`MANAGER_CREATED` 审计），通过 `PATCH admin/users/{id}/` 修改 `active`，业务层在同一事务里写 `USER_UPDATED` 审计。停用学生时，同时把该学生的未决申请改为 `REJECTED`（`ACCOUNT_DEACTIVATED`）并递补；`atomic` 会同时锁住所有 Manager 和被修改的用户，防止并发操作导致系统里没有启用的 Manager。演示用户可以直接写进数据库，`role` 只能是 `STUDENT`／`ADMIN`／`MANAGER`，至少要有一个启用的 Manager。

`Principal` 必须带邮箱；认证适配器和数据库映射都要提供。演示注册用 EmailField 校验格式，不验证邮箱所有权或学校域名，不能当作正式认证证明。Admin／Manager 角色只由受信任来源或系统所有者指定，不能从学生注册请求接收。

## 阻挡查询

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

返回与 `[start,end)` 重叠且当前阻挡时段的预约。`at` 来自后端时钟，不能由浏览器指定。查询条件示意如下，字段名可按实际表结构映射：

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

审批某个请求时，仅排除该预约 ID；不能排除该学生的其他预约。相邻区间不冲突，房间和单台设备独立查询。

## 审批流程

- 只有 induction（及其前置）已审核通过且在有效期内的人才能提交；否则业务层返回 403 `QUALIFICATION_REQUIRED`，不写任何预约记录。
- 创建、人工批准、自动处理、递补、改期都调用 `BookingService.rule_violation`（`booking/services/checks.py`），按顺序检查：账号启用 → 资源可用 → 时间合法 → 预约窗口（仅创建和改期）→ 资格及前置资格。数据库适配器只需保证在锁内能读到最新的用户、资源、资格记录。
- 时段空闲的申请一律进入 `PENDING_APPROVAL`（`reason_code=AWAITING_REVIEW`），写入 `hold_until = review_due_at = min(start, 提交时间 + pending_hold_minutes)`，在期限内阻挡重叠时段。有阻挡记录的申请为 `WAITLISTED`，`hold_until=None`，**不阻挡任何时段**。
- 紧急申请（`urgent=true`）时段必须空闲，不进候补；`reason_code=URGENT_AWAITING_MANAGER`，只能由 Manager 决定，不自动处理，开始前没人决定就过期。
- Admin／Manager 在期限内批准（`APPROVED`）或拒绝（`REJECTED`）。不能审批给自己的或自己创建的申请。
- 期限到了仍未决：`process_due_requests` 在资源锁内重查规则，仍符合（账号启用、资格有效、资源可用、无冲突）则 `APPROVED`（`reason_code=AUTO_APPROVED_AFTER_REVIEW_WINDOW`），否则 `REJECTED`（`AUTO_REJECTED_ACCOUNT_INACTIVE`／`AUTO_REJECTED_QUALIFICATION`／`AUTO_REJECTED_RESOURCE_UNAVAILABLE`／`AUTO_REJECTED_BOOKING_RULES`／`AUTO_REJECTED_CONFLICT`）；`reviewed_by='SYSTEM'`，写审计。自动批准同样生成 Outlook 同步待办。使用数据库时由定时命令 `python manage.py process_due` 触发（见 database/README.md）。
- 预约开始时仍未决的申请（含候补）改为 `EXPIRED`。取消、拒绝、过期立即失去阻挡效力；`hold_until` 保留供追溯。
- 学生的 induction 被拒绝时，其依赖这项资格的未决申请（`PENDING_APPROVAL`／`WAITLISTED`）一并 `REJECTED`（`QUALIFICATION_REJECTED`）。induction 通过不会自动批准任何预约。

## 等待名单与自动递补

业务层的 `_promote_waitlist(resource_id)`（`booking/services/waitlist.py`）在**同一事务、持有该资源锁**时运行，处理该资源全部 `WAITLISTED` 预约：

1. 按 `(created_at, id)` 升序遍历。**顺序就是先到先得的依据**，`created_at` 需保存到微秒；如有条件，建议加一个单调递增的序号列作为最终排序依据，避免同一时刻提交时顺序不确定。
2. 已过开始时间的候补改为 `EXPIRED`；仍有阻挡记录的跳过；资源不可用时跳过；否则仍符合规则的改为 `PENDING_APPROVAL`（`reason_code=PROMOTED_FROM_WAITLIST`，重新计算 `hold_until`／`review_due_at`），不符合的改为 `REJECTED`（`reason_code` 为规则检查的错误码，如 `QUALIFICATION_REQUIRED`、`ACCOUNT_INACTIVE`）。同时写审计 `BOOKING_PROMOTED`／`BOOKING_REJECTED`（actor 为 `SYSTEM`）。递补不会直接获批，仍要走审批期限。
3. 触发时机：取消、拒绝、过期、改期、自动拒绝，以及资源恢复 `AVAILABLE`。

递补会修改**其他学生**的预约，但只持有资源锁。这是可以的，因为所有会改变同一资源占用情况的写操作（创建、审批、取消、改期、资料审核、时间推进）都会先锁住该资源。数据库适配器必须保证：`atomic` 嵌套调用时复用外层事务（或使用 savepoint），并且不会在已持有资源锁的情况下，再按不同顺序去锁其他资源。

建议索引：`(resource_id, status, created_at)` 用于读取候补队列，`(status, review_due_at)` 用于找出审批期限已到的申请，`(student_id, status)` 用于重复预约检查和资料被拒时的级联拒绝。

## 事务和并发要求

`atomic(resource_ids, student_ids)` 必须实现真实数据库事务和一致顺序的资源／学生锁。创建申请、人工批准、期限到期后的自动决定、资料被拒时的级联拒绝以及规则修改必须遵循业务服务传入的锁约定。在同一事务内重读资源规则、资格及阻挡预约，然后保存预约和审计；失败完整回滚。

数据库索引可覆盖资源、时间区间、状态和占位截止时间。仅对 APPROVED 建区间排斥约束无法防止跨状态的占位冲突，仍需资源锁和事务内重查。可用性接口只提供快照，不能代替写入事务中的校验。适配器需验证两个并发请求只会产生一个占位／获批预约，且错误能回滚全部关联写入。

同一资源／学生锁内还必须检查该学生是否已经有与新时段重叠的有效申请（状态为 `PENDING_APPROVAL`、`WAITLISTED` 或 `APPROVED`；早期数据中的 `WAITING_QUALIFICATION` 也算）。存在时业务层返回 `DUPLICATE_BOOKING`，不能再创建一条候补记录。终态记录不阻止重新申请；不同资源同一时间不属于重复预约。

规则更新写入 `RESOURCE_BOOKING_POLICY_UPDATED` 审计，保存前后分钟数。`QualificationSubmission.valid_until` 在 VERIFIED 时由业务服务设定（审核时间加可配置规则 `qualification_validity_days`，默认 120 天），PENDING／REJECTED 为空；`QUALIFICATION_VERIFIED` 审计的 details 带 `valid_until`。审计查询接口 `GET admin/audit/` 在业务层对 `list_audit()` 的结果做筛选和分页；数据量变大后，数据库适配器应为审计表的 `at`、`entity_type`＋`entity_id`、`actor_id`、`action` 建索引，必要时再把筛选下推到查询中（结果需与现有测试一致）。审计记录只追加，不修改、不删除。每个资源关联一项 `required_qualification_id`，不同资源可以不同；该要求的前置项记录在 `qualification_requirement.prerequisite_ids`。不要改成用户全局 inducted 布尔值。

## 接入和升级

- 已有数据库按顺序运行 `database/migrations/` 里的全部脚本（001–005，都可重复执行），步骤见 `database/README.md` 第 2 节。
- 用户邮箱应从可信身份数据补齐；不要编造正式用户邮箱。
- 环境变量 `DEFAULT_PENDING_HOLD_MINUTES` 仅用于创建演示种子数据，不能覆盖数据库中的 Manager 配置。
- 时间字段使用带时区存储；API 输出 UTC，开放时间规则使用资源时区。
- `save_booking`、`save_resource`、`save_principal` 必须读写上述全部字段；替换适配器后保持 API 结构不变。

## Outlook 同步记录

Outlook 使用 `OutlookSyncRecord` 和 `get_outlook_sync`／`list_outlook_sync`／`save_outlook_sync`。预约、审计和同步待办同事务提交；网络调用在事务外。Pending 申请不创建 Outlook 事件；人工或自动批准后才同步。同步是单向的，系统从不读取 Outlook 的修改。改期时如果发现事件已经被用户删除，就把待办改成 CREATE 重新写入（保留旧 iCal UID 作为标记，换一个 transactionId），并写审计 `OUTLOOK_EVENT_RECREATED`。只有使用 PostgreSQL 这类共享数据库时，才能多进程运行后端和独立的后台处理命令；内存演示不共享或持久化数据。
