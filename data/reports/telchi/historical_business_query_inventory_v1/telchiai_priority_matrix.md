# Prioridad para reutilizar conocimiento existente

La prioridad combina incidentes documentados y valor empresarial inferido. No se dispone de frecuencia de usuarios en producción; ocurrencias repetidas en fixtures/benchmarks no se consideran demanda observada.

| Orden | Familia | Evidencia de demanda / valor | Disponibilidad | Brecha que decide habilitación |
| --- | --- | --- | --- | --- |
| 1 | F09 cobertura temporal | Incidente de último mes; prerequisito de respuestas fiables | Census + MAX CURRENT verificado | Cobertura por métrica/entidad; separar parcial/completo |
| 2 | F08 últimos documentos | Incidente WhatsApp / batería HTTP | ORDER BY histórico + 10 headers CURRENT | Fecha/grano/status, scope y binding |
| 3 | F02 importes por período | Mayo/septiembre documentados; utilidad comercial inferida alta | SQL mensual y DocTotal mayo demostrado | Contrato monetario, NC, moneda, cobertura |
| 4 | F04 ventas por SKU | Incidente Calenta, catálogo productos | sales_by_item EXACT y CURRENT; mayo cuatro SKUs | Alias comercial y namespace; UoM/importe fuente |
| 5 | F03 ventas por cliente | CEO Q003/Q004; valor comercial inferido | SQL nativo EXACT y CURRENT | Identidad/alias y métricas compatibles; cantidades multi-SKU |
| 6 | F01 documentos/líneas | Prerrequisito transversal de drilldown | READY_FOUNDATION nativo | Binding y permisos; no ampliar scope |
| 7 | F11 stock actual | CEO + auditorías stock | 4 operaciones nativas reproducidas, stock_availability existente | UoM/as_of por SKU, permisos |
| 8 | F19 cobranzas | CEO + reglas settlement y publicación RC | Fact publicado y sample pinned; no reproducción de todas las preguntas | Pago vs componente/aplicación; moneda/fechas |
| 9 | F14 cadena compras | Auditorías profundas, universo/paridad ya construidos | 8 datasets de purchasing en manifest CURRENT; schemas verificados | Query empresarial delimitada, lineage, out_of_coverage |
| 10 | F07 rankings | Incidente y capability fija existente | SQL EXACT fuente y variante net units histórica | Definir «más»: unidades compatibles, importe, neto y universo |
| Posterior | F12/F13/F15/F16/F17/F18/F20/F21/F22/F23/F24/F25/F26 | Oportunidad operacional inferida, evidencia histórica amplia | Ver familias, matriz y baselines | Mapping/metric/source/historia; no repetir investigaciones cerradas |

## Selección de 5, 10 o 20 familias

La amplitud debe seguir los contratos ya acreditados; el número no mide por sí mismo valor ni seguridad semántica.

- **Primer paquete de 5:** cobertura, últimos documentos, período monetario explícito, SKU exacto y cliente exacto. Son candidatos; no los cinco READY de forma incondicional. Drilldown F01 es dependencia de implementación existente.
- **Llegar a 10:** sumar stock, cobranzas, compras, rankings definidos y drilldown. Reutilizar las publicaciones existentes y focalizar validación de cada query; no reingestar.
- **Llegar a 20:** exige completar mappings comerciales, unidades, historia de settlement/producción y métricas. No hay evidencia para prometer 20 familias inmediatamente habilitables.

En el registro directo se acreditaron 30 operaciones nativas portables técnicamente. La revisión clasifica **9 READY_FOUNDATION**, **8 READY_CONDITIONAL** y **13 REQUIRES_METRIC_DEFINITION**. READY se refiere a la operación nativa exacta, no a capability TelchiAI. El catálogo actual continúa siendo una única lectura documental fija.

No se crearon capacidades ni cambios en Luna, State Engine, Messaging, Srv05, Foundation o datos. La próxima etapa puede reutilizar este inventario para formalizar contrato/binding y validar un primer paquete acotado.
