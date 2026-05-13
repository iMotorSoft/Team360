# Team360 — Análisis seller público Mercado Libre

## 1. Resumen ejecutivo
- El seller público `netzajracing` fue detectado y expone un catálogo con dominancia observable en accesorios vehiculares, especialmente iluminación LED, tuning y accesorios para moto/auto/camioneta.
- El valor para Team360 es alto para modelar intents conversacionales de compatibilidad, variante técnica, instalación y cierre comercial en un contexto de venta técnica de accesorios.
- Limitaciones: no hay acceso vendedor, no hay histórico de preguntas reales del seller, y parte de la lectura depende de HTML público precargado y publicaciones públicas visibles; cualquier dato no visible queda no validado.

## 2. Evidencia observable
- Seller page detectada: sí. URL pública detectada: `https://www.mercadolibre.com.ar/pagina/netzajracing`.
- Señales públicas del seller visibles en HTML público de la seller page:
  - `NETZAJ RACING`
  - tipo `seller`
  - estado `active`
  - `owner_id` expuesto: `73847302`
  - `search_url` pública asociada a la página del vendedor
  - `+210 seguidores`
- Señales comerciales públicas visibles asociadas al seller:
  - `MercadoLíder Platinum`
  - `+5mil ventas` en publicaciones públicas más antiguas
  - `+1000 ventas` en publicaciones públicas activas visibles en resultados recientes
- Categorías o líneas visibles en la seller page:
  - `Accesorios para Vehículos`
  - `Acc. para Motos y Cuatriciclos`
  - `Tuning`
  - `Accesorios de Auto y Camioneta`
  - `Seguridad Vehicular`
  - También aparecen públicamente: `Celulares y Teléfonos`, `Juegos y Juguetes`, `Bebés`, `Deportes y Fitness`, `Equipamiento para Camping`, `Linternas y Faroles`
- Ejemplos concretos de publicaciones asociadas:
  - `Faro Led Auxiliar 24w 8 Led Off Road 4x4 Moto Agro 12-24v`
    - `https://articulo.mercadolibre.com.ar/MLA-1135471401-faro-led-auxiliar-24w-8-led-off-road-4x4-moto-agro-12-24v-_JM`
  - `Barra Led Recta 240w 80 Led 105cm Cuatri 4x4 Agro Tractor`
    - `https://articulo.mercadolibre.com.ar/MLA-1128240892-barra-led-recta-240w-80-led-105cm-cuatri-4x4-agro-tractor-_JM`
  - `Juego Faros Luz Led Moto Running Blanca Y Luz De Giro Ambar`
    - `https://articulo.mercadolibre.com.ar/MLA-1459466829-juego-faros-luz-led-moto-running-blanca-y-luz-de-giro-ambar-_JM`
  - `Kit Cree Led Csp Sapphire Super Canbus Iron 75w + 2 T10 Iron`
    - `https://articulo.mercadolibre.com.ar/MLA-1511539601-kit-cree-led-csp-sapphire-super-canbus-iron-75w-2-t10-iron-_JM`
  - `Traba Candado U Oregon Llave Horquilla Piton 180x245mm Motos`
    - `https://articulo.mercadolibre.com.ar/MLA-1477694317-traba-candado-u-oregon-llave-horquilla-piton-180x245mm-motos-_JM`
- Publicaciones visibles directamente en la seller page pública:
  - `Compresor De Aire Mini Encendedor Portátil Oregon Com007 144w Negro`
  - `Compresor De Aire Oregon Inflador Ruedas 150psi Portatil Frecuencia 1500 Mhz`
  - `Kit Cree Led Canbus No Da Error Alta Gama H1 H7 H11`
  - `Kit Cree Led H4 Canbus Csp Proyector Lupa Premium 40000 Lm H4`
  - `Barra Curva 300w 100 Leds 130cm C/soporte Camioneta 4x4`
  - `Interruptor Tecla Basculante Universal 12v / 24v - 3 Pin Color Rojo`
- Frases comerciales repetidas visibles:
  - `SOMOS NETZAJ RACING VENTAS POR MAYOR Y MENOR`
  - variante visible en otras publicaciones: `SOMOS NETZAR RACING VENTAS POR MAYOR Y MENOR`
  - `NUEVO INGRESO`
  - `incluye ... de regalo`
  - `compatible con DRL`
  - `Cancela error de lámpara quemada`
  - `Elegir el deseado en las variantes de la publicación`
- Atributos técnicos visibles repetidos:
  - voltaje `12v` y `12-24v`
  - potencia en `w`: `24w`, `75w`, `240w`, `300w`
  - tecnologías `LED`, `CSP`, `CANBUS`
  - conectores o variantes `H1`, `H4`, `H7`, `H11`, `T20 7443`
  - temperatura/color de luz: `6.500 K`, `Blanco`, `Blanco frío`, `Ambar`
  - compatibilidad declarada con `motos`, `cuatriciclos`, `auto`, `camioneta`, `4x4`, `agro`, `tractor`
  - resistencia/protección visible: `IP67`, resistencia a `impactos`, `corrosión`, `agua` y `lodo`
  - medidas visibles: `105cm`, `130cm`, `145*40 mm`, `10mm`

## 3. Inferencias razonables
- Dominio principal del seller: accesorios vehiculares, con foco observable en iluminación LED y accesorios técnicos para auto, moto, cuatriciclo y 4x4.
- Familias de producto probables:
  - kits LED automotor y moto
  - barras y faros auxiliares LED
  - giro/running y señalización
  - seguridad vehicular para moto
  - compresores e infladores portátiles 12V
  - accesorios auxiliares de instalación o tuning
- Subdominios secundarios probables:
  - camping/utilitarios livianos
  - catálogo oportunista generalista con juguetes/bebés
- Tipo de venta probable:
  - principalmente técnica
  - orientada a reposición y upgrade
  - con componente minorista fuerte
  - con mayorista probable por declaración pública del seller, pero volumen mayorista real no validado
- Tipo de preguntas probables del comprador:
  - compatibilidad con vehículo, año y ficha
  - diferencia entre variantes técnicas
  - instalación y necesidad de adaptaciones
  - potencia, color, alcance o tipo de luz
  - stock, tiempos de entrega, garantía y devolución
- Riesgos de compatibilidad o devolución:
  - error de ficha o encastre
  - error de voltaje `12v` vs `24v`
  - incompatibilidad `CANBUS`
  - falta de espacio físico o medida incorrecta
  - expectativa incorrecta sobre color o potencia de iluminación
  - universalidad asumida en publicaciones para moto o auto
  - instalación no plug-and-play en algunos vehículos

## 4. Intents conversacionales probables para Team360
- Compatibilidad
  - sirve para mi vehículo
  - va para marca/modelo/año
  - qué ficha o base necesita
  - es para `12v`, `24v` o ambos
  - cancela error de lámpara quemada
  - aplica a moto, auto, camioneta, cuatri o tractor
- Variante técnica
  - qué diferencia hay entre `H1/H4/H7/H11/T20`
  - qué color de luz trae
  - cuántos watts o leds tiene
  - qué medida tiene
  - cuál variante tengo que elegir en la publicación
  - trae balasto, cooler, soporte o accesorios
- Instalación / uso
  - es plug and play o hay que adaptar
  - sirve para running, giro o DRL
  - cómo se instala
  - es resistente al agua o al barro
  - sirve para uso off-road o trabajo
- Comercial / cierre
  - hay stock
  - llega mañana
  - hacen precio por cantidad
  - venden por mayor
  - qué garantía tiene
  - si no va, cómo se resuelve el cambio o devolución

## 5. Campos mínimos para calificar una consulta
- `linea_producto`
- `tipo_producto`
- `vehiculo_tipo`
- `marca_modelo_año_version`
- `voltaje_requerido`
- `ficha_o_conector`
- `medida_o_espacio_disponible`
- `variante_deseada`
- `uso_o_problema_a_resolver`
- `urgencia_o_contexto_de_entrega`

## 6. Datos faltantes / límites del análisis
- No validado: mix real de ventas por familia de producto.
- No validado: cuáles son las preguntas más frecuentes reales del inbox o de la bandeja vendedor.
- No validado: tasa real de devoluciones, reclamos o incompatibilidades.
- No validado: stock real, rotación y prioridad comercial por SKU.
- No validado: si las categorías de juguetes/bebés son núcleo de negocio o catálogo secundario circunstancial.
- No validado: política real de facturación, descuentos mayoristas y márgenes.
- No validado: performance operativa del seller en respuesta conversacional.
- Límite técnico: la seller page usa render dinámico; parte de la evidencia salió de HTML público con estado precargado y parte de publicaciones públicas visibles.
- Límite metodológico: no se hizo scraping masivo ni extracción exhaustiva de catálogo, por decisión conservadora.

## 7. JSON conceptual sugerido
```json
{
  "seller_public_id": "netzajracing",
  "seller_name": "NETZAJ RACING",
  "dominant_domain": "accesorios vehiculares con foco en iluminacion LED y tuning tecnico",
  "category_clusters": [
    "accesorios para vehiculos",
    "accesorios para motos y cuatriciclos",
    "tuning",
    "accesorios de auto y camioneta",
    "seguridad vehicular",
    "camping y utilitarios livianos",
    "catalogo secundario generalista no validado"
  ],
  "frequent_attributes": [
    "12v",
    "12-24v",
    "LED",
    "CSP",
    "CANBUS",
    "H1/H4/H7/H11/T20",
    "6500K",
    "blanco frio",
    "ambar",
    "24w/75w/240w/300w",
    "IP67",
    "105cm/130cm"
  ],
  "commercial_language": [
    "ventas por mayor y menor",
    "nuevo ingreso",
    "incluye de regalo",
    "compatible con DRL",
    "cancela error de lampara quemada",
    "elegir variante en la publicacion"
  ],
  "priority_intents": [
    "compatibilidad vehiculo-producto",
    "seleccion de variante tecnica",
    "instalacion y adaptacion",
    "stock y cierre comercial",
    "garantia y devolucion por incompatibilidad"
  ],
  "minimum_qualification_fields": [
    "linea_producto",
    "tipo_producto",
    "vehiculo_tipo",
    "marca_modelo_año_version",
    "voltaje_requerido",
    "ficha_o_conector",
    "medida_o_espacio_disponible",
    "variante_deseada",
    "uso_o_problema_a_resolver",
    "urgencia_o_contexto_de_entrega"
  ],
  "confidence": {
    "overall": "media",
    "dominant_domain": "alta",
    "priority_intents": "media",
    "secondary_catalog": "baja-media"
  },
  "limitations": [
    "sin acceso vendedor",
    "sin historial real de preguntas",
    "sin validacion de mix de ventas",
    "seller page con render dinamico",
    "analisis basado solo en evidencia publica visible"
  ]
}
```

## 8. Recomendación para próximo paso
- Próximo paso conservador: tomar entre `8` y `12` publicaciones públicas activas del seller, priorizando `iluminación LED` y `accesorios vehiculares`, y relevar manualmente solo `preguntas públicas visibles`, variantes y atributos repetidos.
- Objetivo de ese paso: validar intents reales y campos mínimos de calificación antes de tocar `team360_orquestador`, sin scraping masivo y sin sumar arquitectura nueva.
