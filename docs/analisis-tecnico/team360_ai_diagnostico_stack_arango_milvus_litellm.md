# Team360 AI Diagnostico: stack ArangoDB + Milvus + LiteLLM

Fecha: 2026-06-04

## Objetivo

Definir la factibilidad tecnica de acelerar el servicio de Team360 para:

- asistente inteligente de venta;
- diagnostico de automatizacion;
- descubrimiento guiado de procesos automatizables;
- recomendacion de paquetes, workers y alcances posibles;
- experiencia progresiva con AG-UI y SSE.

La decision practica es reutilizar el patron ya probado en JudaismoenVivo para RAG/knowledge:

```text
ArangoDB + Milvus + LiteLLM
```

Esto prioriza velocidad de salida y reduce riesgo de implementacion inicial.

## Factibilidad

La arquitectura es factible para Team360.

Motivos:

- El patron ArangoDB + Milvus ya fue validado en JudaismoenVivo para asistentes RAG con documentos, jerarquias y busqueda semantica.
- Team360 ya tiene PostgreSQL 18 como core transaccional y no necesita que el RAG inicial viva dentro de PostgreSQL.
- LiteLLM ya esta definido en Team360 como gateway AI por adapter boundary.
- AG-UI/SSE encaja naturalmente con diagnosticos por etapas: intake, clasificacion, scoring, recomendaciones y propuesta.
- El diagnostico de automatizacion se beneficia de grafo: procesos, sistemas, riesgos, dependencias, paquetes, workers, acciones bloqueadas y condiciones HITL.

## Stack objetivo

```text
Frontend / consola
  Astro
  Svelte 5 con Runes
  Tailwind CSS 4
  DaisyUI 5
  AG-UI
  SSE

Backend / runtime
  Litestar
  team360_orquestador
  modules/automation_diagnosis
  modules/db con psycopg 3 async

Core transaccional
  PostgreSQL 18

Knowledge / grafo operacional
  ArangoDB

Vectores / similitud semantica
  Milvus

Gateway AI
  LiteLLM
    -> OpenAI
    -> OpenRouter
    -> otros proveedores futuros
```

## Primeras salidas comerciales

El primer objetivo no es un chatbot generico. Es un asistente inteligente de venta y diagnostico que debe salir en dos canales:

```text
Team360 directo
  -> sitio de Team360
  -> lead owner: Team360
  -> assistant_instance: team360_sales_diagnosis

Mamá Mía 360
  -> sitio de Mamá Mía 360
  -> distribuidor / partner regional en Israel
  -> lead owner: Mamá Mía 360
  -> assistant_instance: mamamia360_sales_diagnosis
  -> idiomas: español, ingles, hebreo
```

Ambos canales deben compartir el mismo motor tecnico de diagnostico, retrieval, scoring y render AG-UI/SSE. La diferencia debe estar en configuracion: organizacion, workspace, canal web, marca, mercado, idioma, catalogo visible, paquetes habilitados, knowledge scope, ownership del lead y atribucion de costos.

Mamá Mía 360 no debe hardcodearse como producto separado. Debe operar como el primer caso real de distribuidor regional sobre Team360.

## Team360 como primer cliente directo

El asistente de venta y diagnostico de Team360 no debe construirse como demo interna.

Debe modelarse como la primera instalacion real de un paquete vendido por Team360:

```text
cliente / organizacion: Team360
workspace: team360_public_site
paquete: pkg_sales_diagnosis
assistant_instance: team360_sales_diagnosis
knowledge_scope: ks_team360_sales_diagnosis
lead_owner: Team360
site_channel: team360.live
```

Esto obliga a que el primer caso ya valide la logica comercial y tecnica completa:

- paquete contratado o activado;
- assistant instance configurable;
- workers vinculados por `package_worker`;
- knowledge scope propio;
- ArangoDB/Milvus con filtros obligatorios por scope;
- leads y diagnosticos finales persistidos en PostgreSQL;
- eventos, auditoria y atribucion de costos;
- AG-UI/SSE renderizado desde salida semantica.

Los workers no se venden ni exponen por separado. El cliente compra el servicio visible:

```text
Asistente de venta y diagnostico
```

Internamente el paquete puede vincular:

```text
guided_intake_worker
lead_qualification_worker
knowledge_retrieval_worker
diagnosis_scoring_worker
package_recommendation_worker
proposal_outline_worker
crm_handoff_worker
calendar_handoff_worker
agui_render_worker
```

No debe existir branching tipo `if Team360`. El runtime debe resolver la misma configuracion de paquete/asistente que luego usaran Mamá Mía 360 y otros clientes.

## Separacion de responsabilidades

### PostgreSQL 18

PostgreSQL sigue siendo la fuente de verdad transaccional.

Debe guardar:

- organizaciones;
- workspaces;
- usuarios;
- permisos;
- paquetes contratados;
- package workers;
- diagnosticos;
- eventos;
- auditoria;
- consumo;
- billing interno;
- estado operativo visible en consola.

PostgreSQL no se elimina ni pierde prioridad. La decision solo afecta la capa RAG/knowledge inicial.

### ArangoDB

ArangoDB se propone como knowledge graph operativo para diagnostico.

Puede guardar y relacionar:

- industrias;
- tipos de cliente: profesional, pyme, empresa;
- sistemas usados por el cliente;
- procesos;
- dolores operativos;
- automatizaciones posibles;
- automatizaciones no recomendadas;
- paquetes Team360;
- workers;
- integraciones requeridas;
- riesgos;
- MFA/HITL;
- casos similares;
- playbooks de venta y diagnostico.

Ejemplo conceptual:

```text
cliente_tipo -> proceso -> dolor -> automatizacion_candidata
automatizacion_candidata -> package_worker
automatizacion_candidata -> riesgo
riesgo -> hitl_mode
package_worker -> credencial_requerida
```

Decision inicial de scoping:

- No crear una coleccion fisica por cliente como default.
- Usar colecciones compartidas por dominio con campos obligatorios de scope.
- Crear grafo logico por `knowledge_scope` o `assistant_instance` cuando haga falta aislar recorridos.
- Reservar colecciones/base fisicamente separadas para enterprise, compliance, volumen alto o contrato dedicado.

Colecciones iniciales recomendadas:

```text
diagnosis_vertices
diagnosis_edges
diagnosis_documents
diagnosis_playbooks
```

Campos obligatorios:

```text
organization_id
workspace_id
assistant_instance_id
knowledge_scope_id
document_type
source_kind
version
status
```

### Milvus

Milvus se propone como indice vectorial inicial para busqueda semantica.

Puede indexar:

- documentos de diagnostico;
- playbooks;
- preguntas frecuentes;
- casos previos;
- fragmentos de procesos;
- catalogo de automatizaciones;
- propuestas tipo;
- knowledge chunks derivados desde ArangoDB o archivos.

Milvus no guarda la verdad de negocio. Guarda embeddings y metadata necesaria para recuperar contexto.

Milvus debe usar filtros obligatorios por scope. La coleccion puede ser compartida o particionada, pero retrieval no puede mezclar clientes por accidente.

Metadata minima:

```text
organization_id
workspace_id
assistant_instance_id
knowledge_scope_id
document_id
chunk_id
source_kind
version
status
```

El primer scope directo de Team360 es:

```text
ks_team360_sales_diagnosis
```

### LiteLLM

LiteLLM debe ser el gateway AI de Team360.

Uso recomendado:

```text
Team360 backend
  -> AIInterpreterPort / AIModelGatewayPort
      -> LiteLLM
          -> OpenAI
          -> OpenRouter
          -> otros
```

No se recomienda que cada modulo llame directamente a OpenAI/OpenRouter.

LiteLLM permite:

- aliases de modelo;
- cambio de proveedor sin tocar dominio;
- tracking de costo;
- budgets;
- rate limits;
- fallback;
- observabilidad por metadata.

Cada request AI debe llevar metadata Team360:

```json
{
  "organization_id": "...",
  "workspace_id": "...",
  "assistant_instance_id": "...",
  "automation_package_id": "...",
  "package_worker_id": "...",
  "session_id": "...",
  "correlation_id": "...",
  "feature": "automation_diagnosis",
  "phase": "intake|scoring|recommendation|proposal",
  "model_alias": "automation_diagnosis_text"
}
```

LiteLLM mide. Team360 decide, audita y factura.

## pgvector

Team360 ya tiene la migracion:

```text
003_team360_pgvector_knowledge_embeddings.sql
```

Esa capacidad queda disponible, pero no sera el RAG principal de la primera salida.

Decision:

```text
pgvector instalado/disponible != runtime RAG principal inicial
```

Motivo:

- ArangoDB + Milvus acelera la salida por reutilizar experiencia probada.
- Milvus esta especializado para busqueda vectorial.
- ArangoDB permite modelar relaciones de diagnostico con mayor naturalidad.
- PostgreSQL se mantiene limpio como core transaccional y de auditoria.

pgvector queda como:

- capacidad instalada;
- fallback futuro;
- opcion para knowledge scopes chicos o internos;
- posible consolidacion futura si el costo operativo de Milvus/ArangoDB no se justifica.

## Diagnostico de automatizacion

El diagnostico debe descubrir:

- que quiere automatizar el cliente;
- que sistemas usa;
- que volumen opera;
- que datos existen;
- que accesos requiere;
- que tareas son repetitivas;
- que acciones son riesgosas;
- que puede automatizarse ahora;
- que requiere HITL;
- que no conviene vender todavia;
- que paquete Team360 aplica.

Salida esperada:

```text
diagnosis_summary
automation_candidates
not_recommended_items
required_integrations
risk_flags
hitl_requirements
commercial_fit
suggested_packages
next_questions
proposal_outline
```

El modelo no debe devolver HTML como contrato principal.

Debe devolver estructura semantica y Team360 debe renderizar AG-UI:

- cards;
- formularios;
- tablas;
- timelines;
- alertas;
- scores;
- recomendaciones;
- comparativas.

## Modelos

Resultado preliminar desde pruebas en JudaismoenVivo:

- `qwen/qwen3-30b-a3b-thinking-2507`: mejor candidato para diagnostico consultivo enriquecido y estructura visual/semantica consistente.
- `gpt-4o-mini-2024-07-18`: fallback OpenAI estable.
- `deepseek/deepseek-v4-flash`: bueno para analisis profundo/offline, pero no como default interactivo si mantiene riesgos de latencia/formato.
- `gpt-4.1-nano-2025-04-14`: util para clasificacion barata, extraccion y scoring simple mientras siga disponible; no como cerebro principal.

En Team360 deben usarse aliases, no slugs hardcodeados:

```text
automation_diagnosis_text
automation_diagnosis_classifier
automation_diagnosis_recommender
sales_assistant_text
cheap_classifier
```

## Riesgos

- Nueva complejidad operativa: PostgreSQL + ArangoDB + Milvus + LiteLLM.
- Necesidad de monitorear consistencia entre PostgreSQL, ArangoDB y Milvus.
- Necesidad de jobs de sync/reindex.
- Necesidad de reglas claras de ownership de datos.
- Costo de operar mas servicios.
- Seguridad: no exponer credenciales ni secretos en knowledge stores.
- Riesgo de sobreprometer automatizaciones bloqueadas por MFA, hardware keys, politicas anti-bot o acciones financieras.

## Mitigaciones

- PostgreSQL mantiene la verdad transaccional.
- ArangoDB/Milvus se tratan como capas derivadas o especializadas.
- Todo diagnostico final se persiste en PostgreSQL.
- Cada llamada AI lleva `correlation_id`.
- Cada recomendacion queda auditable.
- HITL/MFA se clasifica explicitamente.
- LiteLLM centraliza uso y costos.
- Team360 decide con scoring deterministico; el LLM interpreta y redacta.

## Decision recomendada

Para acelerar la primera salida de Team360:

```text
Usar ArangoDB + Milvus como runtime RAG/knowledge inicial.
Mantener PostgreSQL 18 como core transaccional y auditoria.
Mantener pgvector como capacidad instalada/futura, no como RAG principal inicial.
Usar LiteLLM como gateway AI obligatorio.
Renderizar diagnosticos con AG-UI/SSE desde estructura semantica, no HTML generado por modelo.
```

## Proximos pasos sugeridos

1. Definir el modelo de paquete instalado para `team360_sales_diagnosis` como primer cliente directo.
2. Definir `assistant_instance`, package workers y `knowledge_scope` para Team360 directo.
3. Definir el schema inicial de ArangoDB para diagnostico con scoping por organizacion/workspace/assistant/scope.
4. Definir colecciones Milvus y metadata minima con filtros obligatorios por `knowledge_scope_id`.
5. Definir aliases LiteLLM de diagnostico.
6. Crear un lab aislado de `automation_diagnosis` con ArangoDB + Milvus.
7. Persistir resultado final del diagnostico en PostgreSQL con atribucion de canal, partner, locale y lead owner.
8. Agregar una pantalla AG-UI/SSE de diagnostico progresivo.
9. Validar con 3 perfiles: profesional, pyme y empresa, en español, ingles y hebreo donde aplique.
