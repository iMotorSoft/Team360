# Product monetary ranking V1

Contrato Development de ranking por importe comercial acumulado; no cambia Foundation, clasificación, SAP ni autorización compartida.

## Cambio mínimo de interpretación

El discriminador de operación `metric` admite `sales.product_line_amount_ranking`. No cambia el algoritmo del State Engine ni el significado de `sales.net_amount`.

- Operación: ranking; dimensión: producto SAP; medida: importe acumulado de líneas comerciales; orden: importe DESC, código SAP ASC. Son semántica fija del discriminador, publicada a Luna y en el resultado, nunca deducida del límite.
- Estado V2: `metric` y `requested_metrics=[metric]`, `limit` entero 1–50, categoría canónica en `entity_mention`, período semiabierto. REFINE conserva contexto pertinente; NEW_QUERY conserva su independencia.
- Capability: `sales.product_line_amount_ranking.v1`; permiso propio `telchi.sales.product_line_amount_ranking.read.v1`, resuelto exclusivamente por Console.
- V1 exige categoría acreditada; no hay universo general acreditado implícito. No soporta selecciones de búsqueda, sucursal, canal ni precio unitario. La proyección histórica admite producto objetivo y dos períodos independientes, sin filtrar el universo.
- Ambigüedad material: preguntar importe acumulado frente a precio unitario, sin ejecutar. En contexto monetario, «más vendidos por precio de venta» puede seleccionar el ranking de importes.
- Ordinales reutilizan exclusivamente referencias a resultados autorizados. No pasan a ser filtros persistentes ni códigos suministrados por Luna.

## Cálculo y auditoría

Reutilizar el contrato acreditado de [category line amount](../datalake/CATEGORY_LINE_AMOUNT_V1.md), sin convertir importes ni repartir cabeceras.

El reader agrega todas las líneas OINV/INV1 activas por producto con DECIMAL(38,6), verifica catálogo único y nombres publicados y concilia con el agregado de categoría en la misma sesión/snapshot. Tolerancia exacta cero; sólo después ordena y aplica Top N. Conserva desglose completo, hash, total, diferencia, conteos, cobertura y clasificación en el resultado auditable. El Top N no tiene que sumar el universo.

Un fallo de conciliación impide presentar ese ranking como verificado; conserva diagnóstico estructurado y explica qué requiere investigación. No elimina resultados independientes de otro período. La presentación no revela infraestructura ni permisos. Importes sin IVA de línea, antes de notas de crédito, descuentos propios incluidos; no neto documental, precio unitario ni cantidades físicas.

## Respuesta empresarial obligatoria

ANSWER_FIRST_WITH_EXCEPTIONS es el principio transversal Telchi: resultado acreditado, excepciones pertinentes, impacto e investigación. Su implementación inicial aquí es acotada al ranking, sin reescribir el asistente.

- Nunca fabricar cifras, posiciones, conversiones o clasificación; tampoco rebajar permisos o aislamiento para responder.
- Establecer unicidad, membresía y procedencia antes de excluir importes. Clasificación desconocida no acredita exclusión inocua; claves o joins no verificables no autorizan un ranking definitivo.
- El guard monetario controla todas las líneas de la categoría acreditada. Anomalías de otras categorías no contribuyen ni son facturas excluidas de este ranking; quedan separadas en auditoría.
- Monedas incompatibles internas: excluir esas líneas, conservar documento/número si publicado, producto, monedas y LineTotal original. No denominar LineTotal en la moneda de precio por inferencia. Agregar sólo operaciones verificadas en BS y conciliar exactamente ese subconjunto.
- Cualquier exclusión interna marca resultado parcial y posición potencialmente variable. V1 no implementa demostraciones de invariancia matemática; nunca declara una posición definitiva ante exclusiones.
- Si no quedan líneas verificadas, no asignar puesto ni ventas cero. Si la integridad impide cifras, explicar el motivo y la investigación necesaria sin inventar un importe sustituto.
- Las referencias ordinales simples no reutilizan una lista parcial omitiendo sus excepciones. No son una autorización para acceder a documentos originales adicionales.

## Posición histórica compatible

El mismo reader y permiso de ranking alimentan períodos independientes. La extensión añade sólo dos campos opcionales a los paths ya validados; no cambia el algoritmo de transición ni la semántica documental de otras métricas.

- `ranking_target_item_code`: código literal a localizar, separado de `entity_mention` (categoría). No es `selected_item_codes` ni una búsqueda por texto.
- `period` y `comparison`: dos intervalos independientes en esta operación, no un único intervalo fusionado ni un delta documental. Se hereda el año conocido, no el reloj. Sin año/categoría inequívocos corresponde aclarar.
- Para cada intervalo: universo, agregación completa, orden importe DESC/código ASC, conciliación, localización del objetivo. `limit` anterior sólo limita Top N, nunca el cálculo del puesto.
- Cada período conserva su resultado completo, cobertura, excepciones y acreditación. Un fallo de un mes no borra el otro. Ausencia del producto no acredita venta cero.
- `ranking_detail=exceptions`: presentación explícita de auditoría monetaria pertinente. Anomalías externas se distinguen de exclusiones internas; no se agregan a una respuesta ordinaria sin relevancia.
- La proyección histórica se persiste en la auditoría existente. Las repreguntas revalidan permisos y vuelven a ejecutar cada período; no agregan memoria horizontal ni grants. Diferencia monetaria local sólo entre dos resultados verificados; nunca entre parciales.

## Validación y aceptación

La aceptación requiere la comprobación manual del owner en la conversación WhatsApp persistida; las sondas HTTP no sustituyen esa comprobación.

Reproducir el estado auditado del incidente del 20/10/2026 13:56 ART en un hilo DEV nuevo, preservando el original. Separar replay de propuesta antigua, Luna real y persistencia PostgreSQL. Ejecutar A–E con reload, controles de autorización y conciliación Foundation. Reacreditar sólo garantías afectadas conforme a change_based_v1; nunca iniciar/reiniciar runtime ni enviar WhatsApp automáticamente.
