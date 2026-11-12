<!-- Sprint 3 (2026-10-25) -->
# Deployment (Docker Compose)

The complete website runs in four containers on a Docker-enabled Linux server such as an AWS EC2 Ubuntu instance:

| Container | Contents |
| --- | --- |
| `db` | PostgreSQL 16; data is stored in the `pgdata` volume, including induction evidence files |
| `api` | Django + gunicorn (`backend/Dockerfile`), started by `backend/entrypoint.sh` |
| `scheduler` | Processes expired reviews, reminders, attendance records, email retries and Outlook synchronisation every minute, using the same backend code and PostgreSQL database as the API |
| `web` | nginx (`frontend/Dockerfile`): serves the frontend and proxies `/api/` to `api` on the same origin, so CORS is not required |

Only port 80 on `web` is exposed. The database and API are not public.

## 1. Configure `.env.docker`

```bash
cp .env.docker.example .env.docker
```

Required changes:

| Variable | Value |
| --- | --- |
| `DB_PASSWORD` | A long, randomly generated database password, for example: `openssl rand -hex 24` |
| `DJANGO_SECRET_KEY` | Generate this in the same way: `openssl rand -hex 32` |
| `ALLOWED_HOSTS` | Comma-separated host names or IP addresses used in the browser, for example `localhost,13.211.0.10` |
| `SITE_URL` | Browser-facing address, for example `http://13.211.0.10`; email links use this value |

For a demonstration deployment, keep `DEBUG=true`, `ENABLE_DEMO_AUTH=true` (both must be true for demo zID sign-in) and `LOAD_DEMO_DATA=true`.

**Do not commit `.env.docker`.** It is already listed in `.gitignore` and contains passwords.

## 2. Start

```bash
docker compose --env-file .env.docker up -d --build
docker compose --env-file .env.docker ps
docker compose --env-file .env.docker logs -f api
docker compose --env-file .env.docker logs -f scheduler
```

Open `http://<server-address>` in a browser. All four containers should be `running` and `api` should be `healthy`. The `scheduler` log should display `Scheduler started`, followed in each cycle by the number of expired requests, emails and Outlook tasks processed. The scheduler requires PostgreSQL and cannot use the in-process memory repository.

To verify one scheduled cycle manually without starting a permanent loop, run:

```bash
docker compose --env-file .env.docker run --rm scheduler manage run_scheduler --once
```

On the **first start**, when the database is empty, `entrypoint.sh` creates the tables from `backend/database/schema.sql`. If `LOAD_DEMO_DATA=true`, it then imports `seed_resources.sql` and `seed_users.sql` (two rooms, 20 pieces of equipment, two training requirements and six demo accounts). These steps run in one transaction: either all succeed or nothing is written. Later starts do not recreate tables or re-import demonstration data, so changes and passwords saved through the website are retained.

Demo accounts: students `z1000001` and `z1000002` use University sign-in; Admin `z9000001` and Manager `z9000002` use Staff sign-in with the demo password documented in `backend/README.md`. A new student can select **Create one** on the simulated SSO page to create an account.

## 3. Update the code and database

**Migrations do not run automatically.** `schema.sql` already contains the latest structure, so a new database needs no migrations. For a running database, execute any migration added under `backend/database/migrations/` by a new version **before** switching to the new code. Use this order:

```bash
# 1. Back up the database
docker compose --env-file .env.docker exec -T db pg_dump -U smartlab smartlab > ~/backup-before-update.sql
# 2. Build the new images while the old containers continue serving requests
docker compose --env-file .env.docker build
# 3. Run each new migration once in a temporary container built from the new image.
#    The old container does not contain the new migration files, so do not use exec.
#    Skip this step when there are no new migrations.
docker compose --env-file .env.docker run --rm api migrate database/migrations/012_additional_hours_requests.sql
docker compose --env-file .env.docker run --rm api migrate database/migrations/013_long_booking_requests.sql
docker compose --env-file .env.docker run --rm api migrate database/migrations/014_remove_booking_freeze.sql
docker compose --env-file .env.docker run --rm api migrate database/migrations/015_resource_internal_info.sql
docker compose --env-file .env.docker run --rm api migrate database/migrations/016_extension_requests.sql
# 4. Replace the containers
docker compose --env-file .env.docker up -d
```

The `api` entry point is `entrypoint.sh`, so the Step 3 argument is simply `migrate <file>`. Migrating before replacing the code means the new database structure is ready when the new code starts. When a migration only adds columns and tables, the old code continues to run against the migrated database without service interruption.

The example assumes that migrations up to 011 have already run. If any earlier migration is missing, apply the missing scripts in numerical order. Migration 012 must run before 013. Both are repeatable and retain the times, statuses and approval results of existing bookings. Migration 012 adds four fields and constraints for additional weekly-hours requests; such a request does not hold the time while it awaits a Manager's decision. Migration 013 adds the flag, reason and constraints for long-booking requests, which use the normal hold/waitlist workflow. A Manager explicitly decides both types of special request; neither is approved automatically. A newly created database already includes 012 and 013 and does not need these scripts separately.

**Migration 014 (1.25.0) deletes columns and a table** (`app_users.no_show_count`, `frozen_until` and the `unfreeze_request` table), unlike the earlier additive migrations:

- For a few seconds after the migration and before the new containers start, the old containers will fail when reading users. The deployment script runs these two steps consecutively, so the impact is brief.
- Deleted freeze data remains only in the pre-deployment backup.
- If deployment fails after running 014 but before switching containers, the currently running old version first needs the tables and columns from 006 restored. The deployment script attempts this automatically. If it reports a failure, rerun 006 from `~/smartlab-next` on the server with the command below, then confirm that the old version can sign in and read bookings.
- To roll back to code older than 1.25.0, first rerun 006 with the new image (it is repeatable) to restore the columns and table, then use `--rollback`:
  `docker compose -p smartlab --env-file .env.docker run --rm --no-deps api migrate database/migrations/006_calendar_notifications_attendance_series.sql`

Do not rerun all migrations on every startup: migration 005 resets both demo staff accounts to their demonstration passwords, which would overwrite passwords changed by the Manager.

## 4. Back up, stop and reset

```bash
# Back up the database to the current directory
docker compose --env-file .env.docker exec -T db pg_dump -U smartlab smartlab > smartlab-backup.sql

# Stop while retaining data
docker compose --env-file .env.docker stop

# Delete the containers and database data. The next start creates a new demo database.
# Deleted data cannot be recovered without a backup.
docker compose --env-file .env.docker down -v
```

## 5. AWS EC2 (first deployment)

1. **Create an instance:** use region `ap-southeast-2` (Sydney), Ubuntu Server 24.04 LTS, `t3.small` (2 GB RAM) and a 20 GB disk. Create or select a key pair and download the `.pem` file.
2. **Security group:** allow inbound port 22 from My IP and port 80 from `0.0.0.0/0`. Port 443 is unnecessary if HTTPS is not in use.
3. **Static public IP (optional):** stopping and restarting an instance changes its public IP, requiring updates to `ALLOWED_HOSTS` and `SITE_URL`. To keep the address fixed, allocate and attach an Elastic IP. An Elastic IP attached to a running instance is free.
4. **Sign in to the server** using the OpenSSH included with Windows:

   ```bash
   ssh -i smartlab.pem ubuntu@<public-IP>
   ```

5. **Install Docker** and add 2 GB of swap; 2 GB RAM may be insufficient while building the frontend:

   ```bash
   curl -fsSL https://get.docker.com | sudo sh
   sudo usermod -aG docker ubuntu
   sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
   echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
   exit
   ```

   Sign in again with `ssh` and confirm that `docker ps` reports no permission error.

6. **Upload the code:** do not store a GitLab token on the server. Archive and upload the committed version from the local machine:

   ```bash
   git -C 'C:\Users\loy\Desktop\9900\team-repo' archive --format=tar.gz -o smartlab.tar.gz HEAD
   scp -i smartlab.pem smartlab.tar.gz ubuntu@<public-IP>:~
   ```

   On the server:

   ```bash
   mkdir -p ~/smartlab && tar -xzf ~/smartlab.tar.gz -C ~/smartlab && cd ~/smartlab
   ```

7. **Configure and start:** create `.env.docker` as described in Section 1 (`ALLOWED_HOSTS=localhost,<public-IP>` and `SITE_URL=http://<public-IP>`), then start the system as described in Section 2. The first build takes several minutes.
8. **Update:** after committing locally, archive and upload the code again and extract it over `~/smartlab`. `.env.docker` is not in the archive and is not overwritten. Then follow the four update steps in Section 3, applying any new migrations before replacing the containers.
9. **Save credits:** stop the instance in the EC2 console when it is not in use; data remains on the disk. Terminating the instance deletes all data.
