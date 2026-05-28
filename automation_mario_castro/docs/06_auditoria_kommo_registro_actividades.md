# Auditoria Kommo Registro de Actividades

Evidencia: captura manual provista en la conversacion el 2026-05-20.

Pantalla observada: `Analitica > Registro de actividades`.

## Lo confirmado

| Elemento | Estado | Evidencia observada | Utilidad para Excel |
|---|---|---|---|
| Registro global de actividades | Confirmado | Pantalla muestra `1789233 actividades`. | Fuente candidata para reconstruir eventos historicos. |
| Filtro | Confirmado | Campo `Filtro` visible arriba. | Puede permitir acotar por texto, objeto, fecha o usuario si la UI lo soporta. |
| Columnas tabulares | Confirmado | `Fecha`, `Usuario`, `Objeto`, `Nombre`, `Actividades`, `Valor previo`, `Valor posterior`. | Estructura muy util para scraping/export si no hay descarga. |
| Objetos auditados | Confirmado | Se ven `Conversacion`, `Contacto`, `Lead`. | Permite distinguir eventos comerciales y conversacionales. |
| Usuarios/actores | Confirmado | `Robot`, `Team Ventas 2025`, `SalesBot...`. | Permite separar acciones automáticas, equipo y bots. |
| Nuevo lead creado | Confirmado | Actividad `Nuevo lead creado` sobre `Lead #26418777`. | Puede alimentar leads ingresados si se filtra por periodo. |
| Nuevo contacto creado | Confirmado | Actividad `Nuevo contacto creado`. | Puede cruzarse con leads/contactos. |
| Mensaje entrante | Confirmado | Actividad `Mensaje entrante` con texto en valor posterior. | Candidato para detectar respuesta real del lead. |
| Mensaje saliente | Confirmado | Actividad `Mensaje saliente` por SalesBot. | Candidato para medir actividad/bot, no necesariamente respuesta humana. |
| Conversacion comenzada/cerrada | Confirmado | Actividades `Conversacion comenzada` y `Conversacion cerrada`. | Puede medir actividad de inbox y lifecycle de conversaciones. |
| Cambio de etapa | Confirmado | `La etapa de ventas cambiada`; valor previo/posterior con etapas. | Fuente clave para reuniones, perdidos, derivados y pipeline. |
| Fuente del lead | Confirmado | `Cambio en el campo "Fuente Lead"` con valor `Whatsapp MKT`. | Fuente estructurada confirmada. |
| Emprendimiento/proyecto | Confirmado | `Cambio en el campo "Emprendimi..."` con valores `Bonifacio`, `Chivilcoy`, `Jaramillo`. | Fuente estructurada confirmada para desarrollos/proyectos. |
| Telefono | Confirmado | `Cambio en el campo "Telefono"` con numero en valor posterior. | Dato sensible; no necesario para Excel CEO salvo deduplicacion. |
| Lead eliminado | Confirmado | Actividad `Lead eliminado`. | Riesgo para conteos historicos si se eliminan registros. |

## Lectura tecnica

El registro de actividades parece la fuente mas prometedora para RPA porque expone eventos discretos con columnas estructuradas. Si se puede filtrar por fecha y exportar, podria alimentar gran parte del Excel sin abrir cada tarjeta de lead.

Incluso sin export, la tabla es mas apta para scraping que el dashboard o el inbox, porque tiene columnas estables y filas con eventos atomicos.

## KPIs que mejora esta pantalla

| KPI / dato | Factibilidad tras captura | Regla candidata |
|---|---|---|
| Leads ingresados | Alta si hay filtro/export | Contar eventos `Nuevo lead creado` por periodo. |
| Leads respondieron | Media-Alta | Detectar `Mensaje entrante` asociado a conversacion/lead despues de creado. |
| Fuente de lead | Alta | Usar eventos `Cambio en el campo "Fuente Lead"`. |
| Proyecto/desarrollo | Alta | Usar eventos `Cambio en el campo "Emprendimi..."`. |
| Cambios de etapa | Alta | Usar `La etapa de ventas cambiada`, valor previo y posterior. |
| Perdidos | Alta si etapa es consistente | Detectar valor posterior `Ventas Perdidos` u otra etapa perdida. |
| Reuniones/derivaciones | Media | Detectar etapa `Solicitud de Reunion/...`, `Derivados Nina` u homologadas. |
| Conversaciones iniciadas/cerradas | Alta | Eventos `Conversacion comenzada` / `Conversacion cerrada`. |
| Actividad bot vs equipo | Media-Alta | Columna `Usuario`: `Robot`, `SalesBot`, `Team Ventas 2025`. |

## Riesgos

- Hay `1789233 actividades`: scraping masivo sin filtro/export puede ser lento e inestable.
- La fecha visible es relativa (`Hoy 19:54`); hay que confirmar si con filtros/rango se obtiene fecha absoluta o si el DOM contiene timestamp completo.
- Cambios de campos pueden tener nombres truncados visualmente (`Emprendimi...`); hay que inspeccionar DOM o export para nombre completo.
- Mensajes pueden contener datos personales; runtime y screenshots deben tratarse como sensibles.
- Eventos de `Robot` y `SalesBot` deben separarse de acciones humanas para KPIs comerciales.
- `Lead eliminado` implica que los conteos por estado actual pueden diferir del historico de eventos.

## Proxima prueba recomendada

1. Buscar si `Registro de actividades` permite filtro por fecha/rango mensual.
2. Confirmar si hay export CSV/XLSX del registro.
3. Si no hay export, probar paginacion/scroll virtualizado con Playwright y guardar las primeras N filas como JSON.
4. Abrir una fila o enlace de `Lead` para confirmar si el ID del evento cruza con tarjeta/listado de leads.
5. Definir mapeo de etapas reales a KPIs del Excel.

## Decision recomendada

Usar `Registro de actividades` como fuente candidata primaria para eventos historicos de Kommo. Mantener dashboard como control agregado e inbox como evidencia secundaria de canal/conversacion.
