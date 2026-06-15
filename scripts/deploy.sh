#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
# deploy.sh — Actualiza y reinicia Depar Finder en la Raspberry Pi
# Uso:
#   git pull && bash scripts/deploy.sh
# (funciona desde cualquier ruta donde esté clonado el repo)
# ══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

# Detectar la raíz del repo automáticamente
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

# Colores
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()    { echo -e "${CYAN}▶ $*${NC}"; }
success() { echo -e "${GREEN}  ✓ $*${NC}"; }
warn()    { echo -e "${YELLOW}  ⚠ $*${NC}"; }
error()   { echo -e "${RED}  ✗ $*${NC}"; exit 1; }

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║   Depar Finder — Deploy  $TIMESTAMP  ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "  Directorio: $APP_DIR"
echo ""

cd "$APP_DIR"

# ── 1. Backup de la DB ────────────────────────────────────────────────────────
info "[1/6] Backup de la base de datos..."
if [ -f "data/departamentos.db" ]; then
    cp "data/departamentos.db" "backups/departamentos_$TIMESTAMP.db"
    # Mantener solo los últimos 7 backups
    ls -t backups/*.db 2>/dev/null | tail -n +8 | xargs rm -f 2>/dev/null || true
    success "Backup creado: backups/departamentos_$TIMESTAMP.db"
else
    warn "No existe DB todavía, saltando backup"
fi

# ── 2. Dependencias Python ────────────────────────────────────────────────────
info "[2/6] Actualizando dependencias Python..."
.venv/bin/pip install --upgrade pip -q
.venv/bin/pip install -r requirements.txt -q
success "Dependencias Python actualizadas"

# ── 3. Build del frontend ─────────────────────────────────────────────────────
info "[3/6] Build del frontend..."
cd "$APP_DIR/frontend"

# Verificar .env.local
if [ ! -f ".env.local" ]; then
    error ".env.local no encontrado. Crealo desde .env.local.example antes de deployar."
fi

# Instalar/actualizar paquetes Node
npm ci --silent 2>/dev/null || npm install --silent
success "Dependencias Node.js OK"

# Build estático
info "   Ejecutando next build..."
npm run build
success "Frontend construido en frontend/out/"

# ── 4. Actualizar configuración Nginx ─────────────────────────────────────────
cd "$APP_DIR"
info "[4/6] Actualizando config Nginx..."
# Parchear el path del repo en la config de nginx antes de copiarla
NGINX_TMP=$(mktemp)
sed "s|root /home/pi/apps/depar-finder/frontend/out;|root $APP_DIR/frontend/out;|g;
     s|access_log /home/pi/apps/depar-finder/logs/|access_log $APP_DIR/logs/|g;
     s|error_log  /home/pi/apps/depar-finder/logs/|error_log  $APP_DIR/logs/|g" \
    nginx/depar-finder > "$NGINX_TMP"
sudo cp "$NGINX_TMP" /etc/nginx/sites-available/depar-finder
rm -f "$NGINX_TMP"
# Habilitar el sitio si no está habilitado
if [ ! -L /etc/nginx/sites-enabled/depar-finder ]; then
    sudo ln -s /etc/nginx/sites-available/depar-finder /etc/nginx/sites-enabled/depar-finder
    sudo rm -f /etc/nginx/sites-enabled/default
fi
sudo nginx -t
success "Config Nginx válida"

# ── 5. Reinstalar servicio systemd + reiniciar ───────────────────────────────
info "[5/6] Reinstalando servicio systemd y reiniciando..."
# Parchear el path en el service file con el path real del repo
SERVICE_TMP=$(mktemp)
sed "s|WorkingDirectory=.*|WorkingDirectory=$APP_DIR|g;
     s|EnvironmentFile=.*|EnvironmentFile=$APP_DIR/.env|g;
     s|ExecStart=.*|ExecStart=$APP_DIR/.venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000 --workers 2 --log-level info --access-log|g" \
    "$APP_DIR/systemd/depar-backend.service" > "$SERVICE_TMP"
sudo cp "$SERVICE_TMP" /etc/systemd/system/depar-backend.service
rm -f "$SERVICE_TMP"

# Verificar que .env existe antes de arrancar
if [ ! -f "$APP_DIR/.env" ]; then
    error ".env no encontrado en $APP_DIR/.env — el backend no puede arrancar sin él."
fi

sudo systemctl daemon-reload
sudo systemctl enable depar-backend
sudo systemctl restart depar-backend || true
sleep 3
if sudo systemctl is-active --quiet depar-backend; then
    success "depar-backend corriendo"
else
    echo ""
    echo "══════════════════════════════════════════════"
    echo "  ✗ depar-backend falló al arrancar."
    echo "  Service file instalado:"
    echo "──────────────────────────────────────────────"
    cat /etc/systemd/system/depar-backend.service
    echo "──────────────────────────────────────────────"
    echo "  Últimas líneas del journal:"
    echo "──────────────────────────────────────────────"
    sudo journalctl -u depar-backend -n 40 --no-pager
    echo "══════════════════════════════════════════════"
    exit 1
fi

# Nginx
sudo systemctl reload nginx
success "Nginx recargado"

# ── 6. Validación ─────────────────────────────────────────────────────────────
info "[6/6] Validando despliegue..."
sleep 2

# Health check del backend
if curl -sf http://127.0.0.1:8000/health > /dev/null 2>&1; then
    success "API backend responde en http://127.0.0.1:8000/health"
else
    warn "Backend no responde todavía (puede tardar unos segundos)"
fi

# Frontend
if [ -f "$APP_DIR/frontend/out/index.html" ]; then
    success "Frontend estático listo en frontend/out/"
else
    error "Build falló: frontend/out/index.html no existe"
fi

# Resumen final
echo ""
echo "══════════════════════════════════════════════"
echo "  Deploy completado exitosamente."
echo ""
echo "  Servicios:"
sudo systemctl is-active depar-backend nginx 2>/dev/null | while IFS= read -r line; do
    echo "    $line"
done || true
echo ""
echo "  App disponible en:"
echo "  → http://192.168.1.43"
echo "  → API: http://192.168.1.43/api/v1/"
echo ""
echo "  Logs útiles:"
echo "  → Backend:  journalctl -u depar-backend -f"
echo "  → Nginx:    tail -f $APP_DIR/logs/nginx-access.log"
echo "══════════════════════════════════════════════"
