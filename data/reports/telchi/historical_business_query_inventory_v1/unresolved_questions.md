# Preguntas y garantías pendientes

La falta de asociación completa queda explícita; no se llena con resultados ni equivalencias inferidas. El detalle por registro permanece en CSV.

| Pregunta / garantía | Causa | Conocimiento existente que debe conservarse |
| --- | --- | --- |
| ¿Cuántos intents empresariales diferentes investigamos en total? | 1.398 redacciones lexicalmente diferentes no equivalen a intents; títulos/rótulos requieren adjudicación semántica y deduplicación | questions_master + family_membership, sin eliminar variantes |
| ¿Cuántas consultas históricas se ejecutaron en todo el corpus? | 30 operaciones y 70 ocurrencias SQL acreditadas estrictamente; muchos scripts/gates aún sin enlace SQL→resultado granular | evidence_index, historical_findings y 116 gates del inventario SAP previo |
| ¿Cuántas preguntas adicionales a las 30 tienen cadena completa? | Los 19 baselines y reportes acreditan resultados históricos, pero no se atribuyó automáticamente cada cifra a un SQL exacto | historical_findings.csv conserva cifra, período, reglas y fuente |
| Neto comercial general de mayo/septiembre | DocTotal, LineTotal y neto tras NC no equivalen; imponer métrica aprobada | Contrato financiero, executive_sales, SQL mensual |
| Últimas ventas «registradas» | DocDate no demuestra timestamp de registro/ingestión | Discovery histórico y lista documental CURRENT |
| Últimas ventas de Calenta como familia | Aliases ambiguos, namespaces distintos, Forte/presentación/internos y coincidencias falsas por LIKE | SKUs, aliases y resultados mayo sin suma de unidades |
| Último mes completo por entidad | MAX documental no certifica completitud ni calendario empresarial | Census/source_as_of/manifest |
| Cantidad global y ranking universal | Faltan factores/documentary UoM compatibles; orden documental no magnitud física | Source quantities, contratos UoM, candidatos sidecar |
| Ventas por sucursal/canal horizontal | Warehouse, branch, vendedor y canal transaccional no equivalen | Sales dimensions, crosswalks y reglas comerciales históricas |
| Deuda histórica al día de venta | Eventos settlement/NC/cancelación y vencimiento efectivos; saldo publicado no sustituye historia | SQL financial/as-of y excepciones crédito |
| Aprobación de crédito / permisos históricos | Configuración no prueba decisión; historia autorizaciones insuficiente | Credit control y auditoría users |
| Consumo real usando sólo BOM vigente | BOM planificada no evidencia emisión real histórica | OWOR/IGE1/IGN1/OINM e investigaciones producción |
| Forecast/demanda perdida actual | Censura por stockout y ventanas parciales; backtests históricos no predicción nueva | Reportes seasonality/replenishment, sin benchmarks de modelos |
| Nómina detallada, GL completo y treasury actual | No acreditados en Foundation publicada | Reportes financieros/historical-only |
| Datasets externos gzip | Metadata/hash inventariados; contenido fila a fila excluido; cadena documental no debe usar valores no leídos | 37 rutas gzip y reports fuente preservados |

Las interrogantes con SQL dinámico no reconstruido y asociaciones débiles conservan UNRESOLVED. No se considera completa la auditoría semántica de toda la historia, aunque el recorrido físico de investigation sí está acreditado.
