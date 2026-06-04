# Backend Scripts

Scripts operativos y utilitarios del backend.

Si aparecen scripts de catalogo, pgvector o sync desde `v360`, deben tratarse como infraestructura futura opcional.
No forman parte del runtime central actual de Team360 ni de la prioridad principal del producto.

## automation_diagnosis

- `smoke_automation_diagnosis_litellm.py`: smoke HTTP controlado para validar que un backend ya levantado con `TEAM360_AI_PROVIDER=litellm` puede iniciar sesion, guardar 10 respuestas y clasificar usando el proxy LiteLLM real. Tambien sirve para modo combinado `TEAM360_AI_PROVIDER=litellm` + `AUTOMATION_DIAGNOSIS_REPOSITORY=postgres`; usar `--print-sql` para imprimir la query read-only de verificacion PostgreSQL por `session_id`.

Modo combinado LiteLLM + PostgreSQL:

```bash
cd backend
uv run python scripts/smoke_automation_diagnosis_litellm.py --backend-url http://127.0.0.1:8011 --timeout 120 --print-sql
```

Si PostgreSQL falla durante el snapshot, el backend debe responder HTTP 503 y el smoke imprime el cuerpo truncado del error.
