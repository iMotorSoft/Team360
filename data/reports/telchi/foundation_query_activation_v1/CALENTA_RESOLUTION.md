# Calenta Resolution

Brecha delimitada, no alias nuevo. Evidencia sellada del inventario reutilizada al comprobar CURRENT 1408; no se declaró una marca, familia o cliente único por semejanza textual.

## Identificadores acreditados

Reference SAP_HANA contiene estos productos. Las dos presentaciones KG son SellItem=N; las demás no prueban por sí solas finalidad comercial externa.

| SKU | ID canónico Reference | Descripción original | SellItem |
| --- | --- | --- | --- |
| L02822 | product_c01355844d4a04e756e3d426 | CALENTA (POMADA SALICILATO DE METILO) x 250 g. | Y |
| L02823 | product_2058b9550c8d045285843703 | CALENTA (POMADA SALICILATO DE METILO) x 30 g | Y |
| L02877 | product_53c02537638f3720672e2106 | CALENTA x Kg. | N |
| L03035 | product_c5b392632b964746307f00f7 | CALENTA (MEDIAN GROUP)  x 50 g | Y |
| L03648 | product_4ef3b41af6a510bd00e57d62 | CALENTA FORTE x Kg. | N |
| L03649 | product_b3a849a9f81829397835bcfa | CALENTA FORTE x 30 g | Y |
| L03650 | product_70a4e5edb55198184748f7de | CALENTA FORTE x 50 g | Y |
| L03658 | product_d02ab393831a50690c22dabc | CALENTA FORTE  x 250 g. | Y |

## Relación que falta

La igualdad de claves físicas y la equivalencia de namespaces son garantías distintas. No se añadió un join correctivo ni un crosswalk sin provenance.

Atomic sales_line/sales_document: `source_system=SAP_B1_HANA`. Reference products: `source_system=SAP_HANA`, clave `item_code`, ID `canonical_product_id`. Falta una relación publicada y autorizada que mapee `(SAP_B1_HANA, item_code)` a `(SAP_HANA, item_code, canonical_product_id)` con evidencia de equivalencia y unicidad.

La sonda `may_calenta_native_lines` une namespaces literalmente y retorna vacío. La sonda `calenta_exact_skus_may`, por SKU exacto, demuestra filas. Ese vacío **no** demuestra ausencia de ventas.

Aliases en `entity_aliases`: PRODUCT con `alias_source=reference.products:SAP_HANA`; hay AMBIGUOUS para Calenta 30 g y KG y MAPPED para determinadas presentaciones Forte. Un alias de presentación MAPPED no acredita una familia Calenta/Forte conjunta. Brand sigue UNKNOWN; customers no tuvo matches en la sonda, no prueba inexistencia universal de un cliente.

LIKE también encuentra INCUBADORA...CALENTADOR y Horno de CALENTAMIENTO en otros namespaces. Es discovery, no resolución ni filtro autorizado.

## Ventas documentadas por SKU

Resultados históricos de mayo CURRENT 1408, no nuevos resultados HTTP. Cantidades nativas por SKU y LineTotal fuente; UoM de catálogo no sustituye unidad/factor de línea.

| SKU | Quantity fuente | LineTotal fuente | Moneda | Cancelación |
| --- | --- | --- | --- | --- |
| L02822 | 1568.0000000000 | 63287.9600000000 | BS | N |
| L02823 | 3472.0000000000 | 24889.6500000000 | BS | N |
| L03649 | 2125.0000000000 | 18487.3900000000 | BS | N |
| L03658 | 785.0000000000 | 43082.5200000000 | BS | N |

Referencias: HQ-fbdda4165b64b30810 / HS-56822a0ce444d328eb; `foundation_business_cases.json` del inventario, sondas calenta_products/calenta_aliases/calenta_exact_skus_may. El detalle original se conserva en [comparación](foundation_comparison.json).

TQ04/TQ12 mantienen la mención sin inventar tipo, ID, familia ni ventas cero. Estado REQUIRES_MAPPING; además no existe grant de consulta por SKU/entidad. Próximo paso: crosswalk namespace con provenance, selección comercial explícita y contrato documental UoM antes de publicar un alias familiar.
