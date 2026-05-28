# Auditoria RPA Kommo / Facebook / Meta Ads - Mario Castro

Objetivo: preparar una auditoria tecnica exploratoria para automatizar por browser automation la recoleccion de datos que alimentan `KPIs_CEO_Proyectos_Inmobiliarios_COMPLETO.xlsx`.

Esta carpeta no contiene la automatizacion final. Contiene probes, evidencias y documentacion para decidir factibilidad tecnica antes de construir el flujo productivo.

## Instalacion

```bash
cd automation_mario_castro
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

## Configuracion

Crear un `.env` local a partir de `.env.example`.

```bash
cp .env.example .env
```

Variables esperadas:

```bash
KOMMO_LOGIN_URL=
KOMMO_USER=
KOMMO_PASS=
FACEBOOK_USER=
FACEBOOK_PASS=
PLAYWRIGHT_HEADLESS=false
```

No versionar `.env`, cookies, storage state, screenshots con datos sensibles ni reportes descargados desde plataformas.

## Analisis del Excel

```bash
PYTHONPATH=src python -m excel.analyze_workbook
```

Genera:

- `runtime/inspect/excel_inventory.json`

## Login probes

Kommo:

```bash
PYTHONPATH=src python -m kommo.login_probe
```

Facebook:

```bash
PYTHONPATH=src python -m facebook.login_probe
```

Si aparece 2FA, captcha o verificacion manual, el script deja el navegador abierto y espera ENTER en consola. Al continuar guarda `storage_state` para reutilizar sesion en corridas siguientes.

## Inspecciones Kommo

```bash
PYTHONPATH=src python -m kommo.inspect_dashboard
PYTHONPATH=src python -m kommo.inspect_leads
PYTHONPATH=src python -m kommo.inspect_pipeline
PYTHONPATH=src python -m kommo.inspect_whatsapp
PYTHONPATH=src python -m kommo.inspect_activity_log
```

## Inspecciones Facebook / Meta

```bash
PYTHONPATH=src python -m facebook.inspect_pages
PYTHONPATH=src python -m facebook.inspect_inbox
PYTHONPATH=src python -m facebook.inspect_ads_manager
```

## Inventario consolidado

```bash
PYTHONPATH=src python -m reports.build_data_inventory
```

Genera:

- `runtime/inspect/data_inventory.json`

## Evidencias

- Screenshots: `runtime/screenshots/`
- Texto visible e inventarios: `runtime/inspect/`
- Sesiones Playwright: `runtime/storage_state/`

Los probes son conservadores: priorizan confirmar acceso, pantallas, descargas disponibles y datos visibles antes de hacer scraping de tablas.
