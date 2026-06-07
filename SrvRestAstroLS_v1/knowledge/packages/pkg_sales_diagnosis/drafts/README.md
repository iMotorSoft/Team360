# Drafts — pkg_sales_diagnosis

Documentos en revisión, no listos para ingesta.

## Reglas

- El worker de ingesta NO lee de este directorio.
- Pasar un documento a `approved/` solo cuando su front-matter YAML esté completo y validado.
- Usar `document-template.md` como punto de partida.

## Cómo promover un documento

1. Completar el front-matter YAML en el archivo.
2. Ubicarlo en `approved/{area_key}/` con el nombre en kebab-case.
3. Asegurar que `area_key` y `topic_key` en el YAML coincidan con la ruta.
4. Los `access_tags` deben ser válidos según `_metadata/access-tags.yaml`.
