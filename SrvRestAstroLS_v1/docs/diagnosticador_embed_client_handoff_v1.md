# Team360 Diagnosticador Embed v1 — Handoff interno

**Propósito:** Documentar el proceso de entrega comercial/técnica del
Diagnosticador embebible a clientes externos.

**Destinatarios:** Equipo Team360 (comercial, técnico, operaciones).

## Qué se entrega al cliente

- `clientId`: identificador público del embed.
- Snippet recomendado con integrity.
- Snippet simple compatible.
- URL del manifest: `https://team360.live/embed/team360-diagnosticador.manifest.json`
- URL del loader: `https://team360.live/embed/team360-diagnosticador-loader.js`
- URL de la API: `https://team360.live/api`
- Requisitos de dominio/origin.
- Guía de troubleshooting.

## Qué NO se entrega

- `hmac_secret`
- `organization_code`
- `workspace_code`
- `package_code`
- `knowledge_scope_code`
- `assistant_instance_code`
- `allowed_origins` editables
- Credenciales de infraestructura
- Configuración de Milvus, LiteLLM ni PostgreSQL
- Acceso al backend de Team360

## Flujo de alta

```
Solicitud comercial
  → dominio del cliente
  → creación de embed_client
  → configuración de allowed_origins
  → entrega de snippet
  → validación browser
  → aprobación
```

## Mensaje breve para técnico del cliente

```
Te compartimos el snippet de instalación del Diagnosticador Team360. Debe
insertarse en la página donde quieran mostrarlo. El clientId es público y no
requiere claves privadas. Team360 autoriza el dominio desde backend, por eso
necesitamos confirmar el dominio exacto donde va a quedar instalado.
```

## Criterio de "listo para cliente"

- Snippet instalado.
- Sin errores de consola.
- `POST /api/diagnosis/embed/auth` → 200.
- `POST /api/diagnosis/turn` → 200/201 según endpoint.
- Respuesta visible del asistente.
- Sin secretos en frontend.
- Sin leaks de tenant/scope en red.

## Referencias

- Guía de instalación externa:
  `docs/diagnosticador_embed_installation_guide_v1.md`
- Contrato de distribución:
  `docs/diagnosticador_loader_distribution_v1.md`
- Snippet con integrity:
  `docs/diagnosticador_external_integrity_snippet_v1.md`
- Assets públicos:
  - `/embed/team360-diagnosticador.manifest.json`
  - `/embed/team360-diagnosticador-loader.js`
  - `/embed/team360-diagnosticador.js`
