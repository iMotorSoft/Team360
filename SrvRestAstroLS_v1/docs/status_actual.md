# Status actual - Team360

Objetivo: `desarrollo`

Ultima actualizacion: 2026-05-13

## Directorio de trabajo

`/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1`

## Estado general

Se dejo preparada una base inicial de arquitectura y persistencia para Team360, sin integrar todavia un backend Litestar productivo ni runtime funcional nuevo.

## Acciones realizadas

### 2026-05-13 - Probes Mercado Libre para lista de preguntas y borrador de respuesta

- Se incorporo inspeccion superficial de la lista visible de preguntas del vendedor.
- Se agrego `smoke_questions_list_inspect.py` para:
  - reutilizar sesion persistente;
  - abrir preguntas del vendedor;
  - detectar lista, filtros, empty state y muestra superficial de items;
  - guardar screenshot, storage state y reporte de inspeccion.
- Se amplio `smoke_reply_draft.py` para validar borradores de respuesta sin publicar:
  - localizar un item con accion de responder;
  - completar textarea;
  - validar estado del boton;
  - limpiar el borrador por defecto salvo `--keep-draft`.
- Se actualizaron helpers/selectores/configuracion del browser lab para soportar inspeccion de preguntas.
- Se actualizaron README y `login-flow.md` con los probes disponibles.
- No se integraron estos probes con `team360_orquestador`, AG-UI ni frontend.

### 2026-05-13 - Documento de factibilidad SAP Business One Desktop Client

- Se creo `sap_b1_desktop_automation_factibilidad.md`.
- El documento analiza la factibilidad tecnica y comercial de automatizar SAP Business One v10 Desktop Client sin depender inicialmente de:
  - certificacion SAP;
  - marketplace SAP;
  - add-on oficial;
  - acceso directo a HANA/SQL.
- Se cubrieron las opciones:
  - Service Layer;
  - DI API / SDK local;
  - RPA Desktop sobre SAP Business One Client;
  - modelo asistido por RDP;
  - fases recomendadas de evolucion;
  - riesgos, mitigaciones y arquitectura minima propuesta.
- Decision registrada en el documento:
  - salida comercial rapida con RPA Desktop asistido en sesion del usuario por RDP;
  - evolucion tecnica a VM dedicada y usuario BOT;
  - robustez profesional posterior con DI API / Service Layer;
  - no prometer autonomia total ni solucion SAP certificada al inicio.
- No se genero codigo funcional ni se tocaron backend, Astro, `team360_orquestador`, AG-UI o laboratorio browser de Mercado Libre.

### 2026-05-13 - Status locales por directorio documental

- Se agrego la convencion de `status_actual.md` local por directorio documental activo.
- Se crearon status locales en:
  - `docs/`
  - `docs/negocio/`
  - `docs/estrategia/`
  - `docs/analisis-tecnico/`
  - `docs/templates/`
  - `data/reports/`
  - `data/reports/mercadolibre/`
  - `data/reports/mercadolibre/netzaj-racing/`
  - `data/reports/snapshots/`
- Se actualizo `AGENTS.md` para que proximos agentes sepan que cada status local describe el ultimo estado de su propio directorio.
- No se tocaron archivos funcionales, backend, Astro, `team360_orquestador`, AG-UI ni laboratorio browser de Mercado Libre.

### 2026-05-13 - Orden documental no tecnico y reportes

- Se reorganizo documentacion no tecnica de Team360 en `docs/`:
  - `docs/negocio/` para contexto comercial y analisis de negocio.
  - `docs/estrategia/` para continuidad, estrategia e inventarios tecnico-negocio.
  - `docs/analisis-tecnico/` para analisis tecnico no operativo ni runtime.
- Se agruparon reportes y evidencias generadas en `data/reports/`:
  - `data/reports/mercadolibre/netzaj-racing/` para relevamientos, playbook e intents del seller NETZAJ RACING.
  - `data/reports/snapshots/` para snapshots historicos.
- Se agregaron indices `README.md` en las carpetas documentales principales.
- Se actualizaron enlaces relativos afectados por los movimientos.
- No se tocaron archivos funcionales, backend, Astro, `team360_orquestador`, AG-UI ni laboratorio browser de Mercado Libre.

### 2026-05-13 - Automatizacion browser para permisos GitHub en `iMotorSoft/concilia`

- Se uso browser automation sobre la web de GitHub para configurar el repositorio `iMotorSoft/concilia`.
- Se invito a `msamia@gmail.com`, que GitHub resolvio como usuario `@msamia`.
- La invitacion quedo pendiente de aceptacion:
  - `0 collaborators`
  - `1 invitation`
  - invitacion visible para `@msamia`
- Se creo y verifico una regla clasica de proteccion de rama para `main`.
- Configuracion verificada de la regla:
  - `Branch name pattern`: `main`
  - `Lock branch`: activo
  - `Do not allow bypassing the above settings`: desactivado
  - `Allow force pushes`: desactivado
  - `Allow deletions`: desactivado
- Efecto esperado:
  - colaboradores comunes no pueden modificar directamente `main`;
  - owner y administradores conservan bypass;
  - `@msamia` podra crear y actualizar ramas propias cuando acepte la invitacion, pero no deberia poder modificar `main`.

### 2026-05-13 - Observacion tecnica sobre diferencia entre intentos GPT-5.4 y GPT-5.5

- Intento anterior con GPT-5.4:
  - el login y la invitacion del colaborador funcionaron;
  - la UI de GitHub mostro el formulario de proteccion de rama con `main` y `Lock branch` cargados;
  - el click automatizado sobre `Create` no disparo el submit real del formulario;
  - no aparecio la navegacion de regreso a `settings/branches`;
  - por eso la regla de proteccion no quedo guardada.
- Intento posterior con GPT-5.5:
  - se diagnostico que el problema no era la configuracion elegida sino el disparo del submit en la UI automatizada;
  - primero se intento enviar el formulario por HTTP usando la sesion temporal, pero GitHub respondio `422` por proteccion anti-CSRF;
  - luego se envio el formulario desde el contexto real de la pagina con `requestSubmit()`;
  - esa variante si ejecuto el submit aceptado por GitHub y navego de vuelta a `settings/branches`;
  - despues se abrio `Edit` para verificar que la regla quedo guardada con `main` y `Lock branch` activo.
- Conclusion:
  - el fallo anterior fue operativo del flujo de browser automation contra una UI dinamica de GitHub;
  - el intento final funciono porque se uso el formulario real ya cargado por GitHub y se disparo el submit desde el contexto de la pagina, preservando las validaciones de sesion.

### 2026-05-01 - Base documental y migration inicial de Team360

- Se creo `docs/team360_multi_whatsapp_multi_llm_architecture.md`.
- Se creo `docs/team360_postgres_dev_setup.md`.
- Se creo `backend/db/migrations/001_team360_core_schema.sql`.

### Estado observado en esta etapa

- Team360 todavia no tiene backend Litestar productivo completo.
- `backend/db/team360_pgvector_catalog.sql` existe, pero esta marcado como futuro opcional y no integrado al runtime actual.
- `backend/globalVar.py` contiene configuracion basica y variables DB/OpenAI futuras opcionales.
- No se implementaron repositorios Python ni rutas nuevas.
- No se tocaron archivos funcionales.

### PostgreSQL dev propuesto

- DB local sugerida: `team360_dev`.
- Usuario dev sugerido: `team360_dev`.
- Puerto local sugerido: `54329`.
- DSN backend sugerido:

```bash
export TEAM360_DB_URL="postgresql+psycopg://team360_dev:team360_dev_password@localhost:54329/team360_dev"
```

- DSN CLI sugerido:

```bash
export TEAM360_DB_URL_PSQL="postgresql://team360_dev:team360_dev_password@localhost:54329/team360_dev"
```

### Migration inicial

Archivo:

`backend/db/migrations/001_team360_core_schema.sql`

Incluye estructura inicial para:

- workspaces
- usuarios placeholder
- eventos core
- communication providers
- WhatsApp channels
- WhatsApp numbers
- provider credentials
- webhook bindings
- routing rules
- message threads
- message events
- migracion de numeros WhatsApp
- LLM providers
- LLM credentials
- LLM model profiles
- workspace LLM settings
- automation LLM policy
- fallback policy
- usage logs
- cost estimates
- scheduled tasks
- task runs
- local runners
- runner heartbeats

## Validacion

- Se ejecuto `python3 -m py_compile` sobre los modulos Python tocados del browser lab Mercado Libre.
- `git diff --check` paso sin errores para el commit de probes Mercado Libre.
- Se verifico que `sap_b1_desktop_automation_factibilidad.md` existe en `SrvRestAstroLS_v1/docs/`.
- `git diff --check` paso sin errores para el documento SAP B1.
- Se verifico la estructura de directorios documentales activos antes de crear status locales.
- `git diff --check` paso sin errores para los cambios documentales.
- Se verifico la estructura final de `docs/` y `data/reports/`.
- Se buscaron referencias internas a documentos movidos y se actualizaron enlaces relativos relevantes.
- Se verifico en GitHub que la regla de rama existe entrando a `Settings > Branches > Edit`.
- Se verifico que el formulario editado muestra `Branch name pattern = main` y `Lock branch` activo.
- Se verifico que `msamia@gmail.com` quedo como invitacion pendiente a `@msamia`.
- `git diff --check` paso sin errores para los archivos creados.
- Se verifico que la migration contiene las tablas principales pedidas.
- No se ejecuto la migration porque `psql` no estaba disponible en el `PATH` de esta sesion.

## Pendientes recomendados

1. Levantar PostgreSQL local con Docker.
2. Aplicar `backend/db/migrations/001_team360_core_schema.sql`.
3. Definir herramienta formal de migrations.
4. Crear seed dev sin secretos reales.
5. Integrar `TEAM360_DB_URL` al backend cuando exista runtime Litestar productivo.
6. Crear repositorios Python en una fase posterior.

## Notas de seguridad

- No se grabo la password de GitHub en archivos del proyecto.
- Se uso un archivo temporal de sesion en `/tmp/team360_github_state.json` solo para diagnostico y se elimino al terminar.
- Se cerro la sesion del navegador automatizado al finalizar la tarea.
- No se hardcodearon secretos reales.
- Las credenciales de providers/LLM se modelaron como `secret_ref`.
- `backend/temp1.txt` aparece modificado en el worktree y contiene material sensible o notas internas; no fue tocado en esta etapa.
