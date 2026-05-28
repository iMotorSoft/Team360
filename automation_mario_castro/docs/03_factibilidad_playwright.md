# Factibilidad Playwright

## Factibilidad general

La automatizacion por Playwright es factible como MVP exploratorio si se aceptan estas condiciones:

- El primer login puede requerir intervencion humana por 2FA/captcha.
- Las sesiones se reutilizan con `storage_state`.
- La extraccion final debe priorizar exportaciones CSV/XLSX desde la UI cuando existan.
- El scraping directo de tablas debe quedar como fallback, porque Kommo, Facebook y Meta cambian la UI con frecuencia.

## Kommo

Factibilidad inicial: `Media-Alta` tras evidencia de Dashboard, Inbox y Registro de actividades.

Datos confirmados o probablemente obtenibles:

- Leads por periodo desde eventos `Nuevo lead creado`, si el registro permite filtro/export.
- Asesor/responsable desde eventos/listado; dashboard confirma agregados por usuario.
- Etapa del pipeline desde eventos `La etapa de ventas cambiada`.
- Fuente/origen desde eventos `Cambio en el campo "Fuente Lead"`; se observo `Whatsapp MKT`.
- Proyecto/desarrollo desde eventos `Cambio en el campo "Emprendimi..."`; se observaron `Bonifacio`, `Chivilcoy`, `Jaramillo`.
- Canal/conversacion desde Inbox y eventos `Mensaje entrante`, `Mensaje saliente`, `Conversacion comenzada/cerrada`.
- Valor de operacion sigue no confirmado; dashboard muestra valores `$0`.

Riesgos:

- El registro tiene volumen alto (`1789233 actividades`); sin filtro/export el scraping masivo puede ser lento.
- La fecha visible puede ser relativa (`Hoy 19:54`); hay que confirmar fecha absoluta en DOM o export.
- Etapas pueden no equivaler directamente a los KPIs del Excel y deben homologarse.
- Mensajes y telefonos son datos personales; screenshots/runtime deben tratarse como sensibles.
- Conversaciones WhatsApp/Instagram aparecen en Inbox, pero el canal por fila puede depender de iconos o atributos no textuales.
- Seguimientos/recuperados dependen de tareas, etapas o etiquetas bien usadas.

Recomendacion:

1. Priorizar `Analitica > Registro de actividades` como fuente candidata primaria de eventos historicos.
2. Confirmar si el registro permite filtrar por fecha/rango y exportar CSV/XLSX.
3. Usar dashboard como control de totales por periodo, pipeline y usuario.
4. Usar Inbox como fuente secundaria para validar canal/respuesta, no como scraping masivo principal.
5. Si no hay export, implementar un probe de tabla paginada/virtualizada que guarde filas estructuradas en JSON.

## Evidencia Kommo observada

- Dashboard confirma filtro mensual, pipeline, usuario, leads por usuario, fuentes visibles y widgets de tareas.
- Inbox confirma chats abiertos, total de conversaciones, iconos de WhatsApp/Instagram, contacto, ID tipo `A168105`, preview de mensaje y hora relativa.
- Registro de actividades confirma tabla con `Fecha`, `Usuario`, `Objeto`, `Nombre`, `Actividades`, `Valor previo`, `Valor posterior`, incluyendo eventos de lead, contacto, conversacion, mensajes, cambios de etapa, fuente y emprendimiento.

## Facebook Page / Inbox

Factibilidad inicial: `Baja a Media`.

Datos probablemente obtenibles si el usuario tiene permisos:

- Acceso a paginas vinculadas.
- Acceso a Inbox / Meta Business Suite.
- Mensajes entrantes, pagina de origen, fecha aproximada y contacto.

Riesgos:

- Permisos insuficientes.
- 2FA y checkpoints de seguridad.
- UI muy dinamica y virtualizada.
- Datos personales en screenshots y textos.

Recomendacion:

- Usar Facebook/Inbox solo para validar origen y casos que no lleguen a Kommo.
- Evitar convertir Inbox en fuente principal si Kommo ya concentra WhatsApp y entradas Facebook.

## Meta Ads Manager

Factibilidad inicial: `Alta si hay permisos`.

Datos probablemente obtenibles:

- Campana.
- Inversion.
- Impresiones.
- Clics.
- CTR.
- CPC.
- Leads/resultados.
- CPL.
- Periodo.

Riesgos:

- Permisos sobre cuenta publicitaria.
- Moneda y zona horaria.
- Cambios en columnas visibles.
- Exportaciones con nombres de columna variables.

Recomendacion:

- Priorizar descarga de reporte CSV/XLSX desde Ads Manager.
- Configurar preset de columnas y rango de fechas.
- Evitar scraping de grillas salvo que no haya descarga.

## Riesgos transversales

- 2FA/captcha: requiere flujo HITL documentado.
- Cambios de UI: selectores deben ser heuristicas, no contrato estable.
- Permisos: login exitoso no implica permisos de pagina, inbox o ads.
- Calidad de datos: sin campos estructurados en Kommo no hay KPI confiable.
- Nomenclatura: campanas Meta deben incluir proyecto y formato de forma consistente.

## Recomendacion MVP

Construir un MVP con dos fuentes primarias:

1. Kommo como fuente comercial: leads, asesor, etapa, fuente, proyecto y valor.
2. Meta Ads como fuente de pauta: inversion, impresiones, clics, leads, campana, formato y proyecto.

Facebook Page/Inbox queda como fuente secundaria de auditoria, no como base principal del Excel, salvo que se detecten mensajes relevantes que no entren a Kommo.
