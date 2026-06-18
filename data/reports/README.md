# Reports

Reportes, evidencias, muestras y entregables generados fuera del codigo fuente.

## Estructura

- `mercadolibre/netzaj-racing/`: relevamientos publicos, playbook e intents derivados del seller NETZAJ RACING.
- `snapshots/`: snapshots historicos de estado del repo o de tareas puntuales.
- `validation/`: reportes JSON generados por `backend/scripts/validate_productive_vera_conversation.py`.
  Cada ejecucion produce un archivo timestamped (ignorado por Git via `.gitignore`).
  Ver `backend/scripts/README.md` para comandos y documentacion del runner.
