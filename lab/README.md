# Laboratorios

Laboratorios técnicos reproducibles y aislados del runtime productivo.

Cada subdirectorio es un experimento independiente con su propio README.

## Laboratorios activos

- `model-evaluation-sales-diagnosis/`: Comparación de modelos LLM sobre el
  dataset headless del diagnosticador Team360.

## Reglas

- No modificar configuración productiva desde `lab/`.
- Cada experimento debe tener su propia carpeta y README.
- Guardar resultados auditables en JSON/Markdown.
- Ejecutar comandos desde la raíz del proyecto.
- Preferir `uv run` cuando corresponda.
- Si un experimento se adopta, migrarlo luego a código productivo, tests o
  documentación formal.