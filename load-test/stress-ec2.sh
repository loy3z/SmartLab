#!/usr/bin/env bash
# Sprint 3：在 EC2 上另起一套临时测试副本做压力测试（2026-10-29）。Git Bash 运行；保持 LF 换行。说明见 README.md。
#
# 用法（先设 EC2_HOST=ubuntu@<服务器地址>；密钥默认 ~/.ssh/smartlab-ec2，可用 EC2_KEY 改）：
#   bash load-test/stress-ec2.sh                # 正式规模：200 学生 + 10 Admin + 2 Manager，约 15 分钟
#   bash load-test/stress-ec2.sh --small        # 试跑：20 学生 + 2 Admin + 1 Manager，各阶段缩短，约 5 分钟
#   bash load-test/stress-ec2.sh --no-fill      # 不导入 fill.sql 的一学期历史数据（只有演示数据和压测账号）
#   bash load-test/stress-ec2.sh --keep ...     # 跑完不删测试副本（之后用 --teardown 删）
#   bash load-test/stress-ec2.sh --profile      # 不压测：在空闲的测试副本里跑 profile.py（单个请求的耗时和 SQL 数），再删副本
#   bash load-test/stress-ec2.sh --teardown     # 只删测试副本
#   bash load-test/stress-ec2.sh --worktree ... # 测工作区里还没提交的改动（git stash create 生成临时提交对象，
#                                               # 不动工作区和 stash 列表；没跟踪的新文件不包括在内）
# 注意：脚本运行中不要改这个文件（bash 边执行边读，改了会读错位置）。
#
# 做什么：
#   1. 把已提交的 HEAD 打包上传到 ~/smartlab-stress，用全新的 .env.stress 起一套独立的 compose 项目 smartlab-stress：
#      自己的数据库卷、随机生成的数据库密码和 Django 密钥、邮件关闭、只监听服务器的 127.0.0.1:8080（公网访问不到）。
#      DEBUG=true 和线上一致：演示登录（学生 zID、员工密码）只在 DEBUG 和 ENABLE_DEMO_AUTH 都开时可用。
#      不读、不复制线上的 .env.docker；线上 smartlab 项目的容器和数据库不动。
#   2. 新库自动建表并加载演示数据，再导入 fill.sql（约 5000 条历史预约）和 seed.sql（200 学生、9+1 名员工）。
#   3. 服务器每几秒记录 CPU（vmstat）和容器占用（docker stats）；本机开 SSH 隧道 127.0.0.1:18080 → 服务器 8080。
#   4. 本机跑 load.py（日常 / 高峰 / 逐步加人），再跑 report.py。结果在仓库外的 ../output/stress/<时间>/（可用 STRESS_OUT 改）。
#   5. 删掉测试副本：容器、数据库卷、镜像和 ~/smartlab-stress（除非 --keep）。
# 测试期间线上网站和测试副本共用 2 核 CPU，线上会变慢。
set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO=$(cd "$HERE/.." && pwd)
HOST=${EC2_HOST:?先设 EC2_HOST=ubuntu@服务器地址}
KEY=${EC2_KEY:-$HOME/.ssh/smartlab-ec2}
LOCAL_PORT=${LOCAL_PORT:-18080}
SSH=(ssh -i "$KEY" -o BatchMode=yes -o ConnectTimeout=15 -o ServerAliveInterval=30 "$HOST")
say() { echo "[stress] $*"; }

KEEP=0; SMALL=0; ONLY_TEARDOWN=0; FILL=1; PROFILE=0; WORKTREE=0
for arg in "$@"; do
  case "$arg" in
    --keep) KEEP=1 ;; --small) SMALL=1 ;; --teardown) ONLY_TEARDOWN=1 ;; --no-fill) FILL=0 ;;
    --profile) PROFILE=1 ;; --worktree) WORKTREE=1 ;;
    *) echo "用法：bash load-test/stress-ec2.sh [--small] [--no-fill] [--keep] [--profile] [--worktree] | --teardown"; exit 2 ;;
  esac
done

teardown() {
  "${SSH[@]}" 'bash -s' <<'REMOTE'
main() {
rm -f ~/stress-sampling
if [ -d ~/smartlab-stress ]; then
  cd ~/smartlab-stress && docker compose -p smartlab-stress --env-file .env.stress down -v --rmi local >/dev/null 2>&1 || true
fi
docker volume rm smartlab-stress_pgdata >/dev/null 2>&1 || true
rm -rf ~/smartlab-stress ~/smartlab-stress.tar.gz
echo "[server] 测试副本已删除；线上容器：$(docker ps --filter name=smartlab- --format '{{.Names}}' | grep -v stress | tr '\n' ' ')"
}
main </dev/null
REMOTE
}

"${SSH[@]}" true 2>/dev/null || { say "SSH 连不上 $HOST（出口 IP 变了要改安全组 22 端口）"; exit 1; }
if [ "$ONLY_TEARDOWN" = 1 ]; then teardown; exit 0; fi

STAMP=$(date +%Y%m%d-%H%M%S)
if [ "$FILL" = 1 ]; then STAMP+=-history; else STAMP+=-fresh; fi
if [ "$SMALL" = 1 ]; then STAMP+=-small; fi
if [ "$PROFILE" = 1 ]; then STAMP+=-profile; fi
TREE=HEAD
if [ "$WORKTREE" = 1 ]; then
  STAMP+=-worktree
  TREE=$(git -C "$REPO" stash create)
  if [ -z "$TREE" ]; then TREE=HEAD; fi   # 工作区干净时 stash create 不输出
fi
OUT="${STRESS_OUT:-$REPO/../output/stress}/$STAMP"
mkdir -p "$OUT"
SHA=$(git -C "$REPO" rev-parse --short HEAD)
if [ "$TREE" != HEAD ]; then SHA+="+工作区($(git -C "$REPO" rev-parse --short "$TREE"))"; fi
say "版本 $SHA；结果目录 $OUT"

# --- 1. 起测试副本 ------------------------------------------------------------------------------------------------
git -C "$REPO" archive --format=tar.gz -o "$OUT/smartlab-stress.tar.gz" "$TREE"
scp -q -i "$KEY" -o BatchMode=yes "$OUT/smartlab-stress.tar.gz" "$HERE/fill.sql" "$HERE/seed.sql" "$HOST:~/"
rm -f "$OUT/smartlab-stress.tar.gz"
"${SSH[@]}" "bash -s -- $FILL" <<'REMOTE' | tee "$OUT/setup.txt"
set -uo pipefail
FILL=$1
fail() { echo "[server] 失败：$1"; tail -n 40 ~/stress-setup.log; exit 1; }
main() {
avail=$(free -m | awk '/^Mem:/ {print $7}')
[ "$avail" -gt 600 ] || fail "可用内存只有 ${avail} MB"
cd ~ && [ -d ~/smartlab-stress ] && { cd ~/smartlab-stress; docker compose -p smartlab-stress --env-file .env.stress down -v >/dev/null 2>&1; cd ~; }
rm -rf ~/smartlab-stress && mkdir ~/smartlab-stress && tar -xzf ~/smartlab-stress.tar.gz -C ~/smartlab-stress && rm -f ~/smartlab-stress.tar.gz
mv ~/fill.sql ~/seed.sql ~/smartlab-stress/
cd ~/smartlab-stress
umask 077
cat > .env.stress <<EOF
DB_NAME=smartlab
DB_USER=smartlab
DB_PASSWORD=$(openssl rand -hex 24)
DJANGO_SECRET_KEY=$(openssl rand -hex 32)
ALLOWED_HOSTS=localhost
SITE_URL=http://localhost:8080
DEBUG=true
ENABLE_DEMO_AUTH=true
LOAD_DEMO_DATA=true
WEB_PORT=127.0.0.1:8080
EMAIL_ENABLED=false
EOF
DC="docker compose -p smartlab-stress --env-file .env.stress"
$DC up -d --build >~/stress-setup.log 2>&1 || fail "构建或启动"
code=000
for i in $(seq 1 60); do code=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/api/v1/health/); [ "$code" = 200 ] && break; sleep 2; done
[ "$code" = 200 ] || fail "测试副本健康检查 HTTP $code"
echo "[server] 1/3 测试副本已启动（127.0.0.1:8080）"
if [ "$FILL" = 1 ]; then
  $DC exec -T db sh -c 'psql -v ON_ERROR_STOP=1 -q -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < fill.sql >>~/stress-setup.log 2>&1 || fail "导入 fill.sql"
fi
$DC exec -T db sh -c 'psql -v ON_ERROR_STOP=1 -q -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < seed.sql >>~/stress-setup.log 2>&1 || fail "导入 seed.sql"
counts=$($DC exec -T db sh -c 'psql -tA -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT (SELECT count(*) FROM app_users), (SELECT count(*) FROM booking)"' </dev/null)
echo "[server] 2/3 测试数据已导入（用户|预约：$counts）"
touch ~/stress-sampling
nohup sh -c 'while [ -f ~/stress-sampling ]; do ts=$(date +%s); echo "$ts V $(vmstat 1 2 | tail -n 1)"; docker stats --no-stream --format "{{.Name}} {{.CPUPerc}} {{.MemUsage}}" | sed "s/^/$ts C /"; sleep 2; done' >~/stress-stats.log 2>&1 </dev/null &
echo "[server] 3/3 开始记录 CPU 和容器占用"
}
main </dev/null
REMOTE
[ "${PIPESTATUS[0]}" = 0 ] || { say "准备测试副本失败，正在清理"; teardown; exit 1; }

if [ "$PROFILE" = 1 ]; then
  "${SSH[@]}" 'rm -f ~/stress-sampling'
  scp -q -i "$KEY" -o BatchMode=yes "$HERE/profile.py" "$HOST:~/smartlab-stress/profile.py"
  "${SSH[@]}" 'cd ~/smartlab-stress && docker compose -p smartlab-stress --env-file .env.stress exec -T api python - < profile.py' \
    2>&1 | tee "$OUT/profile.txt"
  if [ "$KEEP" = 1 ]; then say "保留测试副本"; else teardown; fi
  exit 0
fi

# --- 2. 隧道 + 压测 -------------------------------------------------------------------------------------------------
"${SSH[@]}" -N -o ExitOnForwardFailure=yes -L "127.0.0.1:$LOCAL_PORT:127.0.0.1:8080" &
TUNNEL=$!
cleanup() {
  kill "$TUNNEL" 2>/dev/null || true
  "${SSH[@]}" 'rm -f ~/stress-sampling' 2>/dev/null || true
  scp -q -i "$KEY" -o BatchMode=yes "$HOST:~/stress-stats.log" "$OUT/server-stats.log" 2>/dev/null || true
  if [ "$KEEP" = 1 ]; then say "保留测试副本（删：bash load-test/stress-ec2.sh --teardown）"; else teardown; fi
}
trap cleanup EXIT
for i in $(seq 1 20); do
  [ "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$LOCAL_PORT/api/v1/health/")" = 200 ] && break; sleep 1
done
say "隧道已连上 127.0.0.1:$LOCAL_PORT"

ARGS=(--base "http://127.0.0.1:$LOCAL_PORT" --out "$OUT")
[ "$SMALL" = 1 ] && ARGS+=(--students 20 --admins 2 --managers 1 --daily-seconds 60 --ramp 20,40 --ramp-seconds 20)
python -u "$HERE/load.py" "${ARGS[@]}" 2>&1 | tee "$OUT/load.txt"
[ "${PIPESTATUS[0]}" = 0 ] || { say "load.py 失败（见上）"; exit 1; }

# 先停记录、取回日志再出报告（cleanup 里会再取一次，无害）
"${SSH[@]}" 'rm -f ~/stress-sampling'; sleep 8
scp -q -i "$KEY" -o BatchMode=yes "$HOST:~/stress-stats.log" "$OUT/server-stats.log"
python "$HERE/report.py" "$OUT"
say "报告：$OUT/summary.md；图：$OUT/chart.html"
