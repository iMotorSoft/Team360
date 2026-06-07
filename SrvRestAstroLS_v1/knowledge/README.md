# Knowledge — Documentos Fuente para Ingesta

Raíz de documentos fuente ingeribles por la plataforma Team360.

## Estructura

```
knowledge/
└── packages/
    └── {package_code}/
        ├── README.md
        ├── _metadata/
        │   ├── package-profile.yaml
        │   ├── knowledge-scope-mapping.yaml
        │   └── access-tags.yaml
        ├── drafts/          # Documentos en revisión (no ingerir)
        ├── approved/        # Documentos listos para ingesta
        ├── exports/         # Exportaciones derivadas (PDF, etc.)
        └── archive/         # Documentos reemplazados o deprecated
```

## Reglas

- Cada paquete tiene su propio árbol bajo `packages/{package_code}/`.
- `drafts/` contiene documentos en revisión; el worker de ingesta NO lee de aquí.
- `approved/` contiene documentos validados listos para ser ingeridos.
- `exports/` contiene formatos derivados (PDF). No son fuente canónica.
- `archive/` contiene documentos reemplazados o deprecated. No se ingieren.
- Los archivos `_metadata/` definen el perfil del paquete, el mapeo de scope y el catálogo de tags de acceso.
- No mezclar knowledge de cliente con knowledge de producto.
- No mezclar drafts con approved.
- Los documentos fuente no son documentación técnica del sistema; eso pertenece a `docs/`.

## Paquetes actuales

| package_code | knowledge_scope_code | Asistente |
|---|---|---|
| `pkg_sales_diagnosis` | `ks_team360_sales_diagnosis` | Asistente Inteligente Vera (comercial) |
