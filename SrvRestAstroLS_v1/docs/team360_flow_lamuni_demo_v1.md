# Team360 Flow — Demo LaMuni V1 (repetible)

Guía corta para preparar y mostrar el MVP completo de Team360 Flow a LaMuni.

El demo **no simula estados**: ejecuta los servicios reales del dominio Flow
sobre PostgreSQL real. Solo el transporte externo (envío de correos e
intérpretes de IA) es determinístico y controlado. Cada corrida crea un caso
nuevo identificado con la marca `LAMUNI-DEMO-<fecha>-<hex>`.

## 1. Servicios que deben estar activos

- PostgreSQL (`imotorsoft-postgres`, `127.0.0.1:5432`, base `team360`) con las
  migraciones Flow aplicadas (011–019).
- Backend DEV: `./backend-dev.sh` (escucha en `http://127.0.0.1:7050`).
- Frontend DEV: `./astro-dev.sh` (escucha en `http://127.0.0.1:3050`).
- LiteLLM y Milvus solo si el preflight del backend los exige; el demo Flow
  no depende de Milvus ni de una llamada de modelo real.

## 2. Preparar y lanzar la demo

Desde `SrvRestAstroLS_v1/backend`:

```bash
uv run python -m modules.flow.demo.run
```

El comando es finito y termina con un reporte con los IDs del caso:

```text
DEMO_ID=...
REQUEST_ID=...
N1_ROUTING=...
ESCALATION=...
N2_ROUTING=...
RESOLUTION=...
APPROVAL=...
FINAL_STATUS=RESOLVED
AUDIT_ID=...
DIRECTORIO_VISIBLE=True
```

Para inspeccionar un caso existente:

```bash
uv run python -m modules.flow.demo.run --status <REQUEST_ID>
```

## 3. Qué abrir en el navegador

```
http://127.0.0.1:3050/w/ws-team360-control/flow
```

En el buscador escribir:

```
LAMUNI-DEMO
```

El caso aparece automáticamente desde `GET /api/team360-flow/executive`; no
requiere registrarse en ningún frontend ni pegar el UUID.

## 4. Estados que mostrar

- **N1 asignado** → SLA de primera respuesta en `PENDING`.
- **N1 vencido** → el caso se ve como escalado (SLA `BREACHED`).
- **N2 asignado** → nivel actual N2, escalado automáticamente.
- **Pendiente de aprobación** → antes de aprobar, el caso aparece como
  `RESOLUTION_PENDING_APPROVAL` (nunca cerrado).
- **Resuelto** → tras la aprobación, el mismo request pasa a `RESOLVED` con
  `AUDIT_SNAPSHOT`, `Aprobado`, autorizador, evidencia y timeline.

## 5. Cómo verificar la auditoría

En el detalle del caso resuelto abrir **Evidencia y trazabilidad**: verás
`Request ID`, `Audit record`, `Hash de auditoría`, routings, propuesta y
aprobación. El hash es estable: consultar el caso varias veces devuelve el
mismo audit record y el mismo SHA-256.

También por CLI:

```bash
uv run python -m modules.flow.demo.run --status <REQUEST_ID>
```

## 6. Ciclo demostrado

```text
entra un reclamo
-> Flow lo clasifica (alumbrado)
-> confirma con el vecino
-> lo asigna a N1
-> controla el SLA de primera respuesta
-> escala automáticamente a N2 al vencer
-> registra la respuesta técnica del N2
-> propone resolución
-> el supervisor aprueba
-> cierra con auditoría inmutable
-> la Dirección ve exactamente qué ocurrió
```

## 7. Configuración (para mostrar sin editar)

Abrir:

```
http://127.0.0.1:3050/w/ws-team360-control/flow/configuracion
```

Muestra sector Alumbrado, niveles N1/N2/N3 con sus destinos y el nivel de
aprobación de cierre. Estos valores se leen de PostgreSQL y controlan los
próximos routings: cambiar el destino de un nivel hace que los casos futuros
se asignen al nuevo destino.

## 8. Limpieza

Los casos demo quedan visibles en el Directorio (útil para la presentación).
Para restaurar el dataset estable de la regresión E2E (borra **solo** los casos
`LAMUNI-DEMO`):

```bash
uv run python -m modules.flow.demo.run --cleanup
```

## Regla de ciclo de vida

```text
Podman lifecycle is manual. Automation must never start or restart telchi-vpn.
```

La demo de Flow no levanta ni reinicia Podman ni ningún servicio: opera sobre
el backend y la base de datos ya disponibles.
