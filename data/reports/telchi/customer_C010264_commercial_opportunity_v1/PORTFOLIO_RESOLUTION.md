# Resolución focalizada de portfolio — L&S

Resultado PROVISIONAL con evidencia transaccional verificada. No se promovieron indicios a pertenencia propia ni se modificaron catálogos, Foundation o memoria.

## Fuentes revisadas y límites

La revisión selectiva buscó evidencia comercial, titularidad, clasificación empresarial y fabricación para terceros. No se encontró un catálogo autorizado ni aprobación ItemCode de los productos frontera en las fuentes inspeccionadas.

- Baseline completo: todos los JSON/CSV/Markdown fueron leídos y parseados; SQL_EVIDENCE.json conserva 26 consultas/resultados. Compras del cliente reutilizadas, no reconstruidas; el cotejo nuevo devuelve sólo frecuencia para validar continuidad.
- Reference publicado: products y crosswalks de tipo y portfolio de v2_reference_closure_2088d5885204313a; mismos IDs y snapshot 1408. Se reutilizan evidencia/BOM/producción conservadas en clasificación, sin reingestión.
- Investigación datalake_product_business_classification_v1 y kernel product_business_classification.py: reglas combinadas grupo/BOM/producción; prueban naturaleza, no titularidad.
- PRODUCT_COMMERCIAL_SEMANTICS_V1.md y fuente-gap: ventas/uso mixto no equivalen a marca; brand UNKNOWN y neto monetario por producto sin resolver. No se leen candidates como si fueran CURRENT.
- TELCHI_DATALAKE_REFERENCE_V2_REBUILD_AND_RECONCILIATION_V1.md: portfolio provisional; relaciones propietario, marca, fabricante vacías; white-label representable pero no identificado.
- ADR-026/027/029 en TELCHI_DATALAKE_ADR_INDEX_V1.md: fabricación, propiedad y portfolio independientes. La ausencia de white-label identificado no acredita que no exista.
- la_reja_c010341_operational_identity_v1_report.md: describe fraccionados propios y documenta L00505. Es evidencia contextual derivada para otro cliente, no una aprobación de pertenencia individual aplicable al Top 20. No se convierte en CONFIRMED.
- delivery_analysis_conclusion.md: nombra varios artículos Litel pero traza entregas, no titularidad. Descripciones explícitas se conservan como indicio, no regla de confirmación.
- Búsqueda selectiva de nombres catálogo/marca/portfolio/PDF/XLSX en módulo, reports y Data Root: no surgió una lista comercial autorizada pertinente; no se escanearon todos los Parquet ni se consultó SAP/legacy externo.

## Universo exploratorio reproducible

Uc no es U acreditado. Se define para una comparación preliminar amplia y para detectar la frontera sin asumir prefijos como prueba de pertenencia.

Uc incluye ItemCodes con factura activa real en la ventana y, además, portfolio publicado LITEL provisional O tipo LAB_FINISHED_PRODUCT/FRACTIONATED_PRODUCT/RAW_MATERIAL/OTHER_INPUT/SEMI_FINISHED con estado VALIDATED/SUPPORTED.

La segunda vía evita limitarse al prefijo L o sólo terminados. En la vía portfolio se mantienen otros tipos/UNKNOWN como incertidumbre, no como pertenencia confirmada. Servicios con tipo SERVICE se excluyen de oportunidades de producto; comprobar su presencia en frontera es parte de la validación.

CANDIDATE_TELCHI_LITEL requiere indicio estructural/master no NAME_BASED más venta documentada; sin ese indicio, UNKNOWN. Ninguno se marca CONFIRMED_TELCHI_LITEL ni CONFIRMED_THIRD_PARTY: no hay evidencia suficiente para esas decisiones. No se infiere tercero por marca aislada.

PRODUCT_MEMBERSHIP_EVIDENCE.csv documenta ItemCode, decisión, confianza, fuente, evidencia, conflictos y exclusión del ranking certificado. Es un resultado analítico local, no un dato maestro. U acreditado es no resuelto, no un conjunto vacío probado.

## Ranking y documentación

La frecuencia cuenta DocEntry distinto, namespace SAP_B1_HANA, OINV/INV1, canceled=N, DocDate >= 2026-01-01 y < 2026-09-25. No filtra moneda porque no suma importes.

Joins por namespace y DocEntry; el catálogo se une después de agregar por ItemCode. Mismo Uc y período para global y L&S. Las NC son contexto separado y no se restan de una frecuencia de ocurrencias. No es venta neta por producto. Presentación es una subcadena literal de la descripción, sin conversiones ni fusiones.

## Frontera y sensibilidad

El ranking completo se calcula antes de limitar a 20; EXPLORATORY_TOP100.csv entrega 100 posiciones para reemplazos. GLOBAL_SOLD_PRODUCT_EVIDENCE.json conserva todos los 6.581 productos vendidos y sus frecuencias.

Uc contiene 915 productos; tipos: {'FRACTIONATED_PRODUCT': 250, 'LAB_FINISHED_PRODUCT': 339, 'RAW_MATERIAL': 58, 'PACKAGING': 60, 'TRADED_PRODUCT': 79, 'OTHER_INPUT': 129}. Incluye 19 códigos no L. El Top 20 actual sí corresponde a elaborados/fraccionados; esto es un resultado observado, no una restricción.

Corte global 4186, siguiente 4081, máximo excluido de Uc 2006: ningún excluido puede desplazar a los 20 SI los 20 son propios confirmados. Todos están sin confirmar, por lo que el estado no es CERTIFIED.

La shortlist tiene 36 artículos: primera ola de 11 para oportunidades A/B, resto para unión Top20 global/cliente y 5 reemplazos. Si hay exclusiones, ampliar selectivamente a los siguientes y recalcular; no basta confirmar sólo A/B para certificar rankings.

Una incorporación A mantiene ausencia de compra por ItemCode cualquiera sea U. Si se acredita pertenencia del artículo A actual, su Top20 se sostiene porque no hay omitidos que lo superen y excluir anteriores sólo lo sube. B puede pasar al Top20 cliente si se excluyen suficientes candidatos anteriores; la shortlist señala la cantidad mínima.

## Validación independiente y reproducción

FINAL_SQL_EVIDENCE.json contiene SQL completo y comparación global join vs semijoin, binding y hashes de inputs. FINAL_VALIDATION.json contiene SQL independiente de row_number y anti/intersección sobre los hechos capturados, resultados y controles.

Se verifican 20 posiciones distintas por ranking, A sin compras, B comprado fuera del Top20, C fuera de A/B/G sin compras, coherencia de ItemCode y orden. Los resultados de pertenencia no son PASS certificado; la validación de datos no resuelve autoridad empresarial.

Para reproducir, ejecutar los SELECT registrados en FINAL_SQL_EVIDENCE.json usando FoundationReader en sesión READ_ONLY y los límites de recursos indicados. Luego ejecutar independent_rank_sql e independent_complement_sql de FINAL_VALIDATION.json con DuckDB y los JSON/CSV conservados. Las rutas absolutas son las del worktree actual.
