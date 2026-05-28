# Analisis del Excel de KPIs CEO

Archivo analizado: `docs/clients/mario_castro/KPIs_CEO_Proyectos_Inmobiliarios_COMPLETO.xlsx`

## Hojas detectadas

| Hoja | Rango | Uso observado |
|---|---:|---|
| KPIs CEO Proyectos | A1:C51 | Catalogo de 50 KPIs mensuales. |
| Carga Asesores | A1:T7 | Carga mensual por asesor y formulas de conversion/objetivos. |
| Pautas Publicitarias | A1:Q8 | Carga de campanas, formatos, inversion, impresiones, clics, leads y rankings. |
| Fuentes y Desarrollos | A1:L17 | Fuentes de leads y ranking de desarrollos. |
| Dashboard CEO | A1:L19 | Vista consolidada con formulas hacia las hojas de carga. |

## Campos principales por hoja

| Hoja | Campos principales | Observacion |
|---|---|---|
| Carga Asesores | Mes, Asesor, Leads, Respondieron, Reuniones, Objetivo Reuniones, Visitas, Negociaciones, Cierres, Seguimientos, Recuperados, Facturacion USD, Objetivo USD | Debe alimentarse principalmente desde Kommo, mas objetivos manuales si no existen en CRM. |
| Pautas Publicitarias | Mes, Campana, Proyecto, Formato, Inversion USD, Impresiones, Clics, Leads, Leads Respondidos, Reuniones | Debe alimentarse desde Meta Ads y cruzarse con Kommo para respondidos/reuniones. |
| Fuentes y Desarrollos | Mes, Fuente, Leads, Respondieron, Reuniones, Inversion USD, Desarrollo, Visitas, Reservas/Cierres | Debe alimentarse con Kommo, Meta Ads y calculo local. |
| Dashboard CEO | Totales, rankings, conversiones y objetivos | Hoja de salida calculada. |

## Formulas observadas

- Conversion Lead-Reunion: `Reuniones / Leads`.
- Conversion Reunion-Visita: `Visitas / Reuniones`.
- Conversion Visita-Cierre: `Cierres / Visitas`.
- Conversion Lead-Cierre: `Cierres / Leads`.
- CPL: `Inversion / Leads`.
- CPC: `Inversion / Clics`.
- CTR: `Clics / Impresiones`.
- Costo por Reunion: `Inversion / Reuniones`.
- Rankings con `RANK(...)`.
- Totales con `SUM(...)`.

Nota tecnica: en algunas filas de ejemplo las formulas referencian la fila anterior, incluso encabezados en la primera fila de datos. Antes de generar el Excel productivo conviene corregir o regenerar la plantilla para evitar formulas desplazadas.

## Matriz KPI

| KPI | Hoja | Campo/Columna | Tipo | Fuente probable | Comentario |
|---|---|---|---|---|---|
| Leads Totales Ingresados | KPIs CEO Proyectos / Carga Asesores | Carga Asesores: Leads | Externo | Kommo | Contar leads creados por periodo. Requiere fecha y filtros consistentes. |
| Ranking de Fuentes de Leads | KPIs CEO Proyectos / Fuentes y Desarrollos | Fuente, Leads | Calculo local | Kommo / Facebook / Meta Ads | Requiere campo fuente normalizado. |
| Costo por Lead (CPL) | KPIs CEO Proyectos / Pautas Publicitarias | Inversion USD, Leads, CPL | Calculo local | Meta Ads | Mejor desde export Meta Ads; calcular local para consistencia. |
| Leads Calificados | KPIs CEO Proyectos | No hay columna directa | Externo | Kommo | Requiere etapa, etiqueta o campo de calificacion. No confirmado. |
| Cantidad de Leads que Respondieron | KPIs CEO Proyectos / Carga Asesores | Respondieron | Externo | Kommo / Facebook Inbox | Depende de poder identificar respuesta efectiva. |
| Leads Perdidos | KPIs CEO Proyectos | No hay columna directa | Externo | Kommo | Requiere etapa perdido o motivo de perdida. |
| Inversion Publicitaria Total Mensual | KPIs CEO Proyectos / Pautas Publicitarias | Inversion USD | Externo | Meta Ads | Priorizar descarga CSV/XLSX. |
| Reuniones Generadas Totales del Equipo | KPIs CEO Proyectos / Carga Asesores | Reuniones | Externo | Kommo | Requiere etapa o tarea de reunion. |
| Reuniones Generadas por Asesor | KPIs CEO Proyectos / Carga Asesores | Asesor, Reuniones | Externo | Kommo | Requiere asesor asignado. |
| Visitas Realizadas Totales del Equipo | KPIs CEO Proyectos / Carga Asesores | Visitas | Externo | Kommo | Requiere etapa/tarea de visita. |
| Visitas Realizadas por Asesor | KPIs CEO Proyectos / Carga Asesores | Asesor, Visitas | Externo | Kommo | Requiere asesor asignado. |
| Negociaciones Abiertas Totales del Equipo | KPIs CEO Proyectos / Carga Asesores | Negociaciones | Externo | Kommo | Debe mapearse a etapa del pipeline. |
| Negociaciones Abiertas por Asesor | KPIs CEO Proyectos / Carga Asesores | Asesor, Negociaciones | Externo | Kommo | Depende de etapa y responsable. |
| Cierres Realizados Totales del Equipo | KPIs CEO Proyectos / Carga Asesores | Cierres | Externo | Kommo | Requiere etapa ganado/reserva/cierre. |
| Cierres Realizados por Asesor | KPIs CEO Proyectos / Carga Asesores | Asesor, Cierres | Externo | Kommo | Depende de responsable y periodo. |
| Conversion General del Equipo | KPIs CEO Proyectos / Dashboard CEO | Conv. Lead-Cierre | Calculo local | Calculo local | Cierres / Leads. |
| Conversion Individual por Asesor | KPIs CEO Proyectos / Carga Asesores | Conv. Lead-Cierre | Calculo local | Calculo local | Cierres por asesor / leads por asesor. |
| Conversion Lead -> Visita del Equipo | KPIs CEO Proyectos | Leads, Visitas | Calculo local | Calculo local | Visitas / Leads. |
| Conversion Lead -> Visita por Asesor | KPIs CEO Proyectos | Leads, Visitas, Asesor | Calculo local | Calculo local | Requiere base Kommo por asesor. |
| Conversion Visita -> Cierre del Equipo | KPIs CEO Proyectos / Carga Asesores | Conv. Visita-Cierre | Calculo local | Calculo local | Cierres / Visitas. |
| Conversion Visita -> Cierre por Asesor | KPIs CEO Proyectos / Carga Asesores | Asesor, Conv. Visita-Cierre | Calculo local | Calculo local | Cierres por asesor / visitas por asesor. |
| Leads Asignados Totales | KPIs CEO Proyectos / Carga Asesores | Leads | Externo | Kommo | Similar a leads totales si todos tienen asesor. |
| Leads por Asesor | KPIs CEO Proyectos / Carga Asesores | Asesor, Leads | Externo | Kommo | Requiere responsable asignado. |
| Ranking General de Asesores | KPIs CEO Proyectos / Dashboard CEO | Ranking de asesores | Calculo local | Calculo local | Definir criterio: reuniones, cierres, facturacion o score mixto. |
| Facturacion Total del Equipo | KPIs CEO Proyectos / Carga Asesores | Facturacion USD | Externo | Kommo / Manual | Solo si Kommo guarda valor de operacion. |
| Facturacion por Asesor | KPIs CEO Proyectos / Carga Asesores | Asesor, Facturacion USD | Externo | Kommo / Manual | Requiere valor y responsable. |
| Seguimientos Totales del Equipo | KPIs CEO Proyectos / Carga Asesores | Seguimientos | Externo | Kommo | Requiere tareas/actividades registradas. |
| Seguimientos Realizados por Asesor | KPIs CEO Proyectos / Carga Asesores | Asesor, Seguimientos | Externo | Kommo | Depende de disciplina operativa. |
| Seguimientos Recuperados Totales | KPIs CEO Proyectos / Carga Asesores | Recuperados | Externo | Kommo | Requiere campo o etapa de recuperacion. |
| Seguimientos Recuperados por Asesor | KPIs CEO Proyectos / Carga Asesores | Asesor, Recuperados | Externo | Kommo | No confirmado sin inspeccion. |
| Ranking de Desarrollos Mas Demandados | KPIs CEO Proyectos / Fuentes y Desarrollos | Desarrollo, Leads | Calculo local | Kommo | Requiere proyecto/desarrollo estructurado. |
| Ranking de Desarrollos Menos Demandados | KPIs CEO Proyectos / Fuentes y Desarrollos | Desarrollo, Leads | Calculo local | Kommo | Requiere proyecto/desarrollo estructurado. |
| Valor Promedio m2 Vendido | KPIs CEO Proyectos | No hay columna directa | Calculo local | Kommo / Manual | Requiere superficie y valor vendido. No confirmado. |
| Ticket Promedio | KPIs CEO Proyectos | No hay columna directa | Calculo local | Kommo / Manual | Facturacion / cierres. |
| Velocidad de Absorcion | KPIs CEO Proyectos | No hay columna directa | Calculo local | Manual / no definido | Requiere stock/unidades vendidas por periodo. |
| Tiempo Promedio de Cierre | KPIs CEO Proyectos | No hay columna directa | Calculo local | Kommo | Requiere fecha de alta y fecha de cierre. |
| Ranking de Leads por Desarrollo | KPIs CEO Proyectos / Fuentes y Desarrollos | Desarrollo, Leads | Calculo local | Kommo | Requiere desarrollo normalizado. |
| CTR | KPIs CEO Proyectos / Pautas Publicitarias | Impresiones, Clics, CTR | Calculo local | Meta Ads | Clics / impresiones. |
| CPC | KPIs CEO Proyectos / Pautas Publicitarias | Inversion USD, Clics, CPC | Calculo local | Meta Ads | Inversion / clics. |
| ROI de Marketing | KPIs CEO Proyectos | No hay columna directa | Calculo local | Meta Ads + Kommo | Requiere facturacion atribuible por campana/fuente. |
| Conversion por Fuente | KPIs CEO Proyectos / Fuentes y Desarrollos | Fuente, Leads, Reuniones | Calculo local | Kommo / Meta Ads | Reuniones o cierres por fuente / leads por fuente. |
| Ranking de Pautas por Formato | KPIs CEO Proyectos / Dashboard CEO | Formato, Ranking | Calculo local | Meta Ads | Requiere formato consistente en campana o export. |
| Facturacion Mensual Total | KPIs CEO Proyectos / Dashboard CEO | Facturacion USD | Externo | Kommo / Manual | Depende de valor de operacion. |
| Comision Total Generada | KPIs CEO Proyectos | No hay columna directa | Calculo local | Manual / no definido | Requiere regla de comision. |
| CAC | KPIs CEO Proyectos | No hay columna directa | Calculo local | Meta Ads + Kommo | Inversion / clientes/cierres. |
| Facturacion Proyectada | KPIs CEO Proyectos | No hay columna directa | Calculo local | Manual / no definido | Requiere pipeline ponderado o regla comercial. |
| Objetivo Mensual Total del Equipo | KPIs CEO Proyectos / Carga Asesores | Objetivo Reuniones, Objetivo USD | Manual | Manual / no definido | Podria cargarse manual o desde Kommo si existe. |
| Objetivo Mensual por Asesor | KPIs CEO Proyectos / Carga Asesores | Asesor, Objetivos | Manual | Manual / no definido | Requiere fuente de objetivos. |
| Diferencia entre Objetivo y Resultado del Equipo | KPIs CEO Proyectos / Dashboard CEO | Diferencias | Calculo local | Calculo local | Resultado - objetivo. |
| Diferencia entre Objetivo y Resultado por Asesor | KPIs CEO Proyectos / Carga Asesores | Diferencias por asesor | Calculo local | Calculo local | Resultado por asesor - objetivo por asesor. |
