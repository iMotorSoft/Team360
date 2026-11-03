# Operational observations V1

Contrato offline `CAPTURED_OPERATIONAL_OBSERVATIONS_V1`, implementado en [operational_domains.py](operational_domains.py).

No sustituye ni rejuvenece los componentes históricos de negocio. Publicación exclusivamente mediante [Promotion canónico](SALES_FOUNDATION_PROMOTION_V1.md), CAS y journal existentes.

## Envelope y lectores

La sucesión usa `FOUNDATION_INDEPENDENT_FACTS_SUCCESSION_V1`, preservando ocho componentes y separando las observaciones nuevas de las métricas históricas.

El manifiesto conserva datasets, snapshots, permisos, Reference y ventas selladas; agrega `operational_observations`, vinculado por hash a la base, las capturas, schemas, archivos versionados y conciliación reproducible. Es una extensión de observaciones fuente, no una sustitución implícita de los contratos antiguos ni un noveno componente de métricas.

El validador vuelve a comprobar receipts, checkpoints, hashes, proyecciones fuente acreditadas, claves nativas y cada celda mediante replay bidireccional. Recalcula la conciliación; no confía en el informe del preparador. El reader verifica los bytes antes de exponer cada relación.

```python
# access se obtiene mediante FoundationReader, nunca construyendo un CURRENT.
orders = access.operational_observation("production", "production_order")
payments = access.operational_observation("collections", "collection_payment")
consumption = access.operational_observation(
    "material_supply", "observed_material_actual_consumption"
)
```

Los nombres y grupos permitidos están en `operational_domains.GROUPS`; no hay selección por glob/latest en readers. El journal canónico permite reentrada NOOP y recuperación sobre la misma candidata. Una futura revisión del solape requiere un adapter explícito: el preparador rechaza sobrescribir una observación anterior.

## Semántica y límites

Cada familia conserva su grain, cobertura y naturaleza; ninguna observación parcial habilita automáticamente una métrica global.

- Producción conserva órdenes, BOM y líneas de emisión, incluidas identidades desconocidas, cantidades/unidades nativas y cancelaciones. La evidencia BOM actual no acredita vigencia histórica. No hay receipts de producto terminado.
- Compras conserva snapshots documentales separados de OC, recepciones y AP. Una diferencia entre revisiones no demuestra su causa SAP ni una cancelación; no se inventan líneas ni se suman etapas. Los datasets legacy y su lineage mantienen su corte anterior.
- Cobranzas conserva pagos a cuenta, aplicaciones RCT2, conciliaciones y componentes de pago. Facturas/cuotas son observaciones de un prefijo; no certifican aging global ni reconstrucción histórica. No sumar el total de factura repetido por cuota.
- OINM conserva el prefijo observado, sin certificar cierre de ventana. El componente histórico sigue siendo el reader de continuidad acreditado; los movimientos nuevos no reconstruyen stock ni sustituyen ese componente.
- Material Supply rederiva únicamente consumo observado mediante `material_supply_derivation.build_actual_consumption`: emisiones activas BaseType 202, identidad OITM y orden capturadas, unidad nativa disponible, agrupación por producto/unidad/factor. Verifica la salida de seis decimales contra suma decimal fuente. No convierte unidades, no clasifica materia prima ni aplica BOM retrospectiva. Todos los hechos excluidos del derivado permanecen accesibles en la fuente.
- Los cinco datasets Material Supply históricos permanecen con sus dependencias/cortes originales, no ligados al stock nuevo. Pipeline, lead time, demanda equivalente y status no se anuncian refrescados por publicar estas observaciones.

## Integración conversacional

Dataset publicado, reader validado, capability implementada/habilitada y E2E son garantías distintas.

Este contrato no implementa ni habilita capabilities Luna, no cambia permisos ni prueba WhatsApp. Un consumidor futuro debe presentar primero el resultado empresarial y sus límites reales, no convertir falta de cobertura en cero ni responder con métricas históricas como actuales.
