#!/usr/bin/env bash
# 一键启动 KnowPilot 前后端开发服务(脱离终端会话,持久运行)。
# 用法: ./start.sh
# 停止: ./start.sh stop
set -e

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_LOG="/tmp/knowpilot-uvicorn.log"
FRONTEND_LOG="/tmp/knowpilot-vite.log"

stop() {
  echo "停止服务..."
  for port in 8010 5173; do
    local pid
    pid="$(lsof -ti:$port 2>/dev/null || true)"
    if [ -n "$pid" ]; then
      kill -9 "$pid" 2>/dev/null || true
      echo "  端口 $port (pid $pid) 已停止"
    fi
  done
}

start() {
  echo "启动后端 (uvicorn :8010)..."
  cd "$ROOT/backend"
  caffeinate -is .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8010 \
    > "$BACKEND_LOG" 2>&1 &
  # 等后端就绪
  for i in $(seq 1 15); do
    if curl -s -m 2 http://127.0.0.1:8010/api/v1/health >/dev/null 2>&1; then
      echo "  后端就绪 ✓"
      break
    fi
    sleep 1
  done

  echo "启动前端 (vite :5173)..."
  cd "$ROOT/frontend"
  npm run dev > "$FRONTEND_LOG" 2>&1 &
  for i in $(seq 1 15); do
    if curl -s -m 2 http://localhost:5173/ >/dev/null 2>&1; then
      echo "  前端就绪 ✓"
      break
    fi
    sleep 1
  done

  echo ""
  echo "================ KnowPilot 已启动 ================"
  echo "  前端:   http://localhost:5173"
  echo "  后端:   http://127.0.0.1:8010/api/v1/health"
  echo "  后端日志: $BACKEND_LOG"
  echo "  前端日志: $FRONTEND_LOG"
  echo "  停止: ./start.sh stop"
  echo "==================================================="
}

status() {
  for pair in "前端:5173" "后端:8010"; do
    name="${pair%%:*}"
    port="${pair##*:}"
    if curl -s -m 2 "http://127.0.0.1:$port" >/dev/null 2>&1 \
       || curl -s -m 2 "http://localhost:$port" >/dev/null 2>&1; then
      echo "  $name (:$port) 运行中 ✓"
    else
      echo "  $name (:$port) 未运行 ✗"
    fi
  done
}

case "${1:-start}" in
  start) start ;;
  stop) stop ;;
  restart) stop; start ;;
  status) status ;;
  *) echo "用法: $0 [start|stop|restart|status]"; exit 1 ;;
esac
