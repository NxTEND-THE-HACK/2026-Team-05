#!/usr/bin/env bash
#
# setup.sh — 開発環境の初回セットアップ
#
#   ./setup.sh
#
# Go / Node.js / Python 本体は事前にインストールしてください。
# このスクリプトはリポジトリ内の依存関係、仮想環境、設定ファイル、
# MediaPipeモデルを準備します。既存の .env は上書きしません。

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONT_DIR="$ROOT_DIR/front"
RECOGNITION_DIR="$ROOT_DIR/recognition"
PYTHON_BIN=""

info() {
  printf '[setup] %s\n' "$*"
}

err() {
  printf '[setup] %s\n' "$*" >&2
}

usage() {
  sed -n '3,9p' "$0"
}

if [ "$#" -gt 0 ]; then
  case "$1" in
    -h|--help) usage; exit 0 ;;
    *)
      err "不明なオプション: $1 (--help を参照)"
      exit 1
      ;;
  esac
fi

copy_if_missing() {
  local target="$1" template="$2"
  if [ -f "$target" ]; then
    info "既存の設定を保持: ${target#$ROOT_DIR/}"
    return
  fi
  cp "$template" "$target"
  info "設定ファイルを作成: ${target#$ROOT_DIR/}"
}

missing=0
for command_name in go node npm python3; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    err "コマンドが見つかりません: $command_name"
    missing=1
  fi
done

if [ "$missing" -ne 0 ]; then
  err "Go / Node.js / Python 3.11以降をインストールしてから再実行してください"
  err "macOSの場合の例: brew install go node python@3.11"
  exit 1
fi

PYTHON_BIN="$(command -v python3)"
if ! "$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
  err "Python 3.11以降が必要です"
  exit 1
fi

info "backendの設定とGo依存関係を準備しています"
copy_if_missing "$BACKEND_DIR/.env" "$BACKEND_DIR/.env.example"
(cd "$BACKEND_DIR" && go mod download)

info "frontのNode.js依存関係を準備しています"
(cd "$FRONT_DIR" && npm install --no-audit --no-fund)

info "recognitionのPython環境を準備しています"
if [ ! -x "$RECOGNITION_DIR/.venv/bin/python" ]; then
  "$PYTHON_BIN" -m venv "$RECOGNITION_DIR/.venv"
  info "Python仮想環境を作成: recognition/.venv"
else
  info "既存のPython仮想環境を保持: recognition/.venv"
fi

copy_if_missing "$RECOGNITION_DIR/.env" "$RECOGNITION_DIR/.env.example"
(cd "$RECOGNITION_DIR" && .venv/bin/python -m pip install -e '.[dev]')

info "MediaPipeモデルを準備しています"
(cd "$RECOGNITION_DIR" && .venv/bin/python scripts/download_models.py --output-dir models)

info "セットアップが完了しました"
info "起動するには ./dev.sh を実行してください"
