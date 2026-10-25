# 本地 PostgreSQL 数据库与前后端运行

每位组员使用自己的本地数据库。以下命令适用于 Windows PowerShell，在项目的 `backend` 目录执行；前端启动另开终端。

## 包含的文件和数据

- `database/schema.sql`：14 张表（1.16.0 起多了 `site_contact`）、约束、索引、序列和审计保护触发器。
- `database/seed_resources.sql`：2 条培训要求（Advanced 要求先通过 General）、2 个房间、20 台设备（记录所在房间）。
- `database/seed_users.sql`：6 个演示账号（与内存版演示数据相同的假 zID 和 id），以及 z1000001 一条已通过的 induction。全部是编造的数据，不要把真实学生的 zID 提交进 Git。
- `database/migrations/`：已有数据库的升级脚本 001–007，按编号顺序执行，都可以重复执行（见第 2 节）。
- `booking/tests/test_postgres.py`：用真实 PostgreSQL 跑的适配器集成测试（见第 6 节）。
- `booking/postgres.py`：数据库及上传文件存储适配器。
- `requirements-postgres.txt`：后端依赖及 PostgreSQL 驱动。
- `config/settings.py`：从环境变量读取数据库连接配置。

这些初始化文件不包含预约、Outlook 同步或审计记录。房间开放时间、预约时长、审批期限（`pending_hold_minutes`，默认 1440 分钟即 24 小时）、培训有效期等是项目演示配置，需要团队后续确认。

## 1. 准备软件

安装并启动 PostgreSQL（推荐 18；16 及以上已验证可用），用同一版本的 `psql` 导入。准备 Python 3.13 环境（例如激活自己的 Conda 环境）和能运行项目 Vite 8 的 Node.js。

在 VS Code 打开克隆后的项目，在终端进入 `backend`。以下 PostgreSQL 安装路径按自己的电脑修改：

```powershell
$pgBin = 'C:\Program Files\PostgreSQL\18\bin'
$dbName = 'SmartLab_9900_F15E_BREAD'
```

如果安装在 D 盘，可以把第一行改为 `$pgBin = 'D:\PostgreSQL\bin'`。连接 PostgreSQL 时输入自己安装时设置的密码，不要把密码写进 Git 文件。

## 2. 首次建立并导入数据库

以下操作只用于首次创建一个新的空数据库。若数据库已经存在，创建命令会失败并停止；不要删除现有数据库来强行继续。

```powershell
& "$pgBin\createdb.exe" --host=localhost --port=5432 --username=postgres --password --encoding=UTF8 --template=template0 $dbName
if ($LASTEXITCODE -ne 0) { throw '创建失败。请检查报错；若已有数据库，请先确认其用途。' }

& "$pgBin\psql.exe" --host=localhost --port=5432 --username=postgres --password --dbname=$dbName --no-psqlrc --set=ON_ERROR_STOP=1 --single-transaction --file='.\database\schema.sql' --file='.\database\seed_resources.sql' --file='.\database\seed_users.sql'
if ($LASTEXITCODE -ne 0) { throw '导入失败，导入事务已回滚。请先排查报错。' }
```

`schema.sql` 的建 schema 语句应为 `CREATE SCHEMA IF NOT EXISTS public;`，以兼容新数据库自带的 public。这不代表脚本可以重复导入：表和种子数据只导入一次。保留导出文件中的 `\restrict` / `\unrestrict`，使用 `psql` 执行整个文件。

如果创建成功但导入失败，修复原因后仅重新执行导入命令，不要再次创建数据库。不要在已有业务数据的数据库中试用这些导入命令。

### 已经建过库：升级到最新结构

不想重建的话，按编号顺序执行 `database/migrations/` 里的全部脚本。每个脚本都可以重复执行，已经做过的步骤会跳过，不删除任何数据；在已经是最新结构的库上执行也不会有变化。所以不用判断自己的库停在哪一步，全部执行一遍即可：

```powershell
Get-ChildItem .\database\migrations\*.sql | Sort-Object Name | ForEach-Object {
    & "$pgBin\psql.exe" --host=localhost --port=5432 --username=postgres --password --dbname=$dbName --no-psqlrc --set=ON_ERROR_STOP=1 --single-transaction --file=$_.FullName
    if ($LASTEXITCODE -ne 0) { throw "升级失败：$($_.Name)" }
}
```

每个文件都会要一次 PostgreSQL 密码。`$pgBin`、`$dbName` 见第 1 节，新开的窗口要重新设置。

| 脚本 | 内容 |
| --- | --- |
| `001_client_approval_flow.sql` | 资源状态 `status`、`status_reason`；审批期限默认 1440 分钟 |
| `002_week5_rules.sql` | 前置 induction `prerequisite_ids`、设备所在房间 `room_id`；演示数据设好 Advanced→General 和设备所在房间 |
| `003_staff_sign_in.sql` | 新表 `staff_credential`（密码哈希和邀请码）；演示账号设好密码，其他已有员工拿到邀请码，在 staff 登录页激活 |
| `004_staff_booking_urgent.sql` | `booking` 加 `created_by`、`urgent`、`urgent_reason`；已有预约的 `created_by` 填成 `student_id` |
| `005_resource_category_demo_password.sql` | 设备类别 `bookable_resource.category`（演示设备填上编的类别，已填的不覆盖）；演示账号 z9000001、z9000002 的密码设为 `123` |
| `006_calendar_notifications_attendance_series.sql` | 新表 `notification`、`calendar_feed`、`unfreeze_request`、`booking_series`；`app_users` 加 `no_show_count`、`frozen_until`；`booking` 加 `series_id`、`attendance`、`checked_in_at`。第一次执行时把已经开始的已批准预约标为 `NOT_TRACKED`，不会算成缺席 |
| `007_change_requests_guidance_details_contact.sql` | 1.16.0：`booking` 加 `replaces_id`（申请改期，外键指向原预约，加部分唯一索引：一个预约同时只有一个未决定的改期）；`qualification_requirement` 加 `how_to_complete`、`accepted_evidence`、`reviewer`、`contact`（默认空）；`bookable_resource` 加 `capacity`（只有房间，1–1000）和 `details`（`jsonb` 数组，默认 `[]`）；新表 `site_contact`（实验室联系方式，只有一行）。不改已有数据 |

升级后的库和用 `schema.sql` 与种子文件新建的库，`pg_dump --schema-only` 结果完全一致。每次改表结构都要按这个方法验证：新建一个库、一个按旧脚本建的库，后者执行全部升级脚本（执行两遍），再比较两边的 `pg_dump --schema-only`。

如果本地库里只有测试数据，也可以用 pgAdmin 或 `dropdb` 删掉重建（删之前确认里面没有需要保留的东西）。

## 3. 安装后端依赖和配置连接

仍在 `backend` 目录，激活自己的 Python 环境后执行：

```powershell
python -m pip install -r requirements-postgres.txt
if ($LASTEXITCODE -ne 0) { throw '后端依赖安装失败' }

$env:DB_NAME = 'SmartLab_9900_F15E_BREAD'
$env:DB_USER = 'postgres'
$env:DB_HOST = 'localhost'
$env:DB_PORT = '5432'
$env:DB_PASSWORD = [System.Net.NetworkCredential]::new('', (Read-Host 'PostgreSQL password' -AsSecureString)).Password
$env:DEBUG = 'true'
$env:ENABLE_DEMO_AUTH = 'true'
$env:AUTH_PROVIDER = 'booking.authentication.DemoIdentityProvider'
$env:SEED_DEMO_DATA = 'false'
$env:REPOSITORY_FACTORY = 'booking.postgres.PostgresRepository'
$env:FILE_STORAGE_FACTORY = 'booking.postgres.PostgresFileStorage'
$env:OUTLOOK_ENABLED = 'false'
```

这些环境变量只对当前终端及其启动的程序生效。新开后端终端时需要重新设置；项目不会自动加载 `.env`。两个工厂变量必须设置，否则默认使用内存存储（`REPOSITORY_FACTORY` 指向 PostgreSQL 适配器时，后端才会连接数据库；不设置时不需要安装 PostgreSQL，使用内存演示数据）。`SEED_DEMO_DATA=false` 必须保留，避免运行时再次注入默认演示数据。想让登录在重启后端后仍然有效，可以再设置一个固定的本地 `$env:DJANGO_SECRET_KEY`（只用于本机，不要提交）。

确认适配器能读取数据：

```powershell
python manage.py shell -c "from booking.postgres import PostgresRepository; r = PostgresRepository(); print('Users:', len(r.list_principals())); print('Resources:', len(r.list_resources())); print('Requirements:', len(r.list_requirements())); print('Submissions:', len(r.list_submissions()))"
```

首次导入后的预期：Users 6、Resources 22、Requirements 2、Submissions 1。

## 4. 启动后端和前端

在已配置环境变量的后端终端执行，保持终端运行：

```powershell
python manage.py runserver 127.0.0.1:8000 --noreload
```

另开终端，进入项目的 `frontend` 目录：

```powershell
npm.cmd ci
if ($LASTEXITCODE -ne 0) { throw '前端依赖安装失败' }
npm.cmd run dev
```

打开终端显示的网址，通常为 `http://localhost:5173`。前端通过 Vite 将 `/api` 请求转发至 `http://127.0.0.1:8000`。若端口被占用，先确认哪个已有服务占用了端口。

## 5. 演示登录和验证

学生用大学登录（模拟 SSO，只填 zID，不校验密码）；Admin 和 Manager 点登录页的 **Staff sign-in**，用 zID + 密码登录。

| zID | 角色 | 说明 |
| --- | --- | --- |
| z1000001 | STUDENT | 已通过基础 induction，可以直接预约 Lab Room 1 及其设备 |
| z1000002 | STUDENT | 没有 induction |
| z1000003 | STUDENT | 没有 induction |
| z1000004 | STUDENT | 没有 induction |
| z9000001 | ADMIN | 审核资料和预约；staff 登录，演示密码 `123` |
| z9000002 | MANAGER | 房间状态、导出、人员管理；staff 登录，演示密码 `123` |

建议走一遍：z1000002 上传测试材料 → z9000001 审核通过 → z1000002 预约 → z9000001 批准。然后停掉后端再启动，确认数据还在。只使用可分享的测试附件。新操作写入各自的本地数据库，不会自动进入 Git。后端重启后如果登录失效，重新登录；开发模式未固定密钥时会生成新的临时密钥。

日常启动不需要再次导入 SQL：启动 PostgreSQL、在后端终端重新设置环境变量并运行后端，再启动前端即可。

### 建一个新的 Manager（不用写 SQL）

在设置了上面环境变量的后端终端执行：

```powershell
python manage.py create_manager --zid z9000003 --name "Lab Manager" --email z9000003@ad.unsw.edu.au
```

命令会输出一次性邀请码。对方在 Staff sign-in 页面选“首次激活”，填 zID、邀请码和自己的密码。之后的员工由 Manager 在 User Management 页面用 Add staff 添加；房间和设备由 Manager 在 Resources 页面添加。

### 定时处理到期申请

审批期限到了的申请会在有人访问网页时顺带处理。为了没人访问时也能按时自动批准／拒绝，在设置了同样环境变量的终端里定时运行（例如每分钟一次，用 Windows 任务计划程序或服务器的 cron）：

```powershell
python manage.py process_due
```

输出 `Decided or expired N request(s).`。它也会把开始后没确认到场的预约记为缺席（达到次数会冻结）。演示时也可以手动运行一次。该命令只能用于数据库模式，内存模式会直接报错退出。

## 6. 用真实数据库跑适配器测试

在已设置上面环境变量的后端终端执行。Django 会临时创建并删除一个 `test_<库名>` 测试库，不会改动你自己的数据：

```powershell
python manage.py test booking.tests.test_postgres -v 2
```

这组测试覆盖：各类记录读写和类型、房间状态、前置 induction 和设备所在房间、staff 邀请码激活和密码登录、上传附件、完整审批流程（待审批 → 批准 → 取消 → 候补递补 → 24 小时到期自动批准）、事务回滚、审计记录不可修改、两个人同时申请同一时段时只有一人进入待审批，以及通知、订阅链接、解冻申请、重复预约、到场确认和冻结的读写。

其余测试（`python manage.py test booking`）使用内存存储，跑之前先把 `REPOSITORY_FACTORY` 和 `FILE_STORAGE_FACTORY` 两个变量清掉（或新开一个终端）。

## 验证范围和限制

第 6 节的集成测试和第 2 节的升级验证在 PostgreSQL 16 上通过；`process_due` 命令可在数据库模式运行；前后端完整流程（上传、审核、预约、批准、改房间状态）的数据都会写入数据库，重启后端后仍在。

这是本地联调用的适配方案。适配器使用数据库级 advisory lock 串行化所有写入：并发申请同一时段的正确性已有测试覆盖，但没有做压力测试，不能据此宣称已通过生产性能验收。

提交 Git 时仅选择这些说明、初始化 SQL、适配器和配置改动。不要提交 `.env`、数据库密码、完整数据备份或个人测试附件。
