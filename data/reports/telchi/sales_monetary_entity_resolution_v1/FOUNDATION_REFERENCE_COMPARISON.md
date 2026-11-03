# Foundation reference comparison

La referencia monetaria no reutiliza la función del servicio: agrupa fuente/moneda/cancelación por un SQL separado y coteja un segundo SELECT de cabeceras mediante sumas Decimal individuales.

- [foundation_reconciliation.json](foundation_reconciliation.json): SQL exacto, parámetros, filas agregadas, hashes de documentos y diferencias de cada grupo.
- [http_reference_comparison.json](http_reference_comparison.json): comparación de seis resultados del handler con esa referencia, período, documentos, NC y source binding.
- [luna_preflight.json](luna_preflight.json): llamada real OpenAI Responses, modelo/effort verificados y ausencia de fallback.

Se excluyen Y/C; NC activas se restan una vez; se mantiene BS. La consulta de servicio rechaza duplicados y montos faltantes, no sólo filas HTTP plausibles. No hay joins financieros que multipliquen cabeceras.

El cotejo acredita totales documentales y fidelidad semántica, no detalle fiscal no publicado, integridad de SAP actual, recepción histórica externa ni cierre empresarial completo. Los límites de Calenta y UoM se preservan. El guard no deja que una petición de neto por producto ejecute el total compañía.
