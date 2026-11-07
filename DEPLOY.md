<!-- Sprint 3 (2026-10-25) -->
# 部署（Docker Compose）

一台装了 Docker 的 Linux 服务器（例如 AWS EC2 Ubuntu）上用四个容器运行整个网站：

| 容器 | 内容 |
| --- | --- |
| `db` | PostgreSQL 16，数据在 `pgdata` 卷里（induction 证明文件也存在数据库里） |
| `api` | Django + gunicorn（`backend/Dockerfile`），启动脚本 `backend/entrypoint.sh` |
| `scheduler` | 每分钟处理到期审批、提醒、缺席记录、邮件重试和 Outlook 同步，使用与 API 相同的后端代码和 PostgreSQL |
| `web` | nginx（`frontend/Dockerfile`）：提供前端页面，并把 `/api/` 转给 `api`，同一个地址，不需要 CORS |

只开放 `web` 的 80 端口；数据库和 API 不对外。

## 一、配置：`.env.docker`

```bash
cp .env.docker.example .env.docker
```

必须改的：

| 变量 | 填什么 |
| --- | --- |
| `DB_PASSWORD` | 数据库密码，随便生成一个长的：`openssl rand -hex 24` |
| `DJANGO_SECRET_KEY` | 同上：`openssl rand -hex 32` |
| `ALLOWED_HOSTS` | 浏览器访问用的主机名或 IP，逗号分隔，例如 `localhost,13.211.0.10` |
| `SITE_URL` | 浏览器访问的地址，例如 `http://13.211.0.10`（邮件里的链接用它） |

演示部署保持 `DEBUG=true`、`ENABLE_DEMO_AUTH=true`（两个都为 true 才能用演示 zID 登录）、`LOAD_DEMO_DATA=true`。

**`.env.docker` 不要提交**（已在 `.gitignore` 里），里面有密码。

## 二、启动

```bash
docker compose --env-file .env.docker up -d --build
docker compose --env-file .env.docker ps
docker compose --env-file .env.docker logs -f api
docker compose --env-file .env.docker logs -f scheduler
```

浏览器打开 `http://<服务器地址>`。四个容器都是 `running`、`api` 是 `healthy` 就好了。`scheduler` 日志应显示
`Scheduler started`，之后每轮输出处理了多少到期申请、邮件和 Outlook 任务。它只能使用 PostgreSQL，不能使用进程内存仓储。

需要手动验证一次定时处理但不想启动永久循环时，可以运行：

```bash
docker compose --env-file .env.docker run --rm scheduler manage run_scheduler --once
```

**第一次启动**（数据库是空的）时，`entrypoint.sh` 用 `backend/database/schema.sql` 建表；`LOAD_DEMO_DATA=true` 时再导入 `seed_resources.sql`、`seed_users.sql`（2 个房间、20 台设备、2 项培训要求、6 个演示账号）。这些在同一个事务里，要么全部成功，要么什么都不写。之后的启动不会再建表或导入演示数据，网页上改过的内容和密码都会保留。

演示账号：学生 `z1000001`、`z1000002`（University sign-in）；Admin `z9000001`、Manager `z9000002`（Staff sign-in，演示密码见 `backend/README.md`）。新学生可以在模拟 SSO 页点 **Create one** 自己建账号。

## 三、更新代码和数据库

**迁移不会自动执行。** `schema.sql` 已经是最新结构，所以新建的数据库不需要迁移；已经在运行的数据库，遇到新版本带来的迁移（`backend/database/migrations/` 里新增的文件）时，要在换上新代码**之前**执行一次。换成新代码后按这个顺序：

```bash
# 1. 备份数据库
docker compose --env-file .env.docker exec -T db pg_dump -U smartlab smartlab > ~/backup-before-update.sql
# 2. 只构建新镜像，旧容器继续服务
docker compose --env-file .env.docker build
# 3. 用新镜像临时跑一次新迁移（旧容器里没有新迁移文件，所以不能用 exec）；没有新迁移就跳过
docker compose --env-file .env.docker run --rm api migrate database/migrations/012_additional_hours_requests.sql
docker compose --env-file .env.docker run --rm api migrate database/migrations/013_long_booking_requests.sql
docker compose --env-file .env.docker run --rm api migrate database/migrations/014_remove_booking_freeze.sql
docker compose --env-file .env.docker run --rm api migrate database/migrations/015_resource_internal_info.sql
docker compose --env-file .env.docker run --rm api migrate database/migrations/016_extension_requests.sql
# 4. 换上新容器
docker compose --env-file .env.docker up -d
```

`api` 的入口就是 `entrypoint.sh`，所以第 3 步的参数直接写 `migrate <文件>`。先迁移再换代码，新代码启动时数据库已经是新结构；迁移只加列和表时，旧代码在迁移后的库上也照常运行，不会中断服务。

上例适用于数据库已经执行到 011 的情况；若缺少更早迁移，先按编号补齐缺少的脚本。必须先执行 012，再执行 013；两者都可重复执行，并保留已有预约的时间、状态和审批结果。012 为额外每周小时申请增加四个字段及约束，该申请等待 Manager 决定时不占时段。013 为长时段请求增加标志、理由及约束，该请求沿用普通占位／候补流程。两种特殊请求都由 Manager 明确审批，不自动批准。首次建库已经包含 012 和 013，无需另跑。

**014（1.25.0）会删列和表**（`app_users.no_show_count`、`frozen_until`，表 `unfreeze_request`），和前面只加不删的迁移不同：

- 迁移后、换上新容器前的几秒里，旧容器读用户会报错；部署脚本两步紧挨着，影响很短。
- 删掉的冻结数据只在部署前的备份里。
- 要回滚到 1.25.0 之前的代码，先用新镜像重跑 006（可重复执行）补回列和表，再 `--rollback`：
  `docker compose --env-file .env.docker run --rm api migrate database/migrations/006_calendar_notifications_attendance_series.sql`

为什么不在每次启动时重跑全部迁移：迁移 005 会把两个演示员工账号的密码改回演示密码，重跑会冲掉 Manager 改过的密码。

## 四、备份、停止、清空

```bash
# 备份数据库到当前目录
docker compose --env-file .env.docker exec -T db pg_dump -U smartlab smartlab > smartlab-backup.sql

# 停止（数据保留）
docker compose --env-file .env.docker stop

# 删除容器和数据库数据，下次启动重新建一个全新的演示库（数据无法恢复）
docker compose --env-file .env.docker down -v
```

## 五、AWS EC2（第一次部署）

1. **建实例**：区域 `ap-southeast-2`（悉尼），Ubuntu Server 24.04 LTS，`t3.small`（2 GB 内存），磁盘 20 GB。新建或选一个密钥对，下载 `.pem`。
2. **安全组**：入站只开 22（来源选 My IP）和 80（来源 `0.0.0.0/0`）。不用 HTTPS 时不需要 443。
3. **固定公网 IP（可选）**：实例停止再启动后公网 IP 会变，`ALLOWED_HOSTS`、`SITE_URL` 也要跟着改。要固定就申请一个 Elastic IP 绑定到实例（实例运行时绑定的 Elastic IP 不收费）。
4. **登录服务器**（Windows 自带 OpenSSH）：

   ```bash
   ssh -i smartlab.pem ubuntu@<公网IP>
   ```

5. **装 Docker**，再加 2 GB swap（2 GB 内存构建前端时可能不够）：

   ```bash
   curl -fsSL https://get.docker.com | sudo sh
   sudo usermod -aG docker ubuntu
   sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
   echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
   exit
   ```

   重新 `ssh` 登录后，`docker ps` 不报权限错误即可。

6. **放代码**：不在服务器上存 GitLab Token，从本机打包上传已提交的版本：

   ```bash
   git -C 'C:\Users\loy\Desktop\9900\team-repo' archive --format=tar.gz -o smartlab.tar.gz HEAD
   scp -i smartlab.pem smartlab.tar.gz ubuntu@<公网IP>:~
   ```

   在服务器上：

   ```bash
   mkdir -p ~/smartlab && tar -xzf ~/smartlab.tar.gz -C ~/smartlab && cd ~/smartlab
   ```

7. **配置并启动**：按第一节建 `.env.docker`（`ALLOWED_HOSTS=localhost,<公网IP>`，`SITE_URL=http://<公网IP>`），再按第二节启动。第一次构建要几分钟。
8. **更新**：本机提交后重新打包上传，解压覆盖到 `~/smartlab`（`.env.docker` 不在压缩包里，不会被覆盖），再按第三节的四步更新（有新迁移时先迁移再换容器）。
9. **省额度**：不用时在 EC2 控制台 Stop 实例（数据在磁盘上，保留）；彻底不用时 Terminate（数据全部删除）。
