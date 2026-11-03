# Gates

Foundation `foundation_afd08d9eca6a725be53cdc3f9d5709c9`, snapshot **1408**, CURRENT efectivo confirmado; solo DEV y lectura. Sin SAP, modificaciones canónicas, reingestión, deploy ni cambio de modelo.

El flujo funcional Product Search → ItemCode → Sales Query está demostrado por HTTP y SQL independiente. El cierre global se mantiene PARTIAL por falta de UoM/factor físico de línea e importe neto por producto; no se fuerza semántica para conseguir PASS.

```text
TELCHI_PRODUCT_CATALOG_DISCOVERY=PASS
TELCHI_PRODUCT_SEARCH=PASS
TELCHI_PRODUCT_IDENTITY_CONTRACT=PASS
TELCHI_ITEMCODE_SALES_RELATION=PASS
TELCHI_CALENTA_PRODUCT_DISCOVERY=PASS
TELCHI_CALENTA_SALES_QUERY=PASS
TELCHI_SALES_BY_PRODUCTS=PASS
TELCHI_PRODUCT_PRESENTATIONS=PARTIAL
TELCHI_PRODUCT_LINE_AMOUNT_SEMANTICS=PARTIAL
TELCHI_PRODUCT_QUERY_RBAC=PASS
TELCHI_PRODUCT_QUERY_SQL_PARITY=PASS
TELCHI_PRODUCT_QUERY_HTTP_RUNTIME=PASS
TELCHI_PRODUCT_QUERY_CONTEXT=PASS
TELCHI_PRODUCT_QUERY_SECURITY=PASS
TELCHI_EXISTING_SALES_REGRESSION=PASS
TELCHI_PRODUCT_SEARCH_SALES_BY_ITEM_V1=PARTIAL
```

Validación: 200 tests focalizados; 19 casos de referencia; 25 turnos empresariales finales; negativos y reinicio HTTP. La denegación HTTP de identidad alternativa usa fixture, mientras los grants negativos Console son reales. Ver informes enlazados para no confundir esas garantías.

Sin commit/push/deploy. HEAD preservado: 09d2ec715a31bb88574d734eacb9f437f008624e. Cambios limitados a Telchi y su evidencia. Próximo paso: acreditar UoM física y contrato monetario de línea/NC, sin alterar Foundation en esta ejecución.
