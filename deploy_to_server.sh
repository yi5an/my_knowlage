#!/usr/bin/env bash
# Deploy KnowPilot from this dev machine to the production server.
# 本地开发 → 远程部署的标准入口：rsync 同步代码 + 服务器上重建容器 + 健康检查。
#
# 用法:
#   ./deploy_to_server.sh              # 正式部署
#   DEPLOY_DRY_RUN=1 ./deploy_to_server.sh   # 只看 rsync 会同步什么，不执行
#
# 可用环境变量覆盖默认目标:
#   KNOWPILOT_SERVER_HOST (默认 123.57.165.38)
#   KNOWPILOT_SERVER_PORT (默认 12222)
#   KNOWPILOT_SERVER_USER (默认 yi5an)
#   KNOWPILOT_REMOTE_DIR  (默认 knowpilot，相对服务器家目录)
#
# 注意:
# - 服务器上的 .env 不会被覆盖（部署配置以服务器为准）。
# - 部署前建议先本地跑: cd backend && pytest && ruff check . && mypy app
set -euo pipefail

SERVER_HOST="${KNOWPILOT_SERVER_HOST:-123.57.165.38}"
SERVER_PORT="${KNOWPILOT_SERVER_PORT:-12222}"
SERVER_USER="${KNOWPILOT_SERVER_USER:-yi5an}"
REMOTE_DIR="${KNOWPILOT_REMOTE_DIR:-knowpilot}"
COMPOSE_FILE="docker-compose.prod.yml"
REMOTE="${SERVER_USER}@${SERVER_HOST}"

RSYNC_OPTS=(-az --delete -e "ssh -p ${SERVER_PORT}"
  --exclude='.git' --exclude='.venv' --exclude='node_modules' --exclude='__pycache__'
  --exclude='.pytest_cache' --exclude='.mypy_cache' --exclude='.ruff_cache'
  --exclude='.DS_Store' --exclude='*.db' --exclude='*.db-wal' --exclude='*.db-shm'
  --exclude='dist' --exclude='backend/storage' --exclude='.env'
  --exclude='.worktrees' --exclude='tmp-*.plist')

say() { printf '\033[1;34m[deploy]\033[0m %s\n' "$*"; }

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "请在仓库根目录运行: ./deploy_to_server.sh" >&2
  exit 1
fi

say "目标: ${REMOTE}:${REMOTE_DIR} (ssh 端口 ${SERVER_PORT})"

if [[ "${DEPLOY_DRY_RUN:-0}" == "1" ]]; then
  say "DRY RUN —— 仅预览将同步的文件"
  rsync -n --itemize-changes "${RSYNC_OPTS[@]}" "./" "${REMOTE}:${REMOTE_DIR}/"
  say "预览结束，未做任何更改"
  exit 0
fi

say "1/3 同步代码 (rsync)..."
rsync "${RSYNC_OPTS[@]}" "./" "${REMOTE}:${REMOTE_DIR}/"

say "2/3 重建并重启容器 (backend + frontend + x-collector)..."
ssh -p "${SERVER_PORT}" "${REMOTE}" \
  "cd ${REMOTE_DIR} && docker compose -f ${COMPOSE_FILE} up -d --build"

say "3/3 健康检查..."
ok=0
for _ in $(seq 1 30); do
  if ssh -p "${SERVER_PORT}" "${REMOTE}" \
      "curl -fsS -m 3 http://127.0.0.1/api/v1/health" >/dev/null 2>&1; then
    ok=1
    break
  fi
  sleep 2
done

if [[ "$ok" != "1" ]]; then
  say "健康检查失败！查看日志: ssh -p ${SERVER_PORT} ${REMOTE} 'docker logs knowpilot-backend --tail 50'"
  exit 1
fi

say "部署完成 ✓  (前端 http://${SERVER_HOST}/ )"
say "查看后端日志: ssh -p ${SERVER_PORT} ${REMOTE} 'docker logs -f knowpilot-backend'"
