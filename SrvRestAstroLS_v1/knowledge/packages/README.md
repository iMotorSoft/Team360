# Knowledge Packages

Indice de paquetes knowledge de Team360.

Cada paquete vive en:

```text
knowledge/packages/{package_code}/
```

## Convencion de paquete

Todo paquete debe tener:

- `README.md`;
- `status_actual.md`;
- `_metadata/package-profile.yaml`;
- `_metadata/knowledge-scope-mapping.yaml`;
- `_metadata/access-tags.yaml`;
- `drafts/`;
- `approved/`;
- `exports/`;
- `archive/`.

## Paquetes actuales

| package_code | Estado | Nota |
|---|---|---|
| `pkg_sales_diagnosis` | draft / validacion inicial | Primer paquete concreto; no define por si solo la arquitectura knowledge. |

## Regla

Crear un paquete nuevo solo cuando exista un `package_code` estable y una
frontera clara de corpus. El contenido reusable por varios paquetes debe vivir
en `knowledge/global/` o enlazarse desde alli.
