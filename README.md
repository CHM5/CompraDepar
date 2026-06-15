# 🏠 Scraper Departamentos CABA

Sistema automatizado de búsqueda, seguimiento y scoring de departamentos en venta en Buenos Aires (CABA).  
Consulta periódicamente **Zonaprop** y **Argenprop**, detecta novedades, calcula scores, exporta a **Google Sheets** y envía alertas por **Telegram**.

---

## ✨ Features

| Función | Detalle |
|---|---|
| 🔍 Scraping | Zonaprop + Argenprop, con reintentos automáticos |
| 🏷 Scoring | Sistema configurable de puntos por barrio, disposición, metros, amenities, etc. |
| 📊 Google Sheets | Exportación automática de publicaciones relevantes (score ≥ 70) |
| 📱 Telegram | Alertas instantáneas para nuevas oportunidades y bajas de precio |
| 🗃 SQLite | Historial completo con detección de cambios de precio |
| ⚙️ GitHub Actions | Ejecución automática cada 4 horas |

---

## 📁 Estructura del proyecto

```
project/
├── config.py                   ← Parámetros de búsqueda y scoring (editar aquí)
├── main.py                     ← Orquestador principal
├── requirements.txt
├── schema.sql                  ← Esquema SQLite
├── .env.example                ← Variables de entorno de ejemplo
│
├── database/
│   ├── models.py               ← Dataclass Publicacion
│   └── db.py                   ← Operaciones SQLite (upsert, historial, etc.)
│
├── scrapers/
│   ├── base.py                 ← Clase base con helpers de parsing y HTTP
│   ├── zonaprop.py             ← Scraper Zonaprop
│   └── argenprop.py            ← Scraper Argenprop
│
├── services/
│   ├── scoring.py              ← Cálculo de score y clasificación
│   ├── analyzer.py             ← Generador automático de pros y contras
│   ├── telegram.py             ← Cliente Bot Telegram
│   └── sheets.py               ← Integración Google Sheets
│
├── data/                       ← Base de datos SQLite (auto-creado)
├── logs/                       ← Archivos de log (auto-creado)
└── .github/
    └── workflows/
        └── scraper.yml         ← GitHub Actions (cada 4 hs)
```

---

## 🚀 Setup local

### 1. Clonar y crear entorno virtual

```bash
git clone <tu-repo>
cd AutomatizacionCompraDepar
python3 -m venv .venv
source .venv/bin/activate          # Linux/macOS
.venv\Scripts\activate             # Windows
```

### 2. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 3. Configurar variables de entorno

```bash
cp .env.example .env
# Editar .env con tus credenciales reales
```

### 4. Ejecutar

```bash
python main.py
```

### 5. Levantar frontend + backend (API)

```bash
./start.sh
```

Esto detiene cualquier instancia previa y arranca:
- **Backend** (FastAPI) en `http://localhost:8000`
- **Frontend** (Next.js) en `http://localhost:3000`

Logs disponibles en `/tmp/api.log` y `/tmp/frontend.log`.

---

## 🔑 Variables de entorno

| Variable | Descripción | Requerida |
|---|---|---|
| `GOOGLE_SHEETS_ID` | ID del spreadsheet de Google (string largo en la URL) | Sí |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | JSON completo de la service account (como string) | Sí |
| `TELEGRAM_BOT_TOKEN` | Token del bot de Telegram | Opcional |
| `TELEGRAM_CHAT_ID` | ID del chat/canal de Telegram | Opcional |
| `DATABASE_PATH` | Ruta al archivo SQLite | No (default: `data/departamentos.db`) |
| `LOG_LEVEL` | Nivel de logging (`DEBUG`, `INFO`, `WARNING`) | No (default: `INFO`) |

---

## 📊 Google Sheets — Configuración

### Crear la Service Account

1. Ir a [Google Cloud Console](https://console.cloud.google.com/)
2. Crear un proyecto nuevo (o usar uno existente)
3. Activar las APIs:
   - **Google Sheets API**
   - **Google Drive API**
4. Ir a **IAM & Admin → Service Accounts → Crear**
5. Descargar el JSON de la service account
6. Compartir el spreadsheet con el email de la service account (rol: **Editor**)

### Configurar en .env

```bash
# Opción A: JSON como string (recomendado para CI/CD)
GOOGLE_SERVICE_ACCOUNT_JSON='{"type":"service_account","project_id":"..."}'

# Opción B: Ruta al archivo JSON
GOOGLE_SERVICE_ACCOUNT_FILE=/ruta/al/service-account.json
```

---

## 📱 Telegram — Configuración

1. Hablar con [@BotFather](https://t.me/BotFather) → `/newbot`
2. Copiar el token
3. Agregar el bot al canal/grupo
4. Obtener el Chat ID (usar [@userinfobot](https://t.me/userinfobot))

```bash
TELEGRAM_BOT_TOKEN=123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi
TELEGRAM_CHAT_ID=-100123456789
```

---

## ⚙️ GitHub Actions — Despliegue automático

### 1. Subir el repo a GitHub

```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/tuuser/tu-repo.git
git push -u origin main
```

### 2. Configurar Secrets en GitHub

Ir a: **Settings → Secrets and variables → Actions → New repository secret**

| Secret | Valor |
|---|---|
| `GOOGLE_SHEETS_ID` | ID del spreadsheet |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | JSON completo de la service account |
| `TELEGRAM_BOT_TOKEN` | Token del bot |
| `TELEGRAM_CHAT_ID` | Chat ID |

### 3. Activar Actions

El workflow corre automáticamente cada 4 horas.  
También se puede ejecutar manualmente desde **Actions → Scraper Departamentos CABA → Run workflow**.

---

## 🏷 Sistema de scoring

| Criterio | Puntos |
|---|---|
| Palermo | +50 |
| Belgrano | +45 |
| Villa Crespo | +40 |
| Almagro | +35 |
| Núñez | +30 |
| Saavedra | +25 |
| Caballito | +25 |
| Recoleta | +25 |
| Barrio Norte | +25 |
| Chacarita | +25 |
| Coghlan | +25 |
| Villa Urquiza | +25 |
| Colegiales | +25 |
| Disposición Frente | +20 |
| Disposición Contrafrente | +15 |
| Tiene balcón | +15 |
| ≥ 45 m² | +10 |
| Antigüedad ≤ 10 años | +10 |
| USD/m² excelente (≤ 1.800) | +10 |
| USD/m² bueno (≤ 2.200) | +5 |
| Cochera | +5 |
| Piso ≥ 5 | +5 |
| Pileta | +3 |
| SUM | +2 |
| Gimnasio | +2 |

### Clasificación

| Score | Clasificación | Acción |
|---|---|---|
| ≥ 90 | Excelente | Alerta urgente Telegram |
| 80 – 89 | Muy interesante | Alerta Telegram + Sheets |
| 70 – 79 | Revisar | Solo Sheets |
| < 70 | Ignorar | Solo base de datos |

---

## 🗃 Base de datos SQLite

### Tablas

**`publicaciones`** — tabla principal con todos los campos.  
**`historial_precios`** — registro temporal de cada cambio de precio.

### Estados

| Estado | Significado |
|---|---|
| `NUEVA` | Primera vez que aparece este ID |
| `BAJA_PRECIO` | El precio bajó respecto al registro anterior |
| `SUBA_PRECIO` | El precio subió |
| `SIN_CAMBIOS` | Sin variación de precio |
| `ELIMINADA` | Desapareció del sitio (no se borra el registro) |

### Consultas útiles

```sql
-- Top 10 por score
SELECT barrio, precio_usd, score, clasificacion, url
FROM publicaciones
WHERE estado != 'ELIMINADA'
ORDER BY score DESC LIMIT 10;

-- Historial de precios de una publicación
SELECT precio_usd, fecha_registro, estado
FROM historial_precios
WHERE id_publicacion = '12345' AND portal = 'Zonaprop';

-- Bajas de precio recientes
SELECT barrio, precio_anterior, precio_usd, variacion_porcentual, url
FROM publicaciones
WHERE estado = 'BAJA_PRECIO'
ORDER BY ultima_actualizacion DESC;
```

---

## 🛠 Ajustar selectores si el sitio cambia

Si Zonaprop o Argenprop cambian su estructura HTML:

1. Abrir el archivo del scraper correspondiente (`scrapers/zonaprop.py` o `scrapers/argenprop.py`)
2. Buscar `_CARD_SELECTORS` y actualizar los selectores CSS
3. Si cambia el JSON de Next.js, actualizar `_extract_postings_from_json()` con los nuevos paths
4. Ejecutar con `LOG_LEVEL=DEBUG` para ver qué está encontrando el scraper

---

## 📝 Cron manual (sin GitHub Actions)

```bash
# Agregar al crontab: cada 4 horas
crontab -e

# Agregar esta línea:
0 */4 * * * cd /ruta/al/proyecto && /ruta/al/.venv/bin/python main.py >> logs/cron.log 2>&1
```

---

## 🧪 Ejecución de prueba

```bash
# Modo debug para ver todo el detalle del scraping
LOG_LEVEL=DEBUG python main.py
```

---

## 📦 Dependencias

| Paquete | Uso |
|---|---|
| `requests` | HTTP + scraping |
| `beautifulsoup4` + `lxml` | Parsing HTML |
| `gspread` + `google-auth` | Google Sheets API |
| `python-dotenv` | Variables de entorno |
| `tenacity` | Reintentos (disponible para extensiones futuras) |
