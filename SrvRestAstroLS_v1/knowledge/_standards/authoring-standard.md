# Authoring Standard

Reglas editoriales para documentos fuente knowledge de Team360.

## Principios

- Escribir para retrieval, no para presentacion comercial.
- Separar hechos validados, hipotesis, limites y decisiones pendientes.
- Declarar alcance: que cubre, que no cubre y cuando requiere revision humana.
- Evitar contenido ambiguo que pueda convertirse en promesa comercial.
- No duplicar el mismo contenido entre global, paquete y caso particular.
- Mantener el Markdown como fuente canonica.

## Estructura recomendada

Todo documento fuente debe tener:

1. Frontmatter YAML.
2. Titulo H1.
3. Resumen L0.
4. Alcance.
5. Contenido principal en secciones cortas.
6. Limites de uso.
7. Referencias o evidencia.
8. Historial de cambios.

## Redaccion

- Usar encabezados descriptivos y estables.
- Mantener parrafos cortos.
- Preferir listas cuando enumeran reglas, criterios o decisiones.
- Evitar frases de marketing sin evidencia.
- Usar identificadores tecnicos en metadata, no en copy visible.
- Usar nombres comerciales solo cuando el documento trate experiencia visible.

## Contenido sensible

No incluir:

- passwords;
- tokens;
- API keys;
- credenciales de terceros;
- datos personales innecesarios;
- datos reales de clientes sin anonimizar;
- instrucciones para evadir MFA, controles anti-bot o autorizaciones.

## Identificadores

- `package_code`, `knowledge_scope_code`, `assistant_instance_code`,
  `service_code` y `template_code` son identificadores tecnicos.
- Nombres comerciales como `Vera / Asistente Inteligente Vera` son display/copy.
- No crear identificadores tecnicos `vera_*`.

## Promesas y limites

Un documento puede explicar que algo es automatizable sin declararlo vendible
hoy. La metadata debe separar:

- automatizable;
- vendible ahora;
- piloto;
- oportunidad futura;
- revision humana requerida.
