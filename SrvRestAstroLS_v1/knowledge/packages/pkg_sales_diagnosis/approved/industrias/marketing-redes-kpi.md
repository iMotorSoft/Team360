---
document_code: marketing_redes_kpi
document_type: guide
version: "1.0"
status: approved
ingestion_status: ready
package_code: pkg_sales_diagnosis
knowledge_scope_code: ks_team360_sales_diagnosis
scope_type: package
organization_code: team360_live
workspace_code: team360_public_site
assistant_instance_code: team360_sales_diagnosis
service_code: svc_sales_diagnosis
area_key: industrias
topic_key: marketing_redes_kpi
node_path: "/industrias/marketing-redes-kpi"
title: "Automatización en marketing, redes sociales y KPI"
visibility: internal
locale: es
owner: Team360
last_review: 2026-06-15
access_tags:
  - public
  - ejecutivo_comercial
evidence_level: team360_definition
implementation_status: validated_on_knowledge
commercial_status: core_offer
service_maturity: CORE_VALIDADO
offer_decision:
  - sellable_now
review_cycle: per_release
risk_level: low
approval_notes: >
  Documento para orientar casos de marketing/redes/KPI hacia lo que sí
  se puede automatizar parcialmente, sin prometer integraciones no
  disponibles ni publicaciones automáticas no validadas.
---

# Automatización en marketing, redes sociales y KPI

## ¿Qué se puede automatizar en marketing?

El marketing digital tiene muchas tareas repetitivas que se prestan a la automatización, pero **no todo es automático**. Depende de los accesos, las APIs disponibles, los permisos de cada plataforma y las reglas de negocio.

### Planificación y calendario

- Programar contenido en un calendario editorial compartido.
- Recibir recordatorios de fechas de publicación.
- Coordinar aprobaciones entre creadores de contenido y revisores.

Esto **no requiere integración directa con la red social**. Se puede hacer con herramientas de gestión que Team360 puede conectar o complementar.

### Publicación automática

- Algunas plataformas tienen APIs que permiten publicar contenido programado.
- **Team360 no garantiza integración directa con todas las plataformas.** Depende de:
  - Que la plataforma tenga API pública (TikTok, Meta/Facebook/Instagram, LinkedIn, X/Twitter).
  - Que el cliente tenga los permisos necesarios.
  - Que exista un conector validado.
- Si la plataforma no tiene API o los permisos no están disponibles, la publicación debe hacerse manualmente.

### Métricas y KPI

Team360 puede ayudar a **recopilar, ordenar y visualizar métricas** de redes sociales si los datos están disponibles:

| KPI típico | ¿Se puede automatizar? |
|---|---|
| Visualizaciones / alcance | Sí, si hay acceso a datos de la plataforma |
| Clics / interacciones | Sí, si hay acceso |
| Mensajes / leads entrantes | Sí, se pueden registrar automáticamente |
| Tasa de conversión | Depende de tener datos de ventas o CRM |
| Costo por resultado | Depende de datos de inversión publicitaria |
| Frecuencia de publicación | Sí, con calendario y registro |
| Tasa de respuesta | Sí, midiendo tiempo entre consulta y respuesta |

### Lo que NO podemos garantizar hoy

- Team360 **no tiene una integración TikTok nativa lista para todos los clientes**.
- Team360 **no publica automáticamente en nombre del cliente sin revisión**.
- Team360 **no genera contenido creativo** (textos, imágenes, videos) automáticamente.
- Team360 **no reemplaza un administrador de redes sociales o un community manager**.
- Team360 **no promete KPI exactos, ROI ni SLA** sin revisión del caso concreto.

## Cómo empezar

Para diagnosticar automatización en marketing necesitamos entender:

1. **¿Qué red o redes usás?** (TikTok, Instagram, Facebook, LinkedIn, X, YouTube, etc.)
2. **¿Publicás contenido regularmente o es esporádico?**
3. **¿Quién crea el contenido?** (vos, un equipo, una agencia)
4. **¿Qué métricas mirás hoy?** (visualizaciones, likes, comentarios, mensajes, leads, ventas)
5. **¿Usás alguna herramienta hoy?** (planilla, CRM, herramienta de programación)
6. **¿Tenés acceso a la cuenta de negocio / API / permisos de la plataforma?**

Con esa información podemos identificar qué partes del proceso se pueden automatizar.

## Reglas importantes

- No prometer que TikTok / Instagram / Facebook posting automático está listo como servicio comercial si no está validado.
- No prometer KPI exactos ni ROI antes de revisar el caso.
- No decir que "cualquier red social se integra sin configuración".
- Separar siempre entre:
  - **Lo que se puede hacer con herramientas de gestión** (calendario, avisos, reportes).
  - **Lo que requiere integración directa con la plataforma** (publicación automática, lectura de métricas).
  - **Lo que requiere permisos del cliente** (acceso a la cuenta de negocio, API keys).

## Referencias

- `[[que-es-automatizar]]`: Explicación básica de automatización
- `[[procesos-fisicos-vs-digitales]]`: Límites de automatización digital
- `[[reglas-anti-overpromise]]`: No prometer lo que no se puede hacer
- `[[capacidades-futuras-e-integraciones]]`: Estado de integraciones
