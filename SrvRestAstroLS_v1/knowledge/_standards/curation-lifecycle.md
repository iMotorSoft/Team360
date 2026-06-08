# Curation Lifecycle

Ciclo documental para knowledge fuente.

## Directorios

| Directorio | Uso | Ingestion |
|---|---|---|
| `drafts/` | Borradores, hipotesis, aprendizaje no curado. | No ingerir. |
| `approved/` | Documentos revisados y listos para ingestion. | Ingerible si metadata lo permite. |
| `exports/` | Derivados para lectura humana, PDF u otros formatos. | No fuente canonica. |
| `archive/` | Documentos reemplazados, obsoletos o pausados. | No ingerir como activo. |

## Promocion de draft a approved

Antes de mover un documento a `approved/`:

1. Completar frontmatter obligatorio.
2. Validar `area_key`, `topic_key`, `node_path` y `access_tags`.
3. Revisar evidencia y fuentes.
4. Documentar limites de uso.
5. Marcar riesgos y necesidades de HITL.
6. Confirmar que no contiene secretos ni datos sensibles.
7. Declarar quien valido y fecha.

## Reglas para approved

- No usar `evidence_level: hypothesis`.
- No usar `ingestion_status: not_ready`.
- No prometer delivery productivo sin evidencia.
- No mezclar knowledge de varios paquetes en el mismo documento.
- No convertir aprendizaje de una conversacion en conocimiento aprobado sin curaduria.

## Exports

Los exports son derivados. Si un PDF difiere del Markdown fuente, gana el
Markdown aprobado.

## Archive

Mover a `archive/` cuando:

- el documento fue reemplazado;
- la oferta ya no se vende;
- la evidencia quedo vieja;
- el enfoque fue descartado;
- el contenido contiene una decision que ya no debe alimentar retrieval activo.

## Auditoria minima

Cada documento promovido debe registrar:

- version;
- fecha;
- validador;
- motivo de promocion;
- riesgos aceptados;
- cambios relevantes.
