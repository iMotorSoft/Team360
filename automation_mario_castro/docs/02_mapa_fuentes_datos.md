# Mapa de fuentes de datos

Estado: matriz actualizada con evidencia manual de Kommo Dashboard. La lista/export de leads sigue `No confirmado` hasta inspeccionar esa pantalla.

| KPI | Fuente primaria | Fuente secundaria | Pantalla probable | Selector/accion probable | Nivel de confianza | Riesgo | Observaciones |
|---|---|---|---|---|---|---|---|
| Leads totales / leads asignados | Kommo | Facebook Inbox | Registro de actividades, Dashboard y Leads/listado | Filtrar periodo + contar `Nuevo lead creado` | Alta si hay filtro/export | Duplicados, eliminados, leads sin asesor | Registro confirma eventos `Nuevo lead creado`; dashboard queda como control agregado. |
| Leads por asesor | Kommo | Calculo local | Dashboard `Leads por usuario` y Leads/listado | Widget usuario + filtro responsable/asesor | Alta para agregado / Media para detalle | Asignaciones cambiadas historicamente | Captura confirma Mery Faversani, Team Ventas 2025 y Otros; falta detalle/export. |
| Leads por fuente | Kommo | Meta Ads / Facebook | Registro de actividades y Dashboard fuentes | Eventos `Cambio en el campo "Fuente Lead"` | Alta si hay filtro/export | Fuente puede cargarse despues del alta | Registro confirma `Fuente Lead` con `Whatsapp MKT`; dashboard confirma fuentes visibles. |
| Leads calificados | Kommo | Manual | Pipeline o campos de lead | Etapa/tag/campo calificado | Baja | No confirmado | Requiere disciplina operativa. |
| Leads que respondieron | Kommo | Facebook Inbox | Registro de actividades, pipeline e Inbox | Eventos `Mensaje entrante` o etapa `Respondio...` | Media-Alta | Definicion ambigua; mensajes de bot deben excluirse | Registro confirma `Mensaje entrante`; falta definir si eso equivale a respondido. |
| Leads perdidos | Kommo | Manual | Registro de actividades / pipeline | Cambio de etapa a `Ventas Perdidos` u homologada | Alta si etapa es consistente | Motivo incompleto, eliminados | Registro confirma cambios hacia `Ventas Perdidos`. |
| Reuniones totales | Kommo | Manual | Registro de actividades / pipeline | Cambio de etapa a `Solicitud de Reunion/...` o actividad reunion | Media | Solicitud puede no equivaler a reunion realizada | Dashboard confirma etapa de solicitud; registro puede reconstruir cambios de etapa. |
| Reuniones por asesor | Kommo | Manual | Pipeline/listado | Filtro asesor + etapa/tarea | Media | Actividades no cerradas | Confirmar semantica en Kommo. |
| Visitas totales | Kommo | Manual | Pipeline/tareas | Etapa visita o actividad | Media | Visitas fuera del CRM | Requiere disciplina. |
| Visitas por asesor | Kommo | Manual | Pipeline/listado | Filtro asesor + etapa visita | Media | Cambios de responsable | Confirmar trazabilidad historica. |
| Negociaciones abiertas | Kommo | Manual | Registro de actividades / pipeline | Cambio de etapa a negociacion homologada | Media | Etapas no homologadas | Registro confirma cambios de etapa; falta ver etapa de negociacion real. |
| Cierres / reservas | Kommo | Manual | Pipeline | Etapa ganado/reserva/cierre | Media | Cierres sin monto | Requiere periodo de cierre. |
| Facturacion | Kommo | Manual/contabilidad | Lead/deal card | Campo valor/precio operacion | Baja | Valor no cargado o no final | Captura muestra valores `$0`; no confirma facturacion cargada. |
| Seguimientos | Kommo | Inbox / Manual | Dashboard tareas, Inbox y actividades | Widgets tareas + chats abiertos + detalle actividades | Media | Tareas/chats no equivalen siempre a seguimiento | Capturas confirman tareas y chats abiertos; falta cruzar con actividades por lead. |
| Recuperados | Kommo | Manual | Pipeline/tags | Tag/etapa recuperado | Baja | Definicion no estandar | Requiere convencion operativa. |
| Desarrollo/proyecto demandado | Kommo | Meta Ads | Registro de actividades / lead card | Evento `Cambio en el campo "Emprendimi..."` | Alta si campo es obligatorio | Campo puede cargarse tarde o con valores inconsistentes | Registro confirma valores `Bonifacio`, `Chivilcoy`, `Jaramillo`; Inbox tambien muestra proyectos en nombres. |
| Valor promedio m2 | Kommo | Manual | Deal card | Valor vendido + superficie | Baja | Superficie ausente | Requiere campos estructurados. |
| Ticket promedio | Kommo | Manual | Deal/listado | Facturacion / cierres | Media | Valores incompletos | Calculo local si hay montos. |
| Velocidad de absorcion | Manual / no definido | Kommo | No confirmado | Stock/unidades vendidas | Baja | Falta inventario | Requiere stock por desarrollo. |
| Tiempo promedio de cierre | Kommo | Calculo local | Registro de actividades | Fecha `Nuevo lead creado` + fecha etapa ganado/cierre | Media-Alta | Fecha visible relativa; falta fecha absoluta/export | Registro puede reconstruir lifecycle si hay timestamp completo. |
| Inversion publicitaria | Meta Ads | Manual | Ads Manager | Exportar reporte CSV/XLSX | Alta | Permisos Ads | Priorizar descarga sobre scraping. |
| Impresiones | Meta Ads | Manual | Ads Manager | Columnas reporte | Alta | Permisos Ads | Disponible normalmente en export. |
| Clics | Meta Ads | Manual | Ads Manager | Columnas reporte | Alta | Definicion de clic | Definir clics enlace vs todos. |
| CTR | Meta Ads | Calculo local | Ads Manager / Excel | Clics / impresiones | Alta | Metrica distinta por columna | Calcular local si hay base. |
| CPC | Meta Ads | Calculo local | Ads Manager / Excel | Inversion / clics | Alta | Moneda | Normalizar USD/ARS. |
| Leads por campana | Meta Ads | Kommo | Ads Manager | Resultados/leads + export | Alta | Atribucion | Cruzar con Kommo si hay UTM/fuente. |
| CPL | Meta Ads | Calculo local | Ads Manager / Excel | Inversion / leads | Alta | Leads Meta vs leads Kommo | Definir fuente oficial. |
| Campana/proyecto/formato | Meta Ads | Nomenclatura local | Ads Manager | Nombre campana/conjunto/anuncio | Media | Nombres inconsistentes | Convencion obligatoria. |
| ROI marketing | Kommo + Meta Ads | Calculo local | Ads + cierres Kommo | Facturacion atribuida / inversion | Baja | Atribucion incompleta | MVP puede dejarlo No confirmado. |
| CAC | Meta Ads + Kommo | Calculo local | Ads + cierres Kommo | Inversion / cierres | Media | Ventas no atribuibles | Definir si usa cierres o clientes. |
| Objetivos | Manual | Kommo | Excel o campo CRM | Carga mensual | Baja | No hay fuente confirmada | Mantener manual en MVP. |
| Diferencias contra objetivo | Calculo local | Excel | Workbook | Resultado - objetivo | Alta | Objetivos faltantes | Depende de objetivos. |
| Rankings asesores | Calculo local | Kommo | Excel/report local | Orden por criterio definido | Alta | Criterio ambiguo | Definir criterio CEO. |
| Rankings campanas | Calculo local | Meta Ads | Excel/report local | Ranking por reuniones/CPL | Alta | Reuniones por campana | Necesita cruce Ads-Kommo. |
| Rankings desarrollos | Calculo local | Kommo | Excel/report local | Ranking por leads/cierres | Alta | Proyecto sin estructura | Requiere campo proyecto. |

## Datos que requieren disciplina operativa

- Asesor asignado obligatorio en cada lead.
- Fuente/origen normalizado.
- Proyecto/desarrollo como campo estructurado, no texto libre.
- Etapas homologadas: nuevo lead, respondio, reunion, visita, negociacion, ganado/cierre, perdido.
- Valor de operacion y moneda si se espera facturacion.
- Motivo de perdida si se van a analizar perdidos.
- Nombres de campanas Meta con proyecto y formato reconocibles.


## Evidencia Kommo Dashboard - 2026-05-20

- Captura manual confirma acceso a `mariocastroteam.kommo.com/dashboard/`.
- Periodo visible: `01/04/2026 - 30/04/2026`.
- URL incluye `pipeline_id=13089748`, por lo que el dashboard permite filtrar por pipeline.
- Se ve filtro `Elija un usuario`.
- Widget `Leads por usuario`: total `5196`, Mery Faversani `4787`, Team Ventas 2025 `409`, Otros `0`.
- Widget `Fuentes de leads`: aparecen `MARKETING QUE CONSTRUYE`, `MARIO_CASTRO_REMAX` y `KYOMU PILAR`; no se ven conteos por fuente en la captura.
- Widgets de tareas visibles: tareas caducadas, tareas para completar, tareas completadas y leads sin tareas.
- No queda confirmado export CSV/XLSX ni detalle por lead.

## Evidencia Kommo Inbox - 2026-05-20

- Captura manual confirma vista de inbox/conversaciones dentro de Kommo.
- Se ve `ENTRADAS`, filtro `Chats abiertos`, badge `444` y `Total: 6924`.
- Hay buscador y configuracion.
- Cada item visible muestra contacto, badge tipo `A168105`, canal con icono WhatsApp o Instagram/Facebook, preview del ultimo mensaje y hora relativa.
- Se ven mensajes de `Salesbot` y mensajes de usuario, lo que puede ayudar a auditar respuesta.
- La lista es util como fuente secundaria para canal/respuesta, pero no deberia ser la fuente primaria masiva del Excel si existe export/listado de leads.
- Falta confirmar filtros por fecha/canal/asesor, fecha absoluta y exportacion.

## Evidencia Kommo Registro de Actividades - 2026-05-20

- Captura manual confirma `Analitica > Registro de actividades`.
- Se observa total `1789233 actividades`.
- Tabla con columnas `Fecha`, `Usuario`, `Objeto`, `Nombre`, `Actividades`, `Valor previo`, `Valor posterior`.
- Objetos visibles: `Conversacion`, `Contacto`, `Lead`.
- Eventos visibles: `Nuevo lead creado`, `Nuevo contacto creado`, `Mensaje entrante`, `Mensaje saliente`, `Conversacion comenzada`, `Conversacion cerrada`, `La etapa de ventas cambiada`, `Etiquetas agregadas`, `Lead eliminado`.
- Campos estructurados confirmados por eventos: `Fuente Lead`, `Emprendimi...`, `Telefono`, `Nombre`.
- Valores observados: fuente `Whatsapp MKT`; emprendimientos `Bonifacio`, `Chivilcoy`, `Jaramillo`; etapas `RESPONDIO SEGUI...`, `DERIVADOS NINA`, `seguimiento sin info`, `Ventas Perdidos`.
- Esta pantalla pasa a ser fuente candidata primaria para eventos historicos de Kommo, siempre que se confirme filtro/export o paginacion automatizable.
