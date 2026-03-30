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

Team360 es un proyecto separado de Vertice360.
Solo debe reutilizar de Vertice360 lo estrictamente reusable para Team360, sin quedar atado al dominio inmobiliario ni a una base derivada como camino principal.

No es prioridad actual:
- catalogo pgvector
- retrieval / RAG
- embeddings
- sync desde Vertice360
- knowledge base derivada de `v360`

Ese trabajo puede servir mas adelante, pero hoy debe considerarse infraestructura futura opcional y no parte del runtime central del proyecto.
