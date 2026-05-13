# Team360 — Intents y campos operativos derivados de feedback público

Fecha de derivación: `2026-03-31`

## 1. Objetivo
- Traducir señal pública observable del seller `NETZAJ RACING` a un set mínimo de intents y campos operativos útiles para Team360.
- Alcance: solo evidencia pública ya relevada en publicaciones y opiniones/comentarios.
- Exclusión explícita: no se toca `team360_orquestador`, no se propone arquitectura nueva, no se asumen datos vendedor no visibles.

## 2. Evidencia base utilizada
- Fuente 1: análisis público general del seller.
- Fuente 2: muestra de `10` publicaciones activas.
- Hallazgos públicos relevantes:
  - `0/10` publicaciones con preguntas públicas visibles renderizadas en esta pasada.
  - `8/10` publicaciones con opiniones/comentarios visibles.
  - Lenguaje repetido en opiniones:
    - `buena iluminación`
    - `mejora la visibilidad`
    - `fácil de instalar`
    - `no encandila`
    - `práctico`
    - `útil para emergencias`
    - `se la banca`
    - `relación precio-calidad`

## 3. Lectura conservadora
- La mejor señal pública disponible hoy para este seller no viene de preguntas visibles, sino de feedback post-compra.
- Esa señal no valida por sí sola el flujo de pre-venta, pero sí permite identificar:
  - fricciones frecuentes
  - expectativas del comprador
  - atributos que el comprador usa para evaluar si el producto “sirve”
- Para Team360, esto alcanza para definir un set inicial de intents operativos, no para automatizar decisiones finales.

## 4. Intents operativos mínimos sugeridos

### 4.1 Compatibilidad
- Objetivo operativo:
  - determinar si el producto aplica al vehículo, uso o contexto real del comprador
- Señal pública que lo justifica:
  - repetición de compatibilidad técnica en títulos y descripciones
  - feedback que evalúa si el producto realmente sirve en uso concreto
- Preguntas tipo que Team360 debería poder absorber:
  - `va para mi auto/moto/camioneta`
  - `sirve para H4/H7/H11`
  - `me sirve para 12v o 24v`
  - `va para camioneta / cuatri / moto`

### 4.2 Rendimiento esperado
- Objetivo operativo:
  - alinear expectativa de potencia, visibilidad, velocidad o resultado real
- Señal pública que lo justifica:
  - comentarios sobre `buena iluminación`, `visibilidad`, `infla rápido`, `se la banca`
- Preguntas tipo:
  - `alumbra bien`
  - `cuánto tarda en inflar`
  - `sirve para uso exigente`
  - `es mejor que halógena`

### 4.3 Instalación / adaptación
- Objetivo operativo:
  - detectar si el comprador necesita algo plug-and-play o tolera adaptación
- Señal pública:
  - comentarios sobre `fácil de instalar`
  - riesgo técnico visible por fichas, conectores y variantes
- Preguntas tipo:
  - `es plug and play`
  - `hay que adaptar`
  - `qué ficha lleva`
  - `entra por medida`

### 4.4 Confiabilidad / durabilidad
- Objetivo operativo:
  - capturar dudas sobre resistencia, duración y uso intensivo
- Señal pública:
  - comentarios sobre duración incierta o desempeño sostenido
- Preguntas tipo:
  - `cuánto dura`
  - `aguanta uso seguido`
  - `se banca camioneta / ruta / off-road`

### 4.5 Valor percibido / cierre
- Objetivo operativo:
  - resolver si la compra cierra por precio, conveniencia y confianza
- Señal pública:
  - comentarios sobre `relación precio-calidad`
  - reputación pública del seller y volumen de opiniones
- Preguntas tipo:
  - `conviene por lo que vale`
  - `hay stock`
  - `llega mañana`
  - `qué garantía tiene`

## 5. Priorización sugerida
- Prioridad 1:
  - `compatibilidad`
  - `rendimiento_esperado`
- Prioridad 2:
  - `instalacion_adaptacion`
  - `valor_percibido_cierre`
- Prioridad 3:
  - `confiabilidad_durabilidad`

## 6. Campos operativos mínimos

### 6.1 Núcleo común
- `linea_producto`
- `tipo_producto`
- `vehiculo_o_contexto`
- `marca_modelo_año`
- `variante_tecnica`
- `voltaje`
- `conector_o_formato`
- `uso_principal`

### 6.2 Campos para rendimiento
- `expectativa_rendimiento`
- `nivel_exigencia`
- `problema_actual`

### 6.3 Campos para instalación
- `requiere_plug_and_play`
- `tolera_adaptacion`
- `medida_o_espacio`

### 6.4 Campos para cierre
- `urgencia_entrega`
- `sensibilidad_precio`
- `duda_principal`

## 7. Set mínimo operativo sugerido para Team360
```json
{
  "seller_public_id": "netzajracing",
  "source": "public_feedback_only",
  "priority_intents": [
    "compatibilidad",
    "rendimiento_esperado",
    "instalacion_adaptacion",
    "valor_percibido_cierre",
    "confiabilidad_durabilidad"
  ],
  "minimum_fields": [
    "linea_producto",
    "tipo_producto",
    "vehiculo_o_contexto",
    "marca_modelo_año",
    "variante_tecnica",
    "voltaje",
    "conector_o_formato",
    "uso_principal",
    "expectativa_rendimiento",
    "requiere_plug_and_play",
    "urgencia_entrega",
    "duda_principal"
  ],
  "confidence": {
    "compatibilidad": "media",
    "rendimiento_esperado": "media-alta",
    "instalacion_adaptacion": "media",
    "valor_percibido_cierre": "media",
    "confiabilidad_durabilidad": "media-baja"
  },
  "limitations": [
    "sin preguntas reales visibles en la muestra",
    "sin acceso vendedor",
    "derivado mayormente de comentarios post-compra",
    "no valida todavia flujo conversacional pre-venta completo"
  ]
}
```

## 8. Qué sí haría Team360 con esto
- Clasificar la consulta entrante en uno de los intents prioritarios.
- Pedir solo los campos mínimos necesarios para reducir ambigüedad.
- Evitar respuestas genéricas cuando falten datos críticos como variante, conector o vehículo.

## 9. Qué no haría todavía Team360 con esto
- No decidir compatibilidad final sin datos mínimos del comprador.
- No asumir que el lenguaje de opiniones reemplaza preguntas reales de pre-venta.
- No convertir todavía esto en normalización rígida, telemetría compleja o cambios del orquestador.

## 10. Próximo paso conservador recomendado
- Si querés seguir en esta línea sin tocar runtime ni orquestador, el siguiente paso lógico es crear un borrador mínimo de `playbook conversacional` por intent con:
  - pregunta de apertura
  - datos mínimos a pedir
  - condición de no-respuesta
  - condición de derivación humana
