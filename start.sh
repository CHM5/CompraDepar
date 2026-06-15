#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "🔴 Deteniendo procesos anteriores..."
pkill -f "uvicorn api.main" 2>/dev/null || true
pkill -f "next dev" 2>/dev/null || true
sleep 1

echo "🟢 Iniciando backend (puerto 8000)..."
nohup .venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8000 > /tmp/api.log 2>&1 &

echo "🟢 Iniciando frontend (puerto 3000)..."
nohup bash -c "cd frontend && npm run dev" > /tmp/frontend.log 2>&1 &

echo "⏳ Esperando..."
sleep 5

echo ""
curl -s -o /dev/null -w "  Backend:  http://localhost:8000  → %{http_code}\n" http://localhost:8000/health
curl -s -o /dev/null -w "  Frontend: http://localhost:3000  → %{http_code}\n" http://localhost:3000
echo ""
echo "✅ Listo. Logs: /tmp/api.log  /tmp/frontend.log"
