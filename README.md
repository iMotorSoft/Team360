# Team360

Base inicial para una solucion multicanal conversacional orientada a venta de productos.

- Foco actual:
  - canales reales
  - flujo conversacional
  - lectura de bandejas, consultas e items
  - normalizacion hacia `team360_orquestador`
  - telemetria operativa
- Nucleo: `team360_orquestador`
- Tiempo real: `AG-UI` y `SSE` como parte estructural
- Providers iniciales: `Gupshup` y `Mercado Libre`
- Canal real inicial prioritario: `Mercado Libre`
- Mercado Libre arranca con un laboratorio aislado de `browser` y `probes`
- Servicio prioritario de plataforma: asistente inteligente de venta y diagnostico de automatizacion.
- Runtime RAG/knowledge inicial para diagnostico: `ArangoDB + Milvus + LiteLLM`, reutilizando el patron probado en JudaismoenVivo.

Team360 es un proyecto separado de Vertice360.
Solo debe reutilizar de Vertice360 lo estrictamente reusable para Team360, sin quedar atado al dominio inmobiliario ni a una base derivada como camino principal.

No es prioridad actual:
- catalogo pgvector derivado de Vertice360;
- sync desde Vertice360;
- knowledge base derivada de `v360`;
- usar pgvector como RAG principal de la primera salida.

Ese trabajo puede servir mas adelante, pero hoy debe considerarse infraestructura futura opcional y no parte del runtime central inicial.

La excepcion vigente es el RAG de diagnostico de automatizacion: para acelerar salida se documenta ArangoDB + Milvus como knowledge/retrieval runtime inicial, con PostgreSQL 18 como fuente de verdad transaccional.
