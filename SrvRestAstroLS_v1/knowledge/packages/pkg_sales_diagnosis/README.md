# pkg_sales_diagnosis — Documentos Fuente

Paquete de conocimiento del asistente de diagnóstico de automatización y ventas.

## Identificadores técnicos

| Campo | Valor |
|---|---|
| `package_code` | `pkg_sales_diagnosis` |
| `knowledge_scope_code` | `ks_team360_sales_diagnosis` |
| `assistant_instance_code` | `team360_sales_diagnosis` |
| `service_code` | `svc_sales_diagnosis` |
| `template_code` | `team360_sales_automation_diagnosis` |

## Áreas de conocimiento

| area_key | Descripción |
|---|---|
| `ventas` | Procesos de venta, guías de producto, argumentación comercial |
| `automatizaciones` | Automatización de procesos, diagnóstico de factibilidad |
| `scoring` | Modelos de scoring, ponderación, criterios de factibilidad |
| `seguridad` | Políticas de seguridad, privacidad, compliance |
| `integraciones` | APIs, conectores, integraciones con terceros |
| `industrias` | Verticales de industria, casos de uso específicos |
| `objeciones` | Manejo de objeciones comerciales y técnicas |
| `glosario` | Términos, definiciones, acrónimos del dominio |

## Convenciones

- Los archivos dentro de `approved/{area_key}/` deben nombrarse en kebab-case, ej: `proceso-de-venta.md`.
- Todo documento en `approved/` debe tener metadata YAML front-matter válida según la plantilla `drafts/document-template.md`.
- No incluir datos de clientes reales ni información sensible.
- `drafts/` es para documentos en revisión; `approved/` para documentos listos para ingesta.
- `exports/pdf/` contiene versiones PDF derivadas; la fuente canónica es el Markdown en `approved/`.
- `archive/` contiene documentos reemplazados que se conservan como referencia histórica.
