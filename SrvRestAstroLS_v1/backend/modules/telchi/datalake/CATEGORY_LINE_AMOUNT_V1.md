# Importe registrado en líneas por categoría V1

Contrato DEVELOPMENT implementado en DEV. LineTotal y moneda BS acreditados por la investigación IVA; registro scoped pendiente, sin activación ni promoción. La conciliación incompleta no bloquea esta métrica.

## Semántica y frontera

La capability horizontal `sales.category_line_amount.v1` suma exclusivamente el campo publicado de líneas comerciales acreditadas, nunca el total de cabecera asignado a una categoría.

- Métrica: `SUM(INV1.LineTotal)` de OINV activas `N`, por DocDate en intervalo semiabierto y categoría actual validada. Nombre visible: «Importe registrado en líneas comerciales»; nunca «facturación neta por categoría».
- Sin notas de crédito restadas, producción, cantidades físicas sumadas, conversión de moneda, prorrateo de cabeceras ni compensación artificial del residuo.
- Facturas mixtas: el filtro de categoría afecta sólo líneas. El total documental y su diferencia son referencias del universo completo, no importes atribuibles a la categoría.
- Clasificación actual no historizada: mostrar esa limitación. Distinguir cobertura de join de calidad VALIDATED/SUPPORTED/PROVISIONAL/UNKNOWN; no descartar silenciosamente líneas de menor calidad.
- La acreditación SAP/OADM y paridad Raw/Foundation está en la investigación IVA. El worker admite sólo BS con acreditación heredada mediante la [sucesión canónica](SALES_FOUNDATION_PROMOTION_V1.md#sucesión-incremental-y-acreditación-comercial) y crosswalk acreditado. Un cambio de identidad de publicación no cambia la semántica; cambiar ésta o el crosswalk exige un contrato explícito.

## Entrada y salida

El servicio existente debe conservar identidad y autorización fuera del SQL, con parámetros tipados y procedencia verificable. No se crea un motor conversacional paralelo.

| Entrada | Contrato |
| --- | --- |
| category | Código canónico de `product_business_type`, nunca búsqueda textual por nombre de producto |
| date_from / date_to_exclusive | ISO, intervalo semiabierto acotado; sin elegir año desde el reloj |
| currency | Denominación de LineTotal acreditada; sin usar automáticamente moneda del precio/documento |
| identity/context | Identidad autenticada, tenant/workspace/módulo y autorización efectiva vigente; no del LLM |

| Salida | Contrato |
| --- | --- |
| amount / currency / definition | Decimal como string finito, moneda y definición versionada; sin redondear cada línea |
| document_count / line_count / product_count | Granos documentales exactos, sin duplicación por crosswalk |
| classification | Versión de clasificación, reference publicada, hash, cobertura y desglose de calidad |
| period / coverage | Ventana solicitada y fechas observadas; no certificar cierre mensual por data_as_of |
| source | publication_id, snapshot_id, component lineage y fecha de actualización |
| warnings | No neto contable; clasificación actual; diferencia con cabeceras no atribuida |
| credit_notes | Componente separado sólo si acreditado; nunca restarlo implícitamente |

Sin filas no significa cero de negocio cuando la cobertura temporal no está certificada. Faltantes, duplicados, monedas desconocidas o linaje incompatible deben fallar explícitamente, no convertirse en cero.

## Relación e integridad

FoundationReader resolverá una sola publicación y snapshot; la operación debe validar claves y denominación antes de agregar, no filtrar inconsistencias para ocultarlas.

- Relación: `source_system=SAP_B1_HANA`, par tipado OINV/INV1 y `doc_entry`; línea por `(source_system,source_table,doc_entry,line_num)`. ORIN/RIN1 se investiga separadamente.
- Cabecera única, línea única y crosswalk ItemCode único dentro del namespace SAP correspondiente. Controlar huérfanos, cabeceras sin líneas, valores nulos/no monetarios, captura y source_as_of.
- Crosswalk actual aplicado a la publicación de referencia resuelta; no cargar una versión más reciente por conveniencia.
- La igualdad entre DocCur e INV1.Currency no prueba por sí sola denominación: la evidencia SAP/OADM acredita BS local. El worker rechaza períodos con monedas documentales/precio incompatibles, sin filtrarlas ni convertirlas silenciosamente.
- Se aceptan membresías VALIDATED o SUPPORTED, explicando estas últimas; PROVISIONAL/UNKNOWN bloquean el importe de la categoría. Integridad y cobertura de join se verifican antes de agregar.

## Acceso y Presidencia

El diseño conserva FULL_ACCESS técnico scoped y Presidencia empresarial como contratos diferentes. No introduce privilegios por nombre, email, título ni texto emitido por Luna.

- Permiso específico implementado, NO registrado: `telchi.sales.category_line_amount.read.v1`. Requiere registrar y habilitar la capability en el catálogo scoped mediante ventana autorizada; FULL_ACCESS vigente la resolvería sin nuevos grants individuales al piloto. Esta implementación no modifica permisos persistidos ni el resolver.
- No reutilizar el permiso de facturación global para ampliar silenciosamente su alcance. Usuarios normales necesitan el permiso específico y la delegación empresarial vigentes.
- Presidencia requiere un perfil Console de lectura Telchi, con idénticos permisos efectivos para las dos identidades confirmadas por el owner. No inferir identidades ni asignarlas por nombres. No concede gestión de usuarios, escritura, privilegios globales ni FULL_ACCESS técnico.
- La inspección local DEV no encontró perfiles ni roles de Presidencia. Se requiere asignación coordinada Console/Auth para definir el perfil y sus permisos; este contrato no modifica el resolver compartido ni aplica migraciones/grants.
- Revalidar autorización en cada consulta y seguimiento; revocación, aislamiento y auditoría deben usar el mecanismo existente. Identificadores completos sólo en auditoría o drill-down necesario.

## Presentación y garantías pendientes

El importe abre la respuesta; los límites explican la métrica sin ocultarla por falta de conciliación completa. Comparaciones reutilizan resultados auditados compatibles en moneda, período, cobertura, clasificación, fuente y definición.

Formato previsto: categoría y período → importe registrado en líneas → productos/líneas/documentos y cobertura → clasificación actual y actualización → advertencia sobre cabeceras/NC/cobertura parcial. No insertar cifras diagnósticas fijas en runtime.

La [validación DEV](../../../../../data/reports/telchi/category-sales-monetary-v1/report.md) acredita cálculo real, segunda categoría, Luna y tests focalizados. Acceso efectivo del piloto y seis gates siguen bloqueados por registro pendiente. Presidencia queda fuera de esta tarea; la explicación semántica no expone otros importes ni ejecuta drill-down documental.

La [evidencia investigativa](../../../../../data/reports/telchi/category-line-amount-reconciliation-v1/report.md) conserva cifras, decisiones, limitaciones y comandos. El [contexto canónico](../CONTEXT.md) mantiene arquitectura, roots y etapas.
