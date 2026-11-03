# Regresión Telchi

PASS sólo para la suite local ejecutada; PARTIAL para regresión empresarial real. Se conservaron State Engine V2, capacidades y composición sin editar sus archivos.

## Corrección mínima reproducida

Tres tests fallaban antes: canónico sin alias devolvía unknown; candidato textual omitía relaciones; followup omitía evidencia en luna_context. Causa: búsqueda exacta sólo código/alias y relation_evidence limitado a exact más serialización incompleta de conversation_concepts.

resolver.py agrega término canónico bajo match alias para conservar el contrato exacto del handler; carga evidencia únicamente para IDs del catálogo autorizado, memo por versión, y la incluye en contexto conversacional. No certifica candidatos vectoriales ni cambia permisos.

Nuevo test_operational_closure.py: once casos locales, incluyendo seis fixtures contractuales y candidato vectorial con score sintético (no calibración real). Se repitió suite completa focalizada sobre el código final; tests.log conserva resultado y comando indicado en BASELINE.md.

## Garantías y límites

La suite cubre rechazo sin reparar ejecución, pending hash, candidate margin, stale reference, followup y capacidades previas con fixtures. No sustituye HTTP real, cifras reproducibles Foundation, reinicio persistente ni comportamiento del LLM upstream.

No hay tests nuevos de ventas reales, no se hardcodearon valores mayo/junio y no se modificó Foundation. La compatibilidad tiene evidencia local; el gate EXISTING_CAPABILITIES permanece PARTIAL hasta regresión auténtica.
