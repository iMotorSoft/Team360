# Service preflight methodology

## Proposito

Todo desarrollo, test, smoke, benchmark o prueba que dependa de servicios reales
debe empezar con un preflight obligatorio antes de interpretar resultados.

La regla evita confundir fallas de infraestructura, credenciales, provider,
credito, modelos no registrados o collections equivocadas con fallas de calidad
del modulo probado.

## Regla central

No aceptar benchmarks, smokes ni conclusiones de calidad si el preflight falla.

Si el preflight no pasa, el resultado es bloqueo de entorno/configuracion, no
evidencia tecnica del modulo bajo prueba.

## Checklist obligatorio

Antes de probar con servicios reales, validar como minimo:

1. PostgreSQL activo.
2. Milvus activo.
3. Collection Milvus correcta para el caso bajo prueba.
4. LiteLLM activo.
5. `.bashrc` / environment variables accesibles desde la shell que ejecuta la prueba.
6. `globalVar.py` importable/legible cuando el flujo usa configuracion backend.
7. Modelo registrado en LiteLLM con el alias que se va a usar.
8. Llamada real minima al modelo antes del benchmark:
   - autenticacion valida;
   - credito/cuota/provider disponible;
   - endpoint correcto para el modelo;
   - contenido no vacio cuando aplique;
   - sin fallback silencioso.

## Interpretacion de resultados

Separar siempre estas categorias:

- infraestructura no disponible;
- env vars o `globalVar.py` mal resueltos;
- Milvus sin collection/corpus/scope/version esperada;
- LiteLLM sin alias o con endpoint incorrecto;
- provider sin credito, auth invalida o acceso no autorizado;
- modelo con respuesta vacia o fallback;
- fallo de guardrail;
- bajo score semantico o baja calidad de respuesta.

Solo la ultima categoria debe usarse como evidencia de calidad del modulo.

## Evidencia minima

Una corrida valida debe dejar evidencia auditable:

- comandos o scripts usados;
- modelo/alias/provider;
- retrieval mode y collection/scope/version cuando aplique;
- PASS/WARN/FAIL/SKIP o resultado equivalente;
- latencia;
- fallback detectado o descartado;
- archivo JSON/JSONL/Markdown cuando sea una evaluacion repetible.

## Aplicacion en Team360

Esta metodologia aplica especialmente a:

- diagnosis assistant;
- knowledge/RAG/Milvus;
- LiteLLM y modelos externos;
- workers con servicios reales;
- smokes backend;
- benchmarks de calidad/latencia/costo.

Para pruebas unitarias puras sin servicios reales, el preflight externo no es
necesario; el test debe mantener fakes/mocks deterministas.
