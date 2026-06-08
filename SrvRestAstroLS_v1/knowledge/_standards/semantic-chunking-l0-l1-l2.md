# Semantic Chunking, L0, L1 y L2

Preparacion documental para una futura etapa con SemanticChunker.

Este documento define criterios editoriales. No implementa chunking runtime ni
embeddings.

## Niveles

| Nivel | Funcion | Uso |
|---|---|---|
| L0 | Resumen ejecutivo o abstract semantico del documento. | Identificar tema, alcance y limites rapido. |
| L1 | Secciones principales con ideas completas. | Recuperacion semantica estable para preguntas frecuentes. |
| L2 | Detalle granular, ejemplos, reglas, tablas o excepciones. | Grounding fino y respuestas con evidencia puntual. |

## Criterios L0

- Debe existir cerca del inicio.
- Debe explicar tema, alcance, audiencia y limite principal.
- Debe evitar promesas comerciales amplias.
- Debe mencionar si el documento es global, de paquete o de caso particular.

## Criterios L1

- Cada H2 debe representar una unidad semantica fuerte.
- Evitar H2 genericos como "Otros" o "Varios".
- Cada seccion debe poder recuperarse sin depender de todo el documento.
- Los limites, riesgos y HITL deben tener secciones propias cuando sean relevantes.

## Criterios L2

- Usar H3 para reglas, ejemplos, matrices o excepciones.
- Mantener tablas pequenas y con encabezados claros.
- Separar ejemplos de politicas normativas.
- No esconder restricciones importantes en parrafos largos.

## Preparacion para SemanticChunker

Los documentos deben facilitar cortes semanticos naturales:

- una idea por parrafo;
- listas con items autocontenidos;
- encabezados que incluyan el concepto buscable;
- metadata completa;
- `node_path` estable;
- referencias claras a evidencia y limites.

## Criterios de chunk util

Un chunk util debe conservar:

- tema;
- regla o afirmacion;
- condicion de uso;
- limite o riesgo si aplica;
- referencia a paquete/scope mediante metadata, no repitiendo texto en exceso.

## Lo que no debe hacer el documento

- No depender de imagenes para explicar reglas criticas.
- No mezclar varias decisiones no relacionadas bajo el mismo encabezado.
- No usar copy comercial como reemplazo de evidencia.
- No declarar capacidades futuras como capacidades productivas.
