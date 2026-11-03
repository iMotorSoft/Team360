# Regla candidata — consultas del directorio Telchi

Propuesta para revisión en el catálogo Business Semantics existente (PostgreSQL + pgvector). Solo documentación: no se insertó ni activó una regla y no se modificó memoria semántica.

## Alcance y precedencia

Cuando el interlocutor/contexto está acreditado como directorio Telchi y pide nuestros Top 20, productos no comprados u oportunidades por cliente, el universo implícito es Telchi/Litel acreditado por ItemCode.

Incluye elaborados propios, fraccionados, materias primas vendidas directamente y productos mixtos. Excluye terceros e insumos exclusivamente internos sin comercialización. No basta marca, prefijo, descripción ni proveedor aislados.

Otros usuarios pueden solicitar todo el catálogo. Una petición explícita de universo prevalece sobre el implícito; si contradice el contexto, aclarar antes de ejecutar. No cambiar silenciosamente consultas ajenas al directorio.

## Operación y condiciones

Resolver cliente por CardCode; comparar productos por ItemCode y presentación, con igual período, métrica y tratamiento documental. Separar no comprado en la ventana de comprado fuera del Top 20. No decir nunca comprado sin cobertura histórica acreditada.

A = G − H; B = (G ∩ H) − C; complemento = U − H fuera de A. Preferir importe de línea validado; si no existe, frecuencia documental etiquetada. No repartir DocTotal ni sumar UoM heterogéneas.

## Estado de la candidata

DRAFT / NOT_ACTIVATED. Autoridad empresarial propuesta: addendum del usuario para este informe. Requiere revisión del alcance directorio, crosswalk de pertenencia acreditado, pruebas positivas/negativas y autorización explícita antes de persistir/activar en el catálogo existente.

C010264 es el caso de validación, no parte de la regla general. Si falta pertenencia, separar incertidumbre y bloquear afirmaciones Top 20 propias, sin sustituir el universo.
