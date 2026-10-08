# Sprint 1 数据库接口交接

业务使用 `booking/repository.py` 的 `Repository` Protocol 和 `booking/domain.py` 的实体。数据库负责人实现适配器，通过 `REPOSITORY_FACTORY` 接入；附件继续通过 `FILE_STORAGE_FACTORY` 接入私有存储。当前提供内存适配器用于联调，本次未增加 ORM 模型或数据库迁移。

## 客户补充要求对应字段

| 实体 | 字段 | 持久化约定 |
| --- | --- | --- |
| Principal | `university_email: str` | 必填；正式环境由可信 SSO／身份记录提供。与 zID、姓名一起返回用户接口。不要据此推断角色或资格 |
| Resource | `pending_hold_minutes: int` | 必填整数 1–10080；演示默认 30。Manager 修改时持久化并记录审计 |
| Booking | `hold_until: datetime \| None` | 可空、带时区。保存创建时算出的截止时间，不随资源规则变化重算 |

`hold_active`、`blocks_slot` 是 API 根据状态和服务端时间计算的响应字段，不需要持久化布尔值。申请状态仍为原六种：`WAITING_QUALIFICATION`、`PENDING_APPROVAL`、`APPROVED`、`REJECTED`、`CANCELLED`、`EXPIRED`。

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

只有没有任何阻挡记录的 Pending 新申请才取得占位：`min(start, created_at + pending_hold_minutes)`。冲突申请保留人工审批资格但 `hold_until=None`，不能叠加或延长别人的占位。已批准预约始终阻挡重叠时段。取消、拒绝、申请过期立即失去占位效力；保留原截止时间供追溯。

用户已确认：**占位到期后保留 Pending，只释放占位**。到期通过查询条件即时生效，不依赖后台清理，也不应把所有到期占位改成 `EXPIRED`。原有 24 小时审批升级与到预约开始时过期的流程继续运行；没有自动续占、自动排队或等待名单晋升。

## 事务和并发要求

`atomic(resource_ids, student_ids)` 必须实现真实数据库事务和一致顺序的资源／学生锁。创建申请、人工批准、资格审核触发的自动批准以及规则修改必须遵循业务服务传入的锁约定。在同一事务内重读资源规则、资格及阻挡预约，然后保存预约和审计；失败完整回滚。

数据库索引可覆盖资源、时间区间、状态和占位截止时间。仅对 APPROVED 建区间排斥约束无法防止跨状态的占位冲突，仍需资源锁和事务内重查。可用性接口只提供快照，不能代替写入事务中的校验。实际适配器需验证两个并发请求只会产生一个占位／获批预约，且错误能回滚全部关联写入。

规则更新写入 `RESOURCE_BOOKING_POLICY_UPDATED` 审计，保存前后分钟数。身份、资料、资格有效期、审批与取消的现有字段及审计继续持久化。每个资源目前关联一项 `required_qualification_id`，不同资源可以不同；不要改成用户全局 inducted 布尔值。未来多项前置资格需单独扩展关系和接口。

## 接入／迁移建议

- 既有用户邮箱应从可信身份数据补齐；不要编造正式用户邮箱。
- 既有资源设置 `pending_hold_minutes=30`，或使用团队确认的初始值。环境变量 `DEFAULT_PENDING_HOLD_MINUTES` 仅用于创建演示种子数据，不能覆盖数据库中的 Manager 配置。
- 既有 Pending 预约的 `hold_until` 可初始化为 NULL；不要回填新的占位而抢占已存在的预约。既有 APPROVED 继续占用，终态继续释放。
- 时间字段使用带时区存储；API 输出 UTC，开放时间规则使用资源时区。
- `save_booking`、`save_resource`、`save_principal` 必须读写上述新增字段；替换适配器后保留原 API 结构。

Outlook 继续使用 `OutlookSyncRecord` 和 `get_outlook_sync`／`list_outlook_sync`／`save_outlook_sync`。预约、审计和同步待办同事务提交；网络调用在事务外。Pending 占位不创建 Outlook 事件。适配器完成后才能使用多进程后端及独立后台处理命令；内存演示不共享或持久化数据。
