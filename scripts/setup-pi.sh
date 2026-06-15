#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
# setup-pi.sh — Configuración inicial de la Raspberry Pi (correr UNA sola vez)
# Ejecutar como: bash scripts/setup-pi.sh
# ══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

APP_DIR="/home/pi/apps/depar-finder"
NGINX_CONF="/etc/nginx/sites-available/depar-finder"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║   Depar Finder — Setup inicial en Pi     ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── 1. Dependencias del sistema ───────────────────────────────────────────────
echo "▶ [1/8] Instalando dependencias del sistema..."
sudo apt-get update -qq
sudo apt-get install -y \
    nginx \
    python3-pip python3-venv \
    git curl \
    ufw fail2ban \
    2>/dev/null

# Node.js 20 LTS (si no está instalado)
if ! command -v node &>/dev/null; then
    echo "  → Instalando Node.js 20 LTS..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo apt-get install -y nodejs
fi
echo "  ✓ node $(node -v) | npm $(npm -v)"

# ── 2. Estructura de carpetas ─────────────────────────────────────────────────
echo ""
echo "▶ [2/8] Creando estructura de carpetas..."
mkdir -p "$APP_DIR"/{logs,scripts,backups}
chmod 755 "$APP_DIR"
echo "  ✓ $APP_DIR creado"

# ── 3. Clonar / actualizar repositorio ───────────────────────────────────────
echo ""
echo "▶ [3/8] Configurando repositorio..."
if [ -d "$APP_DIR/.git" ]; then
    echo "  → Repo ya existe, haciendo pull..."
    cd "$APP_DIR" && git pull
else
    echo "  → Clonando repositorio..."
    git clone https://github.com/CHM5/CompraDepar.git "$APP_DIR"
fi

# ── 4. Python virtualenv + dependencias backend ───────────────────────────────
echo ""
echo "▶ [4/8] Configurando entorno Python..."
cd "$APP_DIR"
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
.venv/bin/pip install --upgrade pip -q
.venv/bin/pip install -r requirements.txt -q
echo "  ✓ Virtualenv listo en .venv/"

# ── 5. Dependencias Node.js frontend ─────────────────────────────────────────
echo ""
echo "▶ [5/8] Instalando dependencias Node.js..."
cd "$APP_DIR/frontend"
npm ci --silent
echo "  ✓ node_modules instalado"

# ── 6. Variables de entorno ───────────────────────────────────────────────────
echo ""
echo "▶ [6/8] Verificando archivos .env..."
if [ ! -f "$APP_DIR/.env" ]; then
    echo "  ⚠ ATENCIÓN: Falta el archivo $APP_DIR/.env"
    echo "    Copiá .env.example y completá las credenciales:"
    echo "    cp $APP_DIR/.env.example $APP_DIR/.env && nano $APP_DIR/.env"
else
    echo "  ✓ $APP_DIR/.env encontrado"
fi
if [ ! -f "$APP_DIR/frontend/.env.local" ]; then
    echo "  ⚠ ATENCIÓN: Falta $APP_DIR/frontend/.env.local"
    echo "    Copiá el ejemplo: cp $APP_DIR/frontend/.env.local.example $APP_DIR/frontend/.env.local"
    echo "    Editá las variables NEXT_PUBLIC_* con tus valores Firebase"
else
    echo "  ✓ frontend/.env.local encontrado"
fi

# ── 7. systemd service ────────────────────────────────────────────────────────
echo ""
echo "▶ [7/8] Instalando servicio systemd..."
sudo cp "$APP_DIR/systemd/depar-backend.service" /etc/systemd/system/depar-backend.service
sudo systemctl daemon-reload
sudo systemctl enable depar-backend
echo "  ✓ Servicio depar-backend habilitado (arranca al boot)"

# ── 8. Nginx ──────────────────────────────────────────────────────────────────
echo ""
echo "▶ [8/8] Configurando Nginx..."
sudo cp "$APP_DIR/nginx/depar-finder" "$NGINX_CONF"
# Deshabilitar el sitio default de nginx
sudo rm -f /etc/nginx/sites-enabled/default
if [ ! -L /etc/nginx/sites-enabled/depar-finder ]; then
    sudo ln -s "$NGINX_CONF" /etc/nginx/sites-enabled/depar-finder
fi
sudo nginx -t
sudo systemctl enable nginx
sudo systemctl reload nginx
echo "  ✓ Nginx configurado"

# ── UFW firewall básico ───────────────────────────────────────────────────────
echo ""
echo "▶ Configurando firewall UFW..."
sudo ufw allow ssh     2>/dev/null || true
sudo ufw allow 'Nginx Full' 2>/dev/null || true
sudo ufw --force enable 2>/dev/null || true
echo "  ✓ UFW activado (SSH + HTTP/HTTPS permitidos)"

# ── Fail2ban ──────────────────────────────────────────────────────────────────
sudo systemctl enable fail2ban 2>/dev/null || true
sudo systemctl start fail2ban  2>/dev/null || true
echo "  ✓ Fail2ban activo"

echo ""
echo "══════════════════════════════════════════════"
echo "  Setup inicial completado."
echo ""
echo "  PRÓXIMOS PASOS:"
echo "  1. Completá el archivo .env con tus credenciales"
echo "  2. Completá frontend/.env.local con las vars Firebase"
echo "     Asegurate de tener: NEXT_PUBLIC_API_URL=http://192.168.1.43"
echo "  3. Ejecutá el primer deploy:"
echo "     bash $APP_DIR/scripts/deploy.sh"
echo ""
echo "  Después del deploy la app estará en:"
echo "  http://192.168.1.43"
echo "══════════════════════════════════════════════"
