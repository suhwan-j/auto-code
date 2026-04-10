#!/bin/bash
# ─────────────────────────────────────────────
# Totoro Docker 빌드 & 실행 스크립트
# ─────────────────────────────────────────────
set -e

# 프로젝트 루트에서 실행 확인
if [ ! -f "docker-compose.yml" ]; then
    echo "[ERROR] docker-compose.yml not found."
    echo "        Run this script from the project root directory."
    exit 1
fi

echo "══════════════════════════════════════════"
echo "  Totoro Docker Build & Run"
echo "══════════════════════════════════════════"
echo ""

echo "[1/2] Building image..."
docker compose build

echo ""
echo "[2/2] Starting container..."
echo ""
docker compose run --rm totoro
