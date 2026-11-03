# Universo operativo V2 offline

Investigación Telchi de ventas, producción y recetas sobre fuentes locales. No contiene transporte HANA ni habilita ejecución SAP. Autoridad: [CONTEXT](../../../CONTEXT.md).

## Reproducción

Desde backend, elegir un destino nuevo bajo `data/reports/telchi/` del repositorio. El analizador rechaza otros roots y destinos existentes.

```bash
uv run python -m modules.telchi.investigation.validation.operational_universe_v2.analyze ../../data/reports/telchi/operational-universe-v2-new-run
uv run pytest --import-mode=importlib modules/telchi/investigation/validation/operational_universe_v2/test_universe.py -q
```

El test de evidencia real apunta al reporte acreditado `data/reports/telchi/operational-universe-v2-20261029-final/`. El analizador V1 existente se reutiliza sin modificaciones para reacreditar actividad y captura física.

## Semántica

La unión usa ItemCode exacto y pertenencias independientes. La BOM productiva requiere OITT.TreeType=P y componentes ITT1.Type=4; los demás registros se conservan como evidencia excluida.

- Sin categorías de ingredientes inventadas, normalización de identidad ni inferencias de estado físico.
- Vigencia de recetas desconocida; fechas de creación y actualización no son fechas efectivas.
- El grafo conserva aristas y todos los caminos simples; registra ciclos y detiene su expansión. Exceder el presupuesto de caminos falla sin producir un universo parcial presentado como completo.
- No se usa `expand_bom` para descubrir identidades: esa función calcula factores y filtra UoM desconocidas, algo que perdería componentes válidos para este análisis topológico.
- OIGN/IGN1 ausentes implican cobertura pendiente, no inexistencia de recepciones.

## Contrato selectivo preparado

`selective.py` implementa un ledger offline separado del keyset. Solo acepta destinos privados aislados; las operaciones requieren el lock de directorio existente durante toda la transacción.

1. Congelar plan ordenado, parámetros y SHA-256; crear destino nuevo y checkpoint independiente.
2. Persistir `reserve_request` antes del futuro SELECT. Un intent sin respuesta confirmada bloquea cualquier reserva/reintento automático y exige revisión offline explícita.
3. Solo una lectura terminada permite `commit_response`. Verificar columnas, orden, duplicados, claves inesperadas y correspondencia exacta; registrar faltantes como NOT_RETURNED, no como NULL ni como eliminados.
4. Persistir journal con respuesta completa antes del batch y checkpoint; fsync de archivo y directorio. Recuperar offline y verificar hashes antes de continuar.
5. Repetir recuperación no cambia el estado. Un batch con todas sus claves faltantes avanza por índice solicitado, nunca por última clave recibida.
6. Temporales no resueltos, corrupción o conflictos bloquean continuación; no se borran evidencias para forzar avance.

El scheduler puro prepara pausas de 10 s entre consultas y 30 s entre bloques, hasta 25 claves/SELECT y 5 SELECT/bloque, y reserva cooperativa de cierre. No ejecuta consultas ni demuestra cierre de recursos HANA.

## Gate futuro obligatorio

La autorización de esta tarea termina antes de SAP. Un futuro runner requiere autorización nueva y pruebas de integración de los controles que dependen del transporte y del dispositivo destino.

- Una conexión, sin paralelismo ni reintentos automáticos.
- Latencia HANA máxima 1,5 s y persistencia durable máxima 10 s; permitir terminar fsync en curso y detener la siguiente consulta ante exceso.
- Deadline cooperativo con reserva de cierre/recuperación; verificar cursor y conexión cerrados en toda salida.
- Guard específico de persistencia reutilizado del capturador existente; iowait global no demuestra por sí solo presión HANA.
- Nunca pasar este plan al runner keyset ni reutilizar capturas anteriores como destino.
