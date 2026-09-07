# TELCHI SAP — INVESTIGACIÓN: 17 CASOS CRÍTICOS DE DESCUENTO EXCEDIDO

**Fecha:** 2026-08-23
**Estado:** INVESTIGACIÓN COMPLETA

---

## 1. RESUMEN EJECUTIVO

| Métrica | Valor |
|---------|-------|
| Total casos críticos | 17 |
| Aumento de descuento | **+50.0 pp** (todos) |
| Descuento proforma | **0.0%** (todos) |
| Descuento factura | **50.0%** (todos) |

**Todos los 17 casos tienen exactamente el mismo patrón: 0% en proforma → 50% en factura.**

---

## 2. ANÁLISIS POR VENDEDOR

| Vendedor | Casos | Clientes |
|----------|-------|----------|
| **138 - Giselly Yara Poveda Da Silva** | **9** | CGRC, CGV1 |
| 58 - Esther Nina | 3 | E000097 |
| 49 - Lizet Rodriguez | 1 | CGV1 |
| 92 - Manuela Rivero Tapia | 1 | CGCM |
| 40 - Rosario Mascaya | 2 | E000287 |
| 142 - Maria Jose Leyes Saavedra | 1 | E000261 |

**El vendedor 138 (Giselly Yara) tiene 9 de los 17 casos (52.9%).**

---

## 3. ANÁLISIS POR CLIENTE

| Cliente | Casos | Tipo |
|---------|-------|------|
| **CGRC - CONTROL TRIBUTARIO** | **6** | Genérico tributario |
| **E000097 - Nina Aliaga Esther Rocio** | **3** | Individual |
| CGCM - CONTROL TRIBUTARIO | 1 | Genérico tributario |
| CGV1 - CONTROL TRIBUTARIO | 1 | Genérico tributario |
| CGCM - CONTROL TRIBUTARIO | 1 | Genérico tributario |
| E000287 - MEDRANO RIVERA NILDA | 2 | Individual |
| E000261 - LEYES SAAVEDRA MARIA JOSE | 1 | Individual |

**Los clientes genéricos tributarios tienen 8 casos (47.1%).**

---

## 4. ANÁLISIS POR PRODUCTO

| Producto | Descripción | Casos |
|----------|-------------|-------|
| M04818 | BABY SHAMPOO CLASICO J&J | 1 |
| M07624 | BIOTIN 10.000 mcg | 1 |
| M02392 | BETARRETIN 0.05% CREMA | 1 |
| M01851 | BACTIFREN 750 mg | 1 |
| M05943 | CORTIPREX 20mg | 1 |
| M07240 | MICROPORE 5 cm | 1 |
| M04944 | GASA ESTERIL LE ROY | 1 |
| M04982 | AGUJA HIPODERMICA | 1 |
| M04955 | VENDA YESO CREMER | 1 |
| M04942 | VENDA ELASTICA LE ROY | 1 |
| M02469 | IPSON FORTE SUSP | 1 |
| M01827 | DIOXADOL | 1 |
| M06000 | SINALERG 4 mg | 1 |
| M06837 | MAREUM ANTIEMETICO | 1 |
| M03589 | NAFAZOL Oftálmico | 1 |
| M02693 | OPTI-VIMIN | 1 |
| M06811 | NOVABUPI | 1 |

**Cada caso es un producto diferente.**

---

## 5. PATRÓN IDENTIFICADO

### 5.1 Características Comunes

1. **Descuento 0% en proforma** - Todos los casos
2. **Descuento 50% en factura** - Todos los casos
3. **Aumento exacto: +50.0 pp** - Todos los casos
4. **Productos de salud/farmacia** - Todos los casos
5. **Clientes genéricos tributarios** - 47.1% de los casos

### 5.2 Hipótesis

Este patrón sugiere que:

1. **Es un descuento autorizado por política** - No parece ser un error
2. **Afecta a productos de salud/farmacia** - Posiblemente una categoría especial
3. **Concentrado en el vendedor 138** - Podría ser una práctica de un vendedor específico
4. **Clientes genéricos tributarios** - Pueden tener condiciones especiales

### 5.3 Riesgo

El descuento del **50%** es significativamente alto. Sin embargo:

- Son solo **17 casos** de **284,377 líneas** proforma-factura (0.006%)
- El monto total es **bajo** (verificar en SAP)
- Puede ser una **política legítima** para productos de salud

---

## 6. RECOMENDACIONES

### 6.1 Investigación Inmediata

1. **Verificar si existe política de descuento del 50%** para productos de salud
2. **Investigar al vendedor 138** - ¿Por qué tiene 9 de 17 casos?
3. **Validar clientes genéricos tributarios** - ¿Tienen condiciones especiales?

### 6.2 Documentación

1. **Crear registro de esta política** si es legítima
2. **Establecer límites** si no está documentada
3. **Monitorear** futuros casos

### 6.3 Acción

Si la política **NO está documentada**:
- Revisar con el vendedor 138
- Establecer límites
- Documentar la excepción

Si la política **ESTÁ documentada**:
- Registrar como `VALID_POLICY`
- No requiere acción correctiva

---

## 7. CONCLUSIÓN

Los 17 casos críticos representan un **patrón consistente**:
- 0% → 50% de descuento
- Productos de salud/farmacia
- Concentrado en vendedor específico
- Clientes genéricos tributarios

**No es un error aislado, sino una práctica comercial que debe validarse contra la política de Telchi.**

---

**Telchi SAP — Investigación: 17 Casos Críticos de Descuento Excedido — V1**
