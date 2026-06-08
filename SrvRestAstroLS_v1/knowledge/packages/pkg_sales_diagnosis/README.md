# pkg_sales_diagnosis — Documentos Fuente

Paquete de conocimiento del asistente de ventas, diagnóstico de automatización y evaluación de procesos automatizables.

`Vera / Asistente Inteligente Vera` es el nombre comercial visible. Los identificadores core del paquete deben mantenerse técnicos y estables; no usar `vera_*` como identificador de runtime, scope, paquete, servicio, worker ni documento canónico.

Este paquete es el primer caso concreto dentro de la fundacion documental
`knowledge/`. No define por si solo la arquitectura general de knowledge de
Team360. Las reglas transversales viven en `../../_standards/` y el knowledge
reusable por multiples paquetes debe vivir en `../../global/`.

## Identificadores técnicos

| Campo | Valor |
|---|---|
| `package_code` | `pkg_sales_diagnosis` |
| `knowledge_scope_code` | `ks_team360_sales_diagnosis` |
| `assistant_instance_code` | `team360_sales_diagnosis` |
| `service_code` | `svc_sales_diagnosis` |
| `template_code` | `team360_sales_automation_diagnosis` |

## Plan real de validación

La primera validación del paquete ocurre en Team360.live como cliente/proyecto interno de prueba. Este paquete debe permitir probar el flujo completo de exposición pública, diagnóstico, aprendizaje, curaduría y actualización antes de escalarlo a clientes externos.

`Vera / Asistente Inteligente Vera` estará visible en la home pública de Team360 como asistente de Ventas y Diagnóstico de Automatización. Ventas es el primer ángulo comercial, pero el diagnóstico no debe quedar limitado a ventas: debe poder analizar cualquier proceso potencialmente automatizable, incluyendo procesos administrativos, operativos, comerciales, documentales, de soporte, integraciones, reportes, seguimiento, controles humanos y flujos con riesgo.

El criterio de respuesta debe separar dos preguntas distintas:

1. Si el proceso es automatizable desde el punto de vista técnico u operativo.
2. Si Team360 debe venderlo hoy, venderlo como piloto, tratarlo como oportunidad futura o derivarlo a revisión humana.

La primera etapa puede operar con documentos curados y un script controlado de carga/update del corpus. No se requiere todavía una interfaz completa de administración de knowledge. La interfaz puede construirse después de validar el ciclo real de uso, aprendizaje y curaduría.

Ciclo operativo esperado:

`prueba -> aprendizaje -> curaduría -> update -> nueva prueba`

Cada prueba pública o interna debe producir aprendizaje revisable. Ese aprendizaje no entra automáticamente a `approved/`: primero debe curarse, clasificarse, validar evidencia y actualizar el corpus con límites claros.

## Decisión de oferta comercial

Además de `commercial_status` y `service_maturity`, cada documento puede orientar una decisión comercial concreta. Esta decisión no reemplaza el scoring ni la revisión humana; sirve para evitar que el asistente prometa como servicio actual algo que solo es automatizable o exploratorio.

| Valor | Uso |
|---|---|
| `automatable` | El proceso parece automatizable, pero todavía no implica que Team360 deba venderlo como oferta actual. |
| `sellable_now` | Puede ofrecerse hoy con alcance y límites claros. |
| `pilot` | Puede ofrecerse como piloto controlado, con validación, HITL o acompañamiento explícito. |
| `future_opportunity` | Interesante para roadmap o paquete futuro, pero no vendible ahora como servicio estándar. |
| `human_review_required` | Requiere evaluación humana antes de responder, presupuestar, ejecutar o prometer resultado. |

Usar `human_review_required` cuando existan riesgos de seguridad, datos sensibles, credenciales, cumplimiento, impacto financiero, acciones irreversibles, integraciones críticas, expectativas ambiguas o falta de evidencia suficiente.

## Política de knowledge evolutivo

`pkg_sales_diagnosis` no es un catálogo cerrado. Es un knowledge package evolutivo que se actualiza con implementaciones reales, pilotos, pruebas comerciales, conversaciones con clientes, validaciones técnicas y aprendizajes posteriores a la venta.

El asistente no debe tratar igual una oportunidad no validada que una capacidad validada en producción. Todo documento fuente debe declarar nivel de evidencia, estado comercial, estado de implementación y madurez del servicio para que retrieval, scoring, copy comercial y recomendaciones puedan distinguir entre:

- capacidades core con evidencia suficiente;
- pilotos o pruebas comerciales vendibles con límites explícitos;
- oportunidades todavía exploratorias;
- paquetes futuros que requieren diseño, delivery o validación adicional;
- temas que no deben ofrecerse todavía.

Reglas por directorio:

- `drafts/`: hipótesis, oportunidades, material en revisión, aprendizajes preliminares o documentos incompletos. No se consideran fuente canónica para ingesta.
- `approved/`: documentos listos para ingesta, con evidencia suficiente, alcance claro, límites documentados, metadata completa y aprobación explícita.
- `archive/`: documentos reemplazados, discontinuados o fuera de uso activo. Se conservan como referencia histórica, pero no deben alimentar respuestas activas salvo decisión explícita.
- `exports/`: derivados para lectura humana. La fuente canónica sigue siendo Markdown.

La priorización inicial debe basarse en evidencia real de ejecución, especialmente inventarios profesionales, implementaciones y casos efectivamente realizados. Team360 frontend y Mamamia360 pueden orientar lenguaje comercial, posicionamiento y oportunidades, pero no convierten por sí solos una idea en oferta core.

## Niveles de evidencia

| Valor | Uso |
|---|---|
| `hypothesis` | Idea, hipótesis comercial o contenido preliminar sin validación suficiente. Solo apto para `drafts/`. |
| `validated_by_source` | Validado por fuentes documentales confiables, inventario profesional, evidencia técnica o experiencia previa verificable. |
| `validated_by_pilot` | Probado en piloto, demo controlada o prueba comercial con aprendizaje real y límites conocidos. |
| `validated_by_production` | Validado en cliente, operación real o implementación productiva con evidencia suficiente. |
| `deprecated` | Reemplazado, pausado, desaconsejado o fuera de uso activo. Debe moverse a `archive/` o quedar marcado como no utilizable. |

## Estados comerciales

| Valor | Uso |
|---|---|
| `exploratory` | Tema exploratorio; puede investigarse o mencionarse como posibilidad, no venderse como servicio definido. |
| `sellable_pilot` | Vendible como piloto acotado, con expectativas, alcance y riesgos explícitos. |
| `sellable_service` | Servicio vendible con alcance definido y delivery razonablemente repetible. |
| `core_offer` | Oferta core del Sales Diagnosis Assistant por evidencia, foco estratégico y factibilidad inicial. |
| `future_package` | Oportunidad relevante, pero requiere paquete, diseño, roadmap o validación futura antes de ofrecerse como core. |
| `not_offered` | No ofrecer activamente; usar solo para límites, objeciones o descarte informado. |

## Estados de implementación

| Valor | Uso |
|---|---|
| `not_implemented` | No existe implementación operativa todavía. |
| `prototype` | Existe demo, mock, PoC o flujo parcial no productivo. |
| `pilot_done` | Hubo piloto o prueba controlada con resultado y aprendizaje documentado. |
| `production_client` | Existe implementación real en cliente o uso productivo. |
| `paused` | Iniciativa pausada por prioridad, riesgo, dependencia o decisión comercial. |
| `deprecated` | Implementación o enfoque reemplazado; no usar para venta ni recomendación activa. |

## Clasificación de servicios

| Etiqueta | Cuándo usarla |
|---|---|
| `CORE_VALIDADO` | Servicio alineado al foco inicial, con evidencia suficiente y capacidad defendible para oferta principal. |
| `PILOTO_VALIDADO` | Servicio probado o factible para vender como piloto con límites claros, pero todavía no maduro como core repetible. |
| `OPORTUNIDAD` | Interés comercial o dirección posible sin evidencia suficiente para prometer delivery estándar. |
| `PAQUETE_FUTURO` | Línea relevante que merece diseño propio, especialización o roadmap antes de activarse como oferta. |
| `NO_OFRECER_AUN` | Tema fuera de alcance actual, riesgoso, no validado o demasiado amplio para comercializar ahora. |

Ejemplos iniciales:

| Servicio o tema | Clasificación esperada |
|---|---|
| Diagnóstico de automatización comercial | `CORE_VALIDADO` |
| CRM + WhatsApp + leads | `CORE_VALIDADO` o `PILOTO_VALIDADO`, según evidencia del documento fuente |
| Seguimiento comercial | `CORE_VALIDADO` |
| Reportes KPI comerciales / Excel / dashboards | `CORE_VALIDADO` |
| Automatización de procesos comerciales | `CORE_VALIDADO` |
| RAG / asistentes sobre documentos propios | `CORE_VALIDADO` |
| Integraciones comerciales | `CORE_VALIDADO` o `PILOTO_VALIDADO`, según complejidad y caso |
| Seguridad, accesos, MFA y HITL | `CORE_VALIDADO` como política transversal |
| Browser automation | `CORE_VALIDADO` o `PILOTO_VALIDADO`, según caso y estabilidad operativa |
| Objeciones comerciales | `CORE_VALIDADO` |
| Casos por industria | `CORE_VALIDADO` o `PILOTO_VALIDADO`, según evidencia sectorial |
| Bot de trading inteligente | `PAQUETE_FUTURO` u `OPORTUNIDAD` |
| Generación de imágenes/video | `OPORTUNIDAD` |
| Asistentes personales genéricos | `OPORTUNIDAD` o `NO_OFRECER_AUN` |
| Marketplaces complejos | `PAQUETE_FUTURO` |
| ERP amplio | `PAQUETE_FUTURO` |
| Conciliaciones bancarias avanzadas | `PAQUETE_FUTURO` o vertical futuro |
| SICOM/PILAGA/FX como oferta general | `PAQUETE_FUTURO` o `NO_OFRECER_AUN` |
| Fidelización genérica | `OPORTUNIDAD` |

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

- Aplican los estandares generales de `../../_standards/`.
- Los archivos dentro de `approved/{area_key}/` deben nombrarse en kebab-case, ej: `proceso-de-venta.md`.
- Todo documento en `approved/` debe tener metadata YAML front-matter válida según la plantilla `drafts/document-template.md`.
- Para promover un documento a `approved/`, los campos `evidence_level`, `evidence_sources`, `implementation_status`, `commercial_status`, `service_maturity`, `review_cycle`, `last_validated_at`, `validated_by`, `risk_level` y `approval_notes` deben estar completos.
- `related_pilots` y `related_clients` son opcionales, pero deben declararse como lista vacía (`[]`) cuando no apliquen o no puedan divulgarse.
- No incluir datos de clientes reales ni información sensible.
- `drafts/` es para documentos en revisión; `approved/` para documentos listos para ingesta.
- `exports/pdf/` contiene versiones PDF derivadas; la fuente canónica es el Markdown en `approved/`.
- `archive/` contiene documentos reemplazados que se conservan como referencia histórica.
