# Snapshot - Team360 automation_diagnosis Fase 1

Fecha: 2026-05-28

## Clasificacion documental

Este archivo es un snapshot historico de evidencia generada para `data/reports/snapshots/`.

La documentacion tecnica viva queda en:

- `SrvRestAstroLS_v1/docs/automation_diagnosis_fase1.md`
- `SrvRestAstroLS_v1/docs/status_actual.md`

No se duplica contenido de negocio en `docs/negocio/`, porque la tarea fue implementacion tecnica de backend/runtime.

## Objetivo realizado

Se implemento la Fase 1 del modulo `automation_diagnosis` para Team360 con LiteLLM previsto como camino real, knowledge scope propio, retrieval simple, scoring/classifier deterministico, fixtures, tests y contratos preparados para multi-paquete / multi-worker.

## Principios preservados

- Team360 gobierna, decide y audita.
- LiteLLM interpreta y redacta.
- RAG aporta contexto.
- Scoring/classifier decide.
- Workers ejecutan capacidades autorizadas.
- El usuario/cliente siempre interactua con Team360.
- Los workers no se exponen directamente al cliente.

## Archivos principales

```text
SrvRestAstroLS_v1/backend/modules/automation_diagnosis/
SrvRestAstroLS_v1/backend/routes/automation_diagnosis.py
SrvRestAstroLS_v1/backend/tests/test_automation_diagnosis.py
SrvRestAstroLS_v1/docs/automation_diagnosis_fase1.md
```

## Knowledge scope inicial

```text
ks_team360_automation_diagnosis
```

Documentos iniciales:

```text
criteria_automation.md
security_limits_mfa.md
sap_b1_automation.md
browser_desktop_automation.md
commercial_packages.md
```

## Clasificaciones cubiertas

- `standard_package`
- `operational_automation`
- `consulting_required`
- `not_recommended`

## Contrato futuro preservado

```text
workspace
assistant_instance
automation_package
worker_definition
package_worker
package_worker_config
credential_reference
knowledge_scope
```

Regla:

```text
Cliente -> Team360 -> automation_package -> package_worker -> worker interno/externo
```

Nunca:

```text
Cliente -> worker directo
```

## Validacion ejecutada

```bash
python3 -m py_compile SrvRestAstroLS_v1/backend/modules/automation_diagnosis/*.py SrvRestAstroLS_v1/backend/routes/automation_diagnosis.py SrvRestAstroLS_v1/backend/tests/test_automation_diagnosis.py
cd SrvRestAstroLS_v1/backend
uv run pytest tests/test_automation_diagnosis.py
```

Resultado observado:

```text
7 passed
```

## Limites actuales

- Persistencia in-memory.
- Eventos in-memory.
- Sin GraphRAG real.
- Sin embeddings ni pgvector en runtime.
- Rutas no montadas en app Litestar productiva.
- Frontend pendiente.
- Workers externos pendientes.
- No se guardaron secretos planos.

## Archivos no tocados por decision

- `team360_orquestador`
- AG-UI/SSE
- Mercado Libre browser lab
- messaging providers
- archivos sensibles como `backend/temp1.txt`
