# Auditoria Kommo Dashboard

Evidencia: captura manual provista en la conversacion el 2026-05-20.

URL observada:

`mariocastroteam.kommo.com/dashboard/?sel=all&period=custom&pipeline_id=13089748&date_from=01%2F04%2F2026&date_to=30...`

Periodo visible: `01/04/2026 - 30/04/2026`.

## Lo confirmado

| Elemento | Estado | Evidencia observada | Utilidad para Excel |
|---|---|---|---|
| Acceso a Kommo dashboard | Confirmado | Se ve dashboard de `mariocastroteam`. | Sirve como smoke de login/sesion y como control agregado. |
| Filtro por periodo personalizado | Confirmado | Selector muestra `01/04/2026 - 30/04/2026`. | Necesario para KPIs mensuales. |
| Filtro por pipeline | Confirmado | URL incluye `pipeline_id=13089748`; sidebar muestra varios pipelines/embudos. | Permite separar embudos/proyectos si el uso operativo lo respeta. |
| Filtro por usuario | Confirmado | Control `Elija un usuario`. | Puede permitir segmentar por asesor desde dashboard. |
| Leads por usuario | Confirmado | Widget: total `5196`; Mery Faversani `4787`; Team Ventas 2025 `409`; Otros `0`. | Alimenta leads por asesor/equipo, al menos como agregado. |
| Fuentes de leads | Parcialmente confirmado | Widget lista `MARKETING QUE CONSTRUYE`, `MARIO_CASTRO_REMAX`, `KYOMU PILAR`. | Confirma existencia de fuentes, pero la captura no muestra conteos por fuente. |
| Etapas/pipeline | Parcialmente confirmado | Se ven etapas como `Contacto Inicial`, `Seguimiento sin Info`, `Respondio Seguimient...`, `Derivados Nina`, `Solicitud de Reunion/...`. | Permite mapear estados comerciales si se valida el significado operativo. |
| Tareas | Confirmado | `Tareas caducadas 211`, `Tareas para completar 211`, `Today's completed tasks 4`, `Leads sin tareas 5013`. | Puede alimentar seguimiento operativo, pero no reemplaza detalle por lead. |
| Valores monetarios | Parcial | Las tarjetas visibles muestran `$0`. | No confirma facturacion ni valor de operacion cargado. |

## Lectura tecnica

El dashboard es util para validar agregados, tendencias y controles mensuales. No alcanza por si solo para generar el Excel CEO con trazabilidad porque no muestra en una tabla exportable todos los campos necesarios por lead: fecha, asesor, fuente, proyecto, etapa, actividad, valor y estado final.

La automatizacion final no deberia depender solo de scraping visual del dashboard. El siguiente objetivo tecnico es confirmar si existe exportacion desde el listado de leads o desde reportes de Kommo. Si existe export, debe ser la fuente primaria. Si no existe, habra que inspeccionar listado y tarjetas individuales.

## KPIs que quedan con mejor factibilidad desde Kommo

| KPI | Factibilidad tras captura | Comentario |
|---|---|---|
| Leads totales | Media-Alta | Confirmado como agregado dashboard; falta confirmar definicion exacta y deduplicacion. |
| Leads por asesor | Alta para agregado | Widget visible con asesores/equipos. Falta detalle/export. |
| Fuentes de leads | Media | Fuentes visibles, pero faltan conteos. |
| Seguimientos/tareas | Media | Widgets de tareas visibles. Falta detalle por asesor/lead. |
| Reuniones solicitadas | Media | Hay etapa `Solicitud de Reunion/...`; falta validar si equivale a reunion generada o solo solicitud. |
| Respondieron | Media | Hay etapa `Respondio Seguimient...`; falta validar definicion. |
| Facturacion | Baja | Los valores visibles estan en `$0`; no confirma uso de monto. |
| Visitas, negociaciones, cierres, perdidos | No confirmado | No se ven claramente en la captura como etapas o totales finales suficientes. |

## Pendientes de inspeccion Kommo

1. Abrir listado de leads con el mismo periodo y pipeline.
2. Confirmar si existe boton de exportacion CSV/XLSX.
3. Confirmar columnas visibles/exportables: fecha, asesor, fuente, proyecto, etapa, valor, telefono/canal, ultima actividad.
4. Abrir una tarjeta de lead de ejemplo y confirmar campos custom de proyecto/desarrollo, fuente y valor.
5. Confirmar etapas reales del pipeline y su equivalencia con KPIs del Excel.
6. Confirmar si WhatsApp/Facebook se identifica como canal/fuente dentro de cada lead.

## Decision recomendada

Usar dashboard Kommo como control de consistencia y auditoria visual. Para el MVP, priorizar export/listado de leads como fuente primaria; usar los widgets del dashboard para comparar totales por periodo, asesor y fuentes.

# Auditoria Kommo Inbox / Chats

Evidencia: segunda captura manual provista en la conversacion el 2026-05-20.

## Lo confirmado

| Elemento | Estado | Evidencia observada | Utilidad para Excel |
|---|---|---|---|
| Acceso a inbox/conversaciones Kommo | Confirmado | Vista lateral con buscador, `ENTRADAS`, `Chats abiertos`. | Confirma que Kommo concentra conversaciones. |
| Total de entradas/chats | Confirmado | Se ve `Total: 6924`. | Puede servir como control operativo, pero no necesariamente como leads mensuales. |
| Chats abiertos | Confirmado | Badge `444` junto a `ENTRADAS`. | KPI operativo posible; no esta directo en Excel base salvo seguimiento/pendientes. |
| Canales visibles | Confirmado | Iconos de WhatsApp e Instagram/Facebook junto a contactos. | Permite distinguir canal si el dato es extraible. |
| Contacto/persona | Confirmado | Ejemplos: `Yessi Mildenberger x Kyomu Pilar`, `Zulma Martinez x Oro`, etc. | Puede asociar lead con proyecto si el nombre contiene desarrollo. |
| ID de lead/contacto | Confirmado | Badges tipo `A168105`, `A158293`, etc. | Puede usarse como identificador estable de scraping si se valida. |
| Ultimo mensaje / preview | Confirmado | Preview de mensajes de Salesbot y usuario. | Ayuda a detectar respuesta, pero no reemplaza estado estructurado. |
| Hora del ultimo mensaje | Confirmado | Horas visibles: `Hoy 19:50`, `Hoy 19:49`, etc. | Util para actividad reciente; falta fecha completa en listado. |
| Menciones/chats de equipo | Confirmado | Seccion `MENCIONES & CHATS DE EQUIPO` con badge `27`. | KPI operativo interno, no pedido central del Excel. |

## Lectura tecnica

El inbox confirma que Kommo contiene conversaciones omnicanal, incluyendo WhatsApp e Instagram/Facebook. Para automatizacion RPA, la lista es potencialmente scrapeable como evidencia de canal, contacto, ultimo mensaje y estado de chat abierto.

Sin embargo, para el Excel CEO no conviene usar inbox como fuente primaria de todos los KPIs comerciales. Es mejor usarlo como fuente secundaria para:

- validar si un lead respondio;
- auditar canal de origen;
- revisar conversaciones sin tarea o abiertas;
- comprobar casos donde el listado/export de leads no traiga el canal.

Riesgo principal: la lista parece virtualizada y orientada a operacion en vivo. Scraping masivo de miles de chats (`Total: 6924`) seria fragil y lento si no hay export o filtros fuertes.

## Datos confirmados desde Inbox

| Dato | Factibilidad Playwright | Comentario |
|---|---|---|
| Nombre/contacto | Media-Alta | Visible en lista. |
| Canal WhatsApp/Instagram | Media | Visible por icono; requiere selector o lectura de atributos/imagenes. |
| Estado chat abierto | Alta | Vista filtrada por `Chats abiertos`. |
| Ultimo mensaje preview | Media-Alta | Visible pero truncado. |
| Hora ultimo mensaje | Media | Visible como hora relativa; falta fecha absoluta. |
| ID tipo A168105 | Alta | Visible en badges; podria usarse para trazabilidad. |
| Respuesta del lead | Media | Detectable si el preview no es Salesbot, pero conviene validar con detalle de conversacion. |
| Proyecto/desarrollo | Baja-Media | A veces aparece en nombre (`Kyomu Pilar`, `Oro`, `Manzanares`), pero debe ser campo estructurado para KPI confiable. |

## Pendientes especificos de Inbox

1. Abrir un chat y confirmar si se ve fecha completa, canal y ficha del lead.
2. Confirmar si el inbox permite filtrar por fecha, canal, responsable o estado.
3. Confirmar si existe export o reporte de conversaciones.
4. Confirmar si el ID `A...` enlaza con tarjeta de lead y puede cruzarse con listado/export.
5. Definir si `respondio` se calcula por estado estructurado o por presencia de mensajes del cliente.
