# Regresión focalizada

El baseline de 215 PASS se conserva. Se revalidaron sólo 13 contratos locales relacionados con evidencia semántica y State Engine, sin llamadas a DB/LLM/WhatsApp ni repetir la suite completa.

## Comando y resultado

Pytest secuencial, con el entorno existente y --no-sync; no se instalaron dependencias ni se modificó lockfile.

Desde SrvRestAstroLS_v1/backend:

```bash
uv run --no-sync pytest modules/business_semantics/tests/test_operational_closure.py modules/telchi/assistant/tests/test_rejected_execution_guard.py modules/telchi/assistant/tests/test_v2_independent_query.py -q
```

[focused_tests.log](focused_tests.log): 13 passed. Cobertura: canónico exacto, evidencia provisional en candidatos/repreguntas, referencias ajenas/retiradas, contextos comerciales no promovidos, propuesta inválida sin ejecución/re-ejecución y NEW_QUERY V2 sin herencia indebida.

[tests.log previo](../business_semantics_operational_closure_v1/tests.log): 215 passed, 1 warning. No se reabrieron investigaciones L&S, calibración teórica ni las capabilities comerciales.

No se modificó código runtime ni tests del baseline. [provenance.json](provenance.json) conserva hashes al inicio de la validación y comprobación posterior. Esos hashes son de esta tarea, no una acreditación retroactiva de los inputs exactos de la corrida histórica.

State Engine PASS significa regresión local, no prueba multiusuario persistida. Capability regression PARTIAL conserva baseline local, sin nueva ejecución comercial autenticada.

## Validaciones adicionales

Los resultados finales de LAT, whitespace e integridad se registran sin convertir bloqueos operacionales en PASS.

Consultar [validation.log](validation.log) y [integrity.json](integrity.json). git diff --check y revisión final incluyen preservación de HEAD y fuentes preexistentes; se comprueba también whitespace de archivos nuevos no tracked.

Primer intento de la sonda local tuvo ruta relativa incorrecta (../../../data); falló antes de conectar. Se corrigió a ../../data con PYTHONPATH=.; no fue fallo funcional ni abort ambiental. El probe final incluye grants directos y usa la variable pública PASETO B64 correcta.
