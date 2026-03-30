# Future Optional: pgvector / v360 Catalog Sync

Estado:
- clasificado como futuro opcional
- no integrado al runtime actual
- no prioritario para la secuencia actual del producto

Que se hizo:
- se preparo un esquema SQL para catalogo documental, chunks y telemetry orientada a retrieval/AI turns
- se agrego un script para sync desde `v360` hacia una DB separada de Team360
- se dejo soporte para embeddings opcionales cuando exista una key de OpenAI

Por que no es prioridad actual:
- Team360 hoy esta enfocado en venta de productos por canales reales
- el camino principal actual es:
  1. canales reales
  2. flujo conversacional
  3. lectura de bandejas / seller questions / items
  4. normalizacion al orquestador
  5. telemetria operativa
- catalogo pgvector, retrieval, embeddings y sync desde Vertice360 quedan despues de eso

Que no debe asumirse hoy:
- que Team360 depende de `v360`
- que el runtime conversacional actual usa retrieval o RAG
- que el dominio inmobiliario de Vertice360 define el dominio central de Team360

Como retomarlo mas adelante:
- revisar `backend/db/team360_pgvector_catalog.sql`
- revisar `backend/scripts/sync_v360_catalog_to_team360.py`
- definir primero el caso real de uso en Team360 para catalogo/retrieval
- integrar esa capa recien cuando el camino principal conversacional y los canales reales ya esten estables
