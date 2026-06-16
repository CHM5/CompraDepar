#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
# setup-cloudflare.sh — Instala y configura Cloudflare Tunnel en la Pi
#
# Prerrequisito: tener el dominio en Cloudflare y correr ANTES:
#   cloudflared tunnel login   (abre el navegador para autenticar)
#
# Uso:
#   bash scripts/setup-cloudflare.sh
# ══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

TUNNEL_NAME="depar-finder-api"
API_HOSTNAME="api.deparfinder.com"      # ← cambiar si tu dominio es otro
BACKEND_URL="http://localhost:8000"
CLOUDFLARED_DIR="/home/pi/.cloudflared"
SERVICE_SRC="$APP_DIR/systemd/cloudflared.service"

# Colores
GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()    { echo -e "${CYAN}▶ $*${NC}"; }
success() { echo -e "${GREEN}  ✓ $*${NC}"; }
warn()    { echo -e "${YELLOW}  ⚠ $*${NC}"; }

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   Depar Finder — Setup Cloudflare Tunnel     ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# ── 1. Instalar cloudflared ───────────────────────────────────────────────────
info "[1/6] Instalando cloudflared..."
if command -v cloudflared &>/dev/null; then
    CURRENT_VERSION=$(cloudflared --version 2>&1 | head -1)
    success "cloudflared ya instalado: $CURRENT_VERSION"
else
    ARCH=$(uname -m)
    case "$ARCH" in
        aarch64) CF_ARCH="arm64" ;;
        armv7l)  CF_ARCH="arm" ;;
        x86_64)  CF_ARCH="amd64" ;;
        *)        echo "Arquitectura no soportada: $ARCH"; exit 1 ;;
    esac
    CF_URL="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${CF_ARCH}"
    echo "  → Descargando cloudflared para $ARCH ($CF_ARCH)..."
    curl -L --progress-bar "$CF_URL" -o /tmp/cloudflared
    sudo install -m 755 /tmp/cloudflared /usr/local/bin/cloudflared
    rm -f /tmp/cloudflared
    success "cloudflared instalado: $(cloudflared --version 2>&1 | head -1)"
fi

# ── 2. Verificar autenticación ────────────────────────────────────────────────
info "[2/6] Verificando autenticación con Cloudflare..."
if [ -f "$CLOUDFLARED_DIR/cert.pem" ]; then
    success "cert.pem encontrado — ya autenticado"
else
    echo ""
    warn "No se encontró autenticación. Corriendo 'cloudflared tunnel login'..."
    echo "  → Se va a abrir una URL. Copiala en tu navegador y autorizá la Pi."
    echo "  (Si estás por SSH, copiá la URL y abrila en tu computadora)"
    echo ""
    cloudflared tunnel login
    success "Autenticado correctamente"
fi

# ── 3. Crear o reusar el túnel ────────────────────────────────────────────────
info "[3/6] Configurando túnel '$TUNNEL_NAME'..."
mkdir -p "$CLOUDFLARED_DIR"

# Verificar si el túnel ya existe
EXISTING=$(cloudflared tunnel list 2>/dev/null | grep "$TUNNEL_NAME" | awk '{print $1}' || true)
if [ -n "$EXISTING" ]; then
    TUNNEL_ID="$EXISTING"
    success "Túnel existente encontrado: $TUNNEL_ID"
else
    echo "  → Creando túnel nuevo..."
    cloudflared tunnel create "$TUNNEL_NAME"
    TUNNEL_ID=$(cloudflared tunnel list 2>/dev/null | grep "$TUNNEL_NAME" | awk '{print $1}')
    success "Túnel creado: $TUNNEL_ID"
fi

echo "  Tunnel ID: $TUNNEL_ID"

# ── 4. Generar config.yml ─────────────────────────────────────────────────────
info "[4/6] Generando ~/.cloudflared/config.yml..."
cat > "$CLOUDFLARED_DIR/config.yml" <<EOF
tunnel: ${TUNNEL_ID}
credentials-file: ${CLOUDFLARED_DIR}/${TUNNEL_ID}.json

ingress:
  - hostname: ${API_HOSTNAME}
    service: ${BACKEND_URL}

  - service: http_status:404
EOF
success "config.yml generado en $CLOUDFLARED_DIR/config.yml"

# ── 5. Crear registro DNS en Cloudflare ───────────────────────────────────────
info "[5/6] Creando registro DNS: $API_HOSTNAME → túnel..."
if cloudflared tunnel route dns "$TUNNEL_NAME" "$API_HOSTNAME" 2>&1; then
    success "DNS creado: $API_HOSTNAME apunta al túnel"
else
    warn "DNS ya existe o hubo un error (puede ser normal si ya estaba creado)"
fi

# ── 6. Instalar servicio systemd ──────────────────────────────────────────────
info "[6/6] Instalando servicio systemd..."
sudo cp "$SERVICE_SRC" /etc/systemd/system/cloudflared.service
sudo systemctl daemon-reload
sudo systemctl enable cloudflared
sudo systemctl restart cloudflared
sleep 3

if sudo systemctl is-active --quiet cloudflared; then
    success "Servicio cloudflared activo y corriendo"
else
    echo ""
    warn "El servicio no arrancó. Logs:"
    sudo journalctl -u cloudflared -n 20 --no-pager || true
    exit 1
fi

# ── Resumen ───────────────────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════════════════"
echo "  Cloudflare Tunnel configurado exitosamente."
echo ""
echo "  Tunnel ID:  $TUNNEL_ID"
echo "  Hostname:   https://$API_HOSTNAME"
echo "  Backend:    $BACKEND_URL"
echo ""
echo "  PRÓXIMOS PASOS:"
echo "  1. Verificar que el túnel funciona:"
echo "     curl https://$API_HOSTNAME/health"
echo ""
echo "  2. Configurar el GitHub Secret:"
echo "     Settings → Secrets → NEXT_PUBLIC_API_URL"
echo "     Valor: https://$API_HOSTNAME"
echo ""
echo "  3. Hacer push a main para que GitHub Actions rebuilde"
echo "     el frontend con la nueva URL de la API."
echo ""
echo "  4. Agregar tu dominio a Firebase Console:"
echo "     Authentication → Settings → Authorized domains"
echo "     → Agregar: $API_HOSTNAME (si usás el mismo dominio para el front)"
echo "══════════════════════════════════════════════════════════"
