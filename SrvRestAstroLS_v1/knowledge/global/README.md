# Global Knowledge

Espacio para documentos fuente knowledge transversales de Team360.

Usar este arbol solo para contenido reusable por multiples paquetes o asistentes,
por ejemplo:

- politicas generales de seguridad y HITL;
- glosarios globales;
- criterios transversales de automatizacion;
- reglas compartidas de privacidad;
- conceptos comunes de Team360 que no pertenecen a un paquete especifico.

## Estructura

```
global/
├── drafts/
├── approved/
├── exports/
└── archive/
```

## Reglas

- No poner aqui documentos especificos de `pkg_sales_diagnosis`.
- No usar nombres comerciales como identificadores tecnicos.
- Todo documento aprobado debe usar `scope_type: global`.
- Si un documento global solo aplica a un paquete, moverlo al paquete.
- Si un documento de paquete se vuelve reusable, extraerlo a global y enlazarlo
  desde el paquete.

## Estado

Todavia no hay documentos globales aprobados. Esta carpeta existe para evitar
que la arquitectura knowledge quede acotada al primer paquete de ventas.
