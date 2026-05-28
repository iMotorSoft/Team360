# Status actual - Auditoria RPA Mario Castro

Objetivo: `auditoria-tecnica-browser`

Ultima actualizacion: 2026-05-20

## Estado general

Se creo una base exploratoria para auditar la factibilidad de extraer KPIs desde Kommo, Facebook Page/Inbox y Meta Ads Manager usando Playwright en Python, sin APIs y sin guardar credenciales reales.

## Acciones realizadas

### 2026-05-20 - Base de laboratorio RPA y analisis inicial de Excel

- Se preparo la estructura `automation_mario_castro/`.
- Se agregaron probes de login e inspeccion para Kommo.
- Se agregaron probes de login e inspeccion para Facebook Pages, Inbox y Ads Manager.
- Se agrego helper reutilizable de Playwright con storage state, screenshots, timeouts largos y pausa HITL para 2FA/captcha.
- Se analizo la estructura del Excel `KPIs_CEO_Proyectos_Inmobiliarios_COMPLETO.xlsx`.
- Se documento una matriz inicial KPI -> fuente probable.
- No se guardaron credenciales reales.
- No se construyo todavia la automatizacion final de generacion del Excel.


### 2026-05-20 - Evidencia manual Kommo Dashboard, Inbox y Registro de actividades

- Se documentaron capturas manuales de Kommo Dashboard, Inbox/Chats y `Analitica > Registro de actividades`.
- Se confirmo que Dashboard muestra rango mensual, pipeline, usuario, leads por usuario, fuentes y widgets de tareas.
- Se confirmo que Inbox muestra chats abiertos, total, canal por icono, contacto, ID, preview y hora.
- Se confirmo que Registro de actividades muestra tabla estructurada con fecha, usuario, objeto, nombre, actividad, valor previo y valor posterior.
- Se actualizo la factibilidad: Registro de actividades pasa a ser fuente candidata primaria para eventos historicos de Kommo.
- Se agrego `src/kommo/inspect_activity_log.py` para probar la pantalla y guardar texto/filas visibles como evidencia.
- No se guardaron screenshots reales ni credenciales en el repo.

## Validacion

- Pendiente ejecutar probes contra Kommo/Facebook con `.env` local.
- Pendiente ejecutar `kommo.inspect_activity_log` para confirmar filtro/export/paginacion del registro.
- Playwright no esta instalado en el entorno Python actual; instalar dependencias antes de ejecutar probes.
- Pendiente confirmar permisos reales y disponibilidad de descargas desde las pantallas.

## Pendientes recomendados

1. Ejecutar `kommo.login_probe` con intervencion humana si aparece 2FA.
2. Ejecutar inspecciones Kommo y revisar `runtime/inspect/`.
3. Ejecutar `facebook.login_probe` y confirmar permisos sobre las paginas.
4. Ejecutar inspeccion de Ads Manager y priorizar descarga CSV/XLSX.
5. Ajustar selectores con evidencia real antes de productivizar.

## Notas de seguridad

- Las credenciales reales deben vivir solo en `.env` local o variables de entorno.
- `runtime/storage_state/` puede contener cookies y no debe subirse.
- `runtime/screenshots/` puede contener datos personales o comerciales y no debe subirse sin revision.
