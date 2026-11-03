# Regresión State Engine

STATE_ENGINE_REGRESSION=PASS exclusivamente para contrato determinista; aislamiento/persistencia con personas reales sigue BLOCKED. No se reconstruyeron tests ni alteró runtime.

## Validación focalizada

Se ejecutaron guards baratos que conectan semántica/evidencia con ejecución y contratos comerciales. Resultado conjunto: 28 passed en 0.45s, sin skip; [focused_tests.log](focused_tests.log).

Desde backend:

```bash
uv run --no-sync pytest modules/business_semantics/tests/test_operational_closure.py modules/business_semantics/tests/test_regression.py modules/telchi/assistant/tests/test_rejected_execution_guard.py modules/telchi/assistant/tests/test_sales_business_contract.py -q
```

Cobertura nueva ejecutada: nombre canónico sin alias, candidato textual/vectorial con evidencia provisional, repregunta/evidencia deduplicada, referencias ajenas o retiradas sin lectura, concepto conocido sin capability, nueva consulta libera referencia, resolver deshabilitado/stale no ejecuta plan previo, raw EXECUTE rechazado no ejecuta, grant específico fail-closed.

## Evidencia conservada

[provenance.json](provenance.json) confirma hashes de engine, handler, composition, conversation repository y tests sin cambios respecto al cierre anterior. Único cambio de esa lista: CLI, ya autorizado y probado en auth_window.

Reutilizamos tests originales de período/producto/contexto/nueva conversación/ASK/BLOCK/autorización y [auth_window/GATES.md](../auth_window/GATES.md) 221 PASS/1 skip. No se repitió toda la batería ni se usó este PASS para certificar usuarios sintéticos como personas reales.

MU-03/04/05 y MT-10/11 siguen pendientes: owner guard inspeccionado y tests locales no son persistencia/concurrencia/reinicio efectivo de U1/U2/U3. Ningún servicio fue iniciado o reiniciado.
