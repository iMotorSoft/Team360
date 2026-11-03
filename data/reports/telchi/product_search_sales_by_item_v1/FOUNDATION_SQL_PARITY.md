# Foundation SQL parity

Foundation `foundation_afd08d9eca6a725be53cdc3f9d5709c9`, snapshot **1408**, CURRENT efectivo confirmado; solo DEV y lectura. Sin SAP, modificaciones canónicas, reingestión, deploy ni cambio de modelo.

Diecinueve casos SQL/servicio cotejados con lecturas independientes: catálogo completo SAP, líneas por códigos y cabeceras por claves, merge y orden en Python, cantidades Decimal. No se utiliza SQL ni output del servicio para construir las filas esperadas.

Casos: Calenta completo, mayo, cada una de las diecisiete coincidencias de palabra, incluidos vacíos. Se verifican claves naturales, unicidad, cobertura, fechas, orden, cantidades, conteos completos, no duplicación y binding 1408. UoM de línea no existe: no se finge equivalencia física.

10 resultados HTTP de líneas coinciden con expected independiente y conteos completos. [Referencia](foundation_reference.json), [paridad HTTP](http_reference_comparison.json). Regresiones monetarias de mayo/junio derivadas del contrato previo acreditado; no importe por producto.
