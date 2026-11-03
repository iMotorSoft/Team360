# Contratos empresariales

Aprendizajes L&S incorporados como contratos y fixtures de propagación, no como reglas publicadas. La correcta respuesta de Luna/HTTP sigue pendiente de prueba real.

## Fuentes y estado

Se revisaron DIRECTORIO_OPPORTUNITIES_FINAL.md, PORTFOLIO_RESOLUTION.md, FINAL_GATES.md y BUSINESS_SEMANTICS_CANDIDATE.md del informe customer_C010264_commercial_opportunity_v1. Los CSV asociados son evidencia analítica, no catálogo autorizado.

La candidata permanece DRAFT / NOT_ACTIVATED. No se publicó nada ni se certificó pertenencia. El caso y sus ItemCodes se usan sólo en fixtures; no se hardcodean en resolver.

## Seis controles

Los controles separan significado empresarial de evidencia, permisos y capacidad efectiva.

| Contrato | Regla | Evidencia en esta etapa |
| --- | --- | --- |
| Directorio | Nuestros productos puede implicar portfolio Telchi/Litel sólo con contexto/identidad acreditados; explícito prevalece sujeto a permiso | Fixture conserva scope provisional y requisito de identidad; aplicación runtime pendiente |
| Mixto L00003 | Consumo interno y venta directa simultáneos; consumo no suma ventas ni prueba propiedad | Fixture y evidencia estructurada preservan dimensiones/limitación; MIX-01 a MIX-05 integrales pendientes |
| Clasificación | Elaborado/fraccionado/BOM/prefijo/marca no certifican propiedad | ownership UNKNOWN conservado; ninguna promoción DB |
| Ranking | Fuera del Top20 no prueba no comprado, underselling, venta perdida ni demanda | Fixture preserva métrica, ventana e incertidumbre; RANK-01 a RANK-09 de respuesta pendientes |
| Utilidad sin inventar | Entender no acredita capability, parámetros, datos, permiso ni ejecución | Regresión previa conservada; nueva fixture conserva intención multimétrica |
| Personas | Código documental observado no acredita identidad, responsable actual ni usuario Team360 | Limitación llega a Luna incluso en followup; atribución en respuesta real pendiente |

## Entidades, canales y métricas

Cliente se resuelve por CardCode con fuente; C010264 no es regla general. Calenta puede tener múltiples presentaciones/ItemCodes; no fusionar ni elegir arbitrariamente. Alias semántico no sustituye resolución canónica de entidad.

Farmacia significa sucursales acreditadas, no medicamentos. Menona requiere membresía comercial sin inferir atributos sensibles. Deudas distingue cobrar/pagar y corriente/vencida. Importaciones es prospectivo, no historial. Ventas perdidas requiere cotizaciones/oportunidades, no falta de factura.

Horizontal/DMS, corporativas y online requieren relaciones/códigos verificados y vigencia. Publicación del significado no habilita una capability por canal. Ninguna regla candidata se activó aquí.

Top20 debe conservar período, universo y métrica común: frecuencia distinta OINV no es facturación. Líneas, cantidades documentales, unidades comerciales, importes y venta neta no son intercambiables. No repartir DocTotal por ItemCode ni restar NC de frecuencia sin contrato.

## Propagación y límites de los tests

test_operational_closure.py comprueba conservación de contexto y evidencia hacia luna_context, incluyendo PROVISIONAL/UNKNOWN, y exclusión de referencias ajenas al catálogo. No comprueba todas las decisiones State Engine/respuesta ni una capability de oportunidades.

CONFIRMED/PROVISIONAL/UNKNOWN/CONFLICTED son evidencia empresarial; score vectorial no los cambia. NOT_EXECUTED/UNAVAILABLE son ejecución/disponibilidad, no hechos negativos. No se introdujeron enums paralelos.
