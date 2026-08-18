#!/usr/bin/env bash
#
# dev.sh — 全サービスを1コマンドで起動する開発用ランチャー
#
#   ./dev.sh                    backend + front + recognition を起動
#   ./dev.sh --no-recognition   recognition を起動しない
#   ./dev.sh --no-front         front を起動しない
#   ./dev.sh --no-backend       backend を起動しない
#   ./dev.sh --no-open          ブラウザを自動で開かない
#
# 停止は Ctrl+C。全サービスをまとめて終了します。
# ログは logs/{backend,front,recognition}.log にも保存されます。
# マイコン(ESP32カメラ)は実機側で動作するため、このスクリプトの対象外です。

set -euo pipefail
set -m  # 各サービスを独立したプロセスグループにして、まとめて停止できるようにする

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$ROOT_DIR/logs"
mkdir -p "$LOG_DIR"

# --- オプション ---------------------------------------------------------------
START_BACKEND=1
START_FRONT=1
START_RECOGNITION=1
OPEN_BROWSER=1

usage() {
  sed -n '3,15p' "$0"
}

for arg in "$@"; do
  case "$arg" in
    --no-backend)     START_BACKEND=0 ;;
    --no-front)       START_FRONT=0 ;;
    --no-recognition) START_RECOGNITION=0 ;;
    --no-open)        OPEN_BROWSER=0 ;;
    -h|--help)        usage; exit 0 ;;
    *)
      echo "不明なオプション: $arg (--help を参照)" >&2
      exit 1
      ;;
  esac
done

if [ "$START_BACKEND" -eq 0 ] && [ "$START_FRONT" -eq 0 ] && [ "$START_RECOGNITION" -eq 0 ]; then
  echo "起動するサービスがありません。" >&2
  exit 1
fi

# --- 表示 ---------------------------------------------------------------------
RESET=$'\033[0m'
C_DEV=$'\033[32m'     # green
C_BACKEND=$'\033[36m' # cyan
C_FRONT=$'\033[35m'   # magenta
C_RECOG=$'\033[33m'   # yellow

info() { printf '%s[dev]%s %s\n' "$C_DEV" "$RESET" "$*"; }
err()  { printf '%s[dev]%s %s\n' "$C_DEV" "$RESET" "$*" >&2; }

# --- 終了処理 -----------------------------------------------------------------
PGIDS=()
NAMES=()
LOGS=()
CLEANED=0

cleanup() {
  [ "$CLEANED" -eq 0 ] || return 0
  CLEANED=1
  set +m  # ジョブ通知を抑える
  info "全サービスを停止しています..."
  for pgid in "${PGIDS[@]:-}"; do
    [ -n "${pgid:-}" ] && kill -TERM -- "-$pgid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
  info "停止しました"
}

on_signal() {
  echo
  cleanup
  exit 0
}

trap on_signal INT TERM
trap cleanup EXIT

# --- 前提チェック -------------------------------------------------------------
fail=0
need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    err "コマンドが見つかりません: $1"
    fail=1
  fi
}

if [ "$START_BACKEND" -eq 1 ]; then
  need_cmd go
  if [ ! -f "$ROOT_DIR/backend/.env" ]; then
    err "backend/.env がありません: cd backend && cp .env.example .env"
    fail=1
  fi
fi
if [ "$START_FRONT" -eq 1 ]; then
  need_cmd npm
  if [ ! -d "$ROOT_DIR/front/node_modules" ]; then
    err "front/node_modules がありません: cd front && npm install"
    fail=1
  fi
fi
if [ "$START_RECOGNITION" -eq 1 ]; then
  if [ ! -x "$ROOT_DIR/recognition/.venv/bin/python" ]; then
    err "recognition/.venv がありません。recognition/README.md の Local setup を実行してください"
    fail=1
  fi
  if [ ! -f "$ROOT_DIR/recognition/.env" ]; then
    err "recognition/.env がありません: cd recognition && cp .env.example .env してカメラ設定を編集してください"
    fail=1
  fi
  if [ ! -f "$ROOT_DIR/recognition/models/pose_landmarker_full.task" ]; then
    err "recognition/models にモデルがありません: cd recognition && python scripts/download_models.py --output-dir models"
    fail=1
  fi
  # 既存の認識ワーカーが残っていると検出イベントが二重送信になるため警告する
  stale=$(pgrep -f "gesture_recognition.main" 2>/dev/null | tr '\n' ' ' || true)
  if [ -n "${stale% }" ]; then
    err "警告: 認識ワーカーがすでに起動しています (PID: ${stale% })。二重起動になる場合は kill してください"
  fi
fi
[ "$fail" -eq 0 ] || exit 1

# --- ポート確保 ---------------------------------------------------------------
free_port() {
  local port="$1"
  # ポートを占有している Docker コンテナ(他プロジェクト)があれば停止する
  if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    local names
    names=$(docker ps --filter "publish=$port" --format '{{.Names}}' 2>/dev/null || true)
    if [ -n "$names" ]; then
      info "ポート $port を使用中のコンテナを停止します: $(echo "$names" | tr '\n' ' ')"
      echo "$names" | xargs docker stop >/dev/null 2>&1 || true
    fi
  fi
  # それでも空かない場合は明示的にエラー
  local i
  for i in 1 2 3 4 5 6 7 8 9 10; do
    if ! lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  err "ポート $port が空きません。使用中のプロセス:"
  lsof -nP -iTCP:"$port" -sTCP:LISTEN >&2 || true
  exit 1
}

wait_port() {
  local port="$1" name="$2"
  local i
  for i in $(seq 1 60); do
    if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  err "$name (port $port) の起動確認がタイムアウトしました。ログ: logs/$name.log"
  exit 1
}

# --- サービス定義 -------------------------------------------------------------
cmd_backend() {
  cd "$ROOT_DIR/backend"
  set -a; . ./.env; set +a
  exec go run ./cmd/server
}

cmd_front() {
  cd "$ROOT_DIR/front"
  exec npm run dev
}

cmd_recognition() {
  cd "$ROOT_DIR/recognition"
  set -a; . ./.env; set +a
  export PYTHONUNBUFFERED=1
  exec .venv/bin/python -m gesture_recognition.main
}

# --- サービス起動 -------------------------------------------------------------
run_service() {
  local name="$1" color="$2" logfile="$3"; shift 3
  : > "$logfile"
  "$@" 2>&1 \
    | tee -a "$logfile" \
    | while IFS= read -r line; do
        printf '%s[%s]%s %s\n' "$color" "$name" "$RESET" "$line"
      done
}

start_service() {
  local name="$1" color="$2"; shift 2
  local logfile="$LOG_DIR/$name.log"
  info "起動: $name (ログ: logs/$name.log)"
  run_service "$name" "$color" "$logfile" "$@" &
  PGIDS+=("$!")
  NAMES+=("$name")
  LOGS+=("$logfile")
}

# backend -> front -> recognition の順に起動
if [ "$START_BACKEND" -eq 1 ]; then
  free_port 8080
  start_service backend "$C_BACKEND" cmd_backend
  wait_port 8080 backend
fi

if [ "$START_FRONT" -eq 1 ]; then
  free_port 5173
  start_service front "$C_FRONT" cmd_front
fi

if [ "$START_RECOGNITION" -eq 1 ]; then
  start_service recognition "$C_RECOG" cmd_recognition
fi

if [ "$START_FRONT" -eq 1 ]; then
  wait_port 5173 front
fi

# --- 起動完了 -----------------------------------------------------------------
echo
info "すべて起動しました:"
[ "$START_FRONT" -eq 1 ]  && info "  フロント:     http://localhost:5173"
[ "$START_BACKEND" -eq 1 ] && info "  バックエンド: http://127.0.0.1:8080"
if [ "$START_RECOGNITION" -eq 1 ]; then
  RECOG_INFO=$(cd "$ROOT_DIR/recognition" && set -a && . ./.env && set +a && echo "${CAMERA_ID} <- ${CAMERA_SOURCE}")
  info "  認識ワーカー: ${RECOG_INFO}"
fi
info "停止するには Ctrl+C"
echo

if [ "$OPEN_BROWSER" -eq 1 ] && [ "$START_FRONT" -eq 1 ] && command -v open >/dev/null 2>&1; then
  open "http://localhost:5173"
fi

# --- 監視ループ ---------------------------------------------------------------
# どれか1つでも異常終了したら、残りもまとめて停止する
while true; do
  for idx in "${!PGIDS[@]}"; do
    if ! kill -0 "${PGIDS[$idx]}" 2>/dev/null; then
      err "${NAMES[$idx]} が終了しました。ログ: ${LOGS[$idx]}"
      exit 1
    fi
  done
  sleep 2
done
