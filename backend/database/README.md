# 本地 PostgreSQL 数据库与前后端运行

每位组员使用自己的本地数据库。以下命令适用于 Windows PowerShell，在项目的 `backend` 目录执行；前端启动另开终端。

## 包含的文件和数据

- `database/schema.sql`：8 张表、约束、索引、序列和审计保护触发器。
- `database/seed_resources.sql`：2 条培训要求、2 个房间、20 台设备。
- `database/seed_users.sql`：5 个测试账号，保留 zID、UUID、角色及启用状态；姓名和邮箱使用演示值，没有密码数据。
- `booking/postgres.py`：数据库及上传文件存储适配器。
- `requirements-postgres.txt`：后端依赖及 PostgreSQL 驱动。
- `config/settings.py`：从环境变量读取数据库连接配置。

这些初始化文件不包含提交材料、上传附件、审批、预约、Outlook 同步或审计记录。账号 zID 和 UUID 仍与导出来源相同，并非完全匿名化的数据。房间开放时间、预约时长、培训有效期等是项目演示配置，需要团队后续确认。

## 1. 准备软件

安装并启动 PostgreSQL 18，使用 PostgreSQL 18 的 `psql` 导入。准备 Python 3.13 环境（例如激活自己的 Conda 环境）和能运行项目 Vite 8 的 Node.js。

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

这些环境变量只对当前终端及其启动的程序生效。新开后端终端时需要重新设置；项目不会自动加载 `.env`。两个工厂变量必须设置，否则默认使用内存存储。`SEED_DEMO_DATA=false` 必须保留，避免运行时再次注入默认演示数据。

确认适配器能读取数据：

```powershell
python manage.py shell -c "from booking.postgres import PostgresRepository; r = PostgresRepository(); print('Users:', len(r.list_principals())); print('Resources:', len(r.list_resources())); print('Requirements:', len(r.list_requirements())); print('Submissions:', len(r.list_submissions()))"
```

首次导入后的预期：Users 5、Resources 22、Requirements 2、Submissions 0。

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

当前登录页使用 zID，不校验数据库密码列，也不是 SSO。

| zID | 角色 |
| --- | --- |
| z5550599 | STUDENT |
| z5615320 | STUDENT |
| z554046 | STUDENT |
| z5546692 | ADMIN |
| z5659271 | MANAGER |

`z554046` 是导出来源中的原始值（比其他 zID 少一位），分享时未擅自修改。可以先用另外两个学生账号测试；若团队确认它是录入错误，再统一更正。

用学生账号提交测试培训材料，管理员审批，再由学生预约相应资源。只使用可分享的测试附件。新操作写入各自的本地数据库，不会自动进入 Git。后端重启后如果登录失效，重新登录；开发模式未固定密钥时会生成新的临时密钥。

日常启动不需要再次导入 SQL：启动 PostgreSQL、在后端终端重新设置环境变量并运行后端，再启动前端即可。

## 验证范围和当前限制

来源环境已人工验证上传、资格审批和预约写入数据库，以及重复 zID、非法预约时间、审计更新拦截。导出的数据经过静态检查；这组分享文件尚未在另一套全新数据库上完成恢复验证，组员首次导入应按上述数量核对。

这是当前本地联调适配方案。适配器使用数据库级 advisory lock 串行化写入，尚未完成并发压力验证；不能据此宣称已通过生产性能验收。现有内存仓库测试也不等于 PostgreSQL 集成测试全部通过。

提交 Git 时仅选择这些说明、初始化 SQL、适配器和配置改动。不要提交 `.env`、数据库密码、完整数据备份或个人测试附件。
