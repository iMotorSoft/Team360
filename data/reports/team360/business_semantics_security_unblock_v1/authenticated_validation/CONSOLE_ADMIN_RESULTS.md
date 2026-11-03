# Administración Console

ADMIN_AUTH/RBAC/WRITE=BLOCKED para operación real. La CLI existente es una interfaz administrativa Console soportada, no UI ni API autenticada validada.

## Interfaz y cobertura

El runbook login emite sesión humana; Business Semantics CLI valida esa sesión y rol actual antes de administración. No se invocó ninguna mutación ni llamada PostgreSQL privilegiada como sustituto.

| Interfaz | Evidencia actual |
| --- | --- |
| CLI | Código y tests descartables previos; rol DB real confirmado; sesión U4 pendiente |
| API | No validada con sesión humana en esta tarea |
| UI Console | No probada; no login web nuevo ni validación browser |

CLI list requiere organization_admin incluso para lectura. No concederlo a usuarios estándar para facilitar MU-02.

## Pruebas pendientes

Todos los ADM quedan BLOCKED hasta sesión U4 y conceptos controlados DEV. Ningún candidato comercial L&S fue publicado ni reclasificado.

| ID | Contrato |
| --- | --- |
| ADM-01 / ADM-02 | Login admin legítimo y lectura autorizada |
| ADM-03 / ADM-04 / ADM-05 | Propuesta, nueva versión/edición y alias válido |
| ADM-06 / ADM-07 / ADM-08 | Publicar, conservar historial, retirar |
| ADM-09 / ADM-10 | Denegar fuera del tenant y sin rol |
| ADM-11 | Auditoría con sujeto autenticado |
| ADM-12 / ADM-13 | Reintento idempotente y concurrencia sin sobrescritura silenciosa |
| ADM-14 | Persistencia tras reinicio seguro propio |

## Riesgos contractuales observados

Estos riesgos requieren pruebas específicas, no cambios preventivos ni permisos amplios para lograr PASS.

propose crea versión sucesiva y no expone idempotency-key; publish sólo admite proposed, así que un reintento publicado rechaza. alias usa ON CONFLICT DO NOTHING, embed compara hash, retire repite UPDATE. No existe acción edit independiente: no afirmar ADM-04/12 sólo por nombres de CLI.

owned usa FOR UPDATE y propose serializa mediante upsert del concepto; no se observó concurrencia humana. history/list retornan sin evento audit; mutaciones insertan actor real desde sesión verificada. core_events no concede SELECT al rol runtime, y no hay acción audit CLI: MT-07 exige otra ruta administrativa soportada acreditada.
