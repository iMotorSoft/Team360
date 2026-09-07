# TELCHI SAP — INVENTARIO: PROFORMAS, PRICING Y CATEGORÍAS

**Fecha:** 2026-08-23
**Estado:** FASE 0 - INVENTARIO INICIAL

---

## 1. UNIVERSO DE PROFORMAS

### 1.1 Tabla: OQUT (Header)

| Métrica | Valor |
|---------|-------|
| Total proformas | 158,799 |
| Activas (N) | 157,392 |
| Canceladas (Y) | 1,407 |
| Primera fecha | 2022-04-05 |
| Última fecha | 2026-08-23 |

### 1.2 Tabla: QUT1 (Líneas)

- **Total columnas:** 368
- **Campos clave:**
  - `DocEntry` - ID proforma
  - `LineNum` - Número de línea
  - `ItemCode` - Código de producto
  - `Dscription` - Descripción
  - `Quantity` - Cantidad
  - `Price` - Precio unitario
  - `GTotal` - Total línea
  - `DiscPrcnt` - Porcentaje de descuento
  - `GPBefDisc` - Precio bruto antes de descuento
  - `PriceBefDi` - Precio antes de descuento
  - `SpecPrice` - Precio especial (flag)
  - `BaseEntry`, `BaseType`, `BaseLine` - Referencia a otros documentos

---

## 2. VINCULACIÓN PROFORMA → FACTURA

### 2.1 Mecanismo de Vinculación

- **Field:** `INV1.BaseEntry = OQUT.DocEntry`
- **BaseType:** 23 (Quotation/Proforma)

### 2.2 Estadísticas

| Métrica | Valor |
|---------|-------|
| Facturas con referencia a proforma | 84,887 |
| Líneas vinculadas | 276,308 |

### 2.3 Cambios de Precio (Proforma → Factura)

| Comparación | Pares | Dif. Promedio |
|-------------|-------|---------------|
| **MISMO PRECIO** | **78,015** | **$0.00** |
| MAYOR en factura | 4,643 | +$56.80 |
| MENOR en factura | 2,232 | -$137.88 |

**89.5% de las proformas mantienen el mismo precio en la factura.**

### 2.4 Cambios de Descuento (Proforma → Factura)

| Comparación | Líneas | Dif. Prom. Desc% |
|-------------|--------|------------------|
| **MISMO DESCUENTO** | **275,707** | **0.00%** |
| MAYOR descuento en factura | 566 | +6.69% |
| MENOR descuento en factura | 35 | -5.44% |

**99.7% de las líneas mantienen el mismo descuento.**

---

## 3. DISTRIBUCIÓN DE DESCUENTOS EN PROFORMAS

| Bucket | Líneas | Monto |
|--------|--------|-------|
| 0% (sin descuento) | 583,023 | $392,967,798.19 |
| 1-5% | 8,229 | $6,310,022.28 |
| 6-10% | 6,127 | $4,445,731.38 |
| 11-15% | 1,106 | $1,640,159.48 |
| 16-20% | 524 | $684,223.64 |
| **20%+** | **5,139** | **$1,245,566.46** |

**5,139 líneas (0.9%) tienen descuento superior al 20%.**

---

## 4. CATEGORÍAS DE CLIENTES

### 4.1 U_CATCLIENTE (Categoría Cliente)

| Categoría | Clientes |
|-----------|----------|
| NULL | 9,148 |
| **A** | **3,768** |

### 4.2 U_CANAL_VENTAS (Canal de Ventas)

| Canal | Clientes |
|-------|----------|
| NULL | 6,744 |
| 2 | 2,619 |
| 1 | 2,133 |
| 6 | 567 |
| 8 | 355 |
| 3 | 344 |
| 7 | 125 |
| 4 | 22 |
| 5 | 7 |

### 4.3 U_TIPOCLIENTE (Tipo Cliente)

| Tipo | Clientes |
|------|----------|
| NULL | 9,239 |
| DMS | 3,672 |

### 4.4 Discount (Descuento Permitido)

| Desc% | Clientes |
|-------|----------|
| 3% | 1 |
| 5% | 378 |
| 7% | 1 |
| 8% | 5 |
| 10% | 178 |
| 11% | 2 |
| 15% | 1 |

**565 clientes tienen un descuento permitido configurado.**

---

## 5. HALLAZGOS INICIALES

### 5.1 Descuentos en Proformas

- **93.7%** de líneas no tienen descuento (0%)
- **6.3%** de líneas tienen algún descuento
- **0.9%** de líneas tienen descuento >20%

### 5.2 Cambios Proforma → Factura

- **89.5%** mantienen el mismo precio
- **5.3%** aumentan el precio (cliente paga más)
- **2.5%** disminuyen el precio (cliente paga menos)
- **99.7%** mantienen el mismo descuento porcentual

### 5.3 Descuentos Excedidos

Hay **566 líneas** donde el descuento en la factura es **MAYOR** que en la proforma:
- Descuento promedio adicional: **+6.69 puntos porcentuales**
- Algunos casos muestran **0% en proforma → 50% en factura**

### 5.4 Categorías

- Solo existe categoría **"A"** en U_CATCLIENTE
- No hay una política de descuento clara por categoría
- El campo `Discount` en OCRD tiene valores (3%, 5%, 7%, 8%, 10%, 11%, 15%)

---

## 6. PRÓXIMOS PASOS

1. **Investigar la política de descuento por categoría**
2. **Validar si U_CATCLIENTE = "A" es la única categoría**
3. **Investigar los 566 casos de descuento excedido**
4. **Vincular descuento con margen**
5. **Crear contratos analíticos**

---

## 7. ARCHIVOS CREADOS

```
docs/proforma_pricing_inventory.md (este documento)
```

---

**Telchi SAP — Inventario: Proformas, Pricing y Categorías — V1**
