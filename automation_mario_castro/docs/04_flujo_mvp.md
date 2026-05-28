# Flujo MVP recomendado

## Objetivo

Generar automaticamente una copia del Excel de KPIs CEO desde datos descargados o leidos por browser automation, sin APIs y sin depender todavia de scraping complejo.

## Bloque 1 - Kommo

Datos a buscar:

- Leads totales.
- Leads por asesor.
- Respondieron.
- Reuniones.
- Visitas.
- Negociaciones.
- Cierres.
- Perdidos.
- Facturacion si existe valor de operacion.
- Fuente.
- Proyecto/desarrollo.

Flujo propuesto:

1. Login con `kommo.login_probe`.
2. Reutilizar `storage_state`.
3. Abrir `Analitica > Registro de actividades`.
4. Aplicar rango mensual o confirmar mecanismo de filtro/export.
5. Extraer eventos: `Nuevo lead creado`, `Cambio en el campo Fuente Lead`, `Cambio en el campo Emprendimiento`, `La etapa de ventas cambiada`, `Mensaje entrante`, `Mensaje saliente`.
6. Usar dashboard como control agregado por periodo, pipeline y usuario.
7. Usar Inbox como fuente secundaria para canal/respuesta.
8. Si el registro no exporta, leer tabla/paginacion y muestrear tarjetas para validar campos.
9. Mapear etapas reales a KPIs: nuevo, respondio, reunion, visita, negociacion, cierre, perdido.

## Bloque 2 - Meta Ads

Datos a buscar:

- Campana.
- Formato.
- Proyecto.
- Inversion.
- Impresiones.
- Clics.
- Leads.
- CTR.
- CPC.
- CPL.

Flujo propuesto:

1. Login con `facebook.login_probe`.
2. Abrir Ads Manager.
3. Confirmar cuenta publicitaria correcta.
4. Aplicar rango mensual.
5. Seleccionar columnas necesarias.
6. Descargar reporte CSV/XLSX.
7. Procesar localmente y normalizar campana/proyecto/formato.

## Bloque 3 - Facebook Page / Inbox

Uso en MVP:

- Confirmar permisos administrativos.
- Verificar si hay mensajes que no llegan a Kommo.
- Auditar origen de conversaciones si Kommo no lo trae limpio.

No recomendado como fuente principal si Kommo ya concentra conversaciones.

## Bloque 4 - Calculos locales

Calculos a generar fuera del browser:

- Conversion lead a reunion.
- Conversion reunion a visita.
- Conversion visita a cierre.
- Conversion lead a cierre.
- Costo por lead.
- Costo por reunion.
- Ranking asesores.
- Ranking campanas.
- Ranking desarrollos.
- CAC.
- ROI si hay atribucion confiable entre gasto y facturacion.

## Salida

1. Crear una copia del workbook base.
2. Actualizar hojas de carga: `Carga Asesores`, `Pautas Publicitarias`, `Fuentes y Desarrollos`.
3. Dejar que `Dashboard CEO` se alimente desde formulas.
4. Guardar evidencia de fuentes usadas y timestamp del reporte.

## Criterios para avanzar a automatizacion final

- Kommo permite obtener leads por rango mensual sin bloqueo.
- Se confirma campo de asesor.
- Se confirma campo/etapa para reuniones, visitas, negociaciones, cierres y perdidos.
- Se confirma campo de fuente y proyecto/desarrollo.
- Ads Manager permite descarga o lectura estable de campanas.
- Las campanas tienen nomenclatura suficiente para proyecto/formato.
- Se define que metricas quedan manuales por falta de fuente.
