#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
# setup-pi.sh — Configuración inicial de la Raspberry Pi (correr UNA sola vez)
# Ejecutar desde la raíz del repo:
#   bash scripts/setup-pi.sh
# ══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

# ── Detectar la raíz del repo automáticamente ─────────────────────────────────
# Funciona sin importar dónde esté clonado el repo
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
NGINX_CONF="/etc/nginx/sites-available/depar-finder"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║   Depar Finder — Setup inicial en Pi     ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "  Directorio de la app: $APP_DIR"
echo ""

# ── 1. Dependencias del sistema ───────────────────────────────────────────────
echo "▶ [1/7] Instalando dependencias del sistema..."
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

# ── 2. Crear subcarpetas si no existen ────────────────────────────────────────
echo ""
echo "▶ [2/7] Creando estructura de carpetas..."
mkdir -p "$APP_DIR"/{logs,backups}
echo "  ✓ logs/ y backups/ listos en $APP_DIR"

# ── 3. Python virtualenv + dependencias backend ───────────────────────────────
echo ""
echo "▶ [3/7] Configurando entorno Python..."
cd "$APP_DIR"
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
.venv/bin/pip install --upgrade pip -q
.venv/bin/pip install -r requirements.txt -q
echo "  ✓ Virtualenv listo en .venv/"

# ── 4. Dependencias Node.js frontend ─────────────────────────────────────────
echo ""
echo "▶ [4/7] Instalando dependencias Node.js..."
cd "$APP_DIR/frontend"
npm ci --silent 2>/dev/null || npm install --silent
echo "  ✓ node_modules instalado"

# ── 5. Variables de entorno ───────────────────────────────────────────────────
echo ""
echo "▶ [5/7] Verificando archivos .env..."
if [ ! -f "$APP_DIR/.env" ]; then
    echo "  ⚠ ATENCIÓN: Falta el archivo $APP_DIR/.env"
    echo "    Crealo antes de ejecutar deploy.sh:"
    echo "    cp $APP_DIR/.env.example $APP_DIR/.env && nano $APP_DIR/.env"
else
    echo "  ✓ $APP_DIR/.env encontrado"
fi
if [ ! -f "$APP_DIR/frontend/.env.local" ]; then
    echo "  ⚠ ATENCIÓN: Falta $APP_DIR/frontend/.env.local"
    echo "    Crealo antes de ejecutar deploy.sh:"
    echo "    cp $APP_DIR/frontend/.env.local.example $APP_DIR/frontend/.env.local"
    echo "    Editá NEXT_PUBLIC_API_URL= con la IP de tu Pi"
else
    echo "  ✓ frontend/.env.local encontrado"
fi

# ── 6. systemd service ────────────────────────────────────────────────────────
echo ""
echo "▶ [6/7] Instalando servicio systemd..."
# Reemplazar el path en el service file con el path real del repo
VENV_PATH="$APP_DIR/.venv/bin/uvicorn"
SERVICE_TMP=$(mktemp)
sed "s|WorkingDirectory=.*|WorkingDirectory=$APP_DIR|g;
     s|EnvironmentFile=.*|EnvironmentFile=$APP_DIR/.env|g;
     s|ExecStart=.*|ExecStart=$VENV_PATH api.main:app --host 127.0.0.1 --port 8000 --workers 2 --log-level info|g" \
    "$APP_DIR/systemd/depar-backend.service" > "$SERVICE_TMP"
sudo cp "$SERVICE_TMP" /etc/systemd/system/depar-backend.service
rm -f "$SERVICE_TMP"
sudo systemctl daemon-reload
sudo systemctl enable depar-backend
echo "  ✓ Servicio depar-backend habilitado (arranca al boot)"

# ── 7. Nginx ──────────────────────────────────────────────────────────────────
echo ""
echo "▶ [7/7] Configurando Nginx..."
# Reemplazar el path del frontend en la config de nginx
NGINX_TMP=$(mktemp)
sed "s|root /home/pi/apps/depar-finder/frontend/out;|root $APP_DIR/frontend/out;|g;
     s|access_log /home/pi/apps/depar-finder/logs/|access_log $APP_DIR/logs/|g;
     s|error_log  /home/pi/apps/depar-finder/logs/|error_log  $APP_DIR/logs/|g" \
    "$APP_DIR/nginx/depar-finder" > "$NGINX_TMP"
sudo cp "$NGINX_TMP" "$NGINX_CONF"
rm -f "$NGINX_TMP"
# Deshabilitar el sitio default de nginx
sudo rm -f /etc/nginx/sites-enabled/default
if [ ! -L /etc/nginx/sites-enabled/depar-finder ]; then
    sudo ln -s "$NGINX_CONF" /etc/nginx/sites-enabled/depar-finder
fi
sudo nginx -t
sudo systemctl enable nginx
sudo systemctl reload nginx
echo "  ✓ Nginx configurado"

# ── UFW firewall ──────────────────────────────────────────────────────────────
echo ""
echo "▶ Configurando firewall UFW..."
sudo ufw allow ssh          2>/dev/null || true
sudo ufw allow 'Nginx Full' 2>/dev/null || true
sudo ufw --force enable     2>/dev/null || true
echo "  ✓ UFW activado (SSH + HTTP/HTTPS permitidos)"

# ── Fail2ban ──────────────────────────────────────────────────────────────────
sudo systemctl enable fail2ban 2>/dev/null || true
sudo systemctl start fail2ban  2>/dev/null || true
echo "  ✓ Fail2ban activo"

echo ""
echo "══════════════════════════════════════════════"
echo "  Setup inicial completado."
echo "  Repo:   $APP_DIR"
echo ""
echo "  PRÓXIMOS PASOS:"
if [ ! -f "$APP_DIR/.env" ]; then
    echo "  1. ⚠ Crear .env:"
    echo "     cp $APP_DIR/.env.example $APP_DIR/.env"
    echo "     nano $APP_DIR/.env"
fi
if [ ! -f "$APP_DIR/frontend/.env.local" ]; then
    echo "  2. ⚠ Crear frontend/.env.local:"
    echo "     cp $APP_DIR/frontend/.env.local.example $APP_DIR/frontend/.env.local"
    echo "     nano $APP_DIR/frontend/.env.local"
    echo "     (cambiar NEXT_PUBLIC_API_URL a http://IP_DE_TU_PI)"
fi
echo "  3. Ejecutar el primer deploy:"
echo "     bash $APP_DIR/scripts/deploy.sh"
echo "══════════════════════════════════════════════"


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
