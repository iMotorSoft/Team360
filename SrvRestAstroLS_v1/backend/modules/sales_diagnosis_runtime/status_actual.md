# Status actual - Diagnosis / Vera

Estado local reconciliado al corte documental 2026-10-06 desde los cierres previos. No se revalidaron servicios ni se modificó runtime protegido en esta tarea.

## Estado vigente y límites

Vera pública y embed no son los skeletons dev/product adapter descritos por fases históricas del README. La autoridad runtime permanece en LAT y PostgreSQL.

- Runtime público validado: `/t360 → Litestar → PostgreSQL 18 → Milvus 2.6 → LiteLLM`, alias `openai_gpt-5.4-nano`, Chat Completions.
- Diagnóstico de factibilidad separado de implementación; no solicitar OAuth/credenciales antes de cerrar factibilidad suficiente.
- Embed con loader/manifest/integrity y CORS; backend decide cliente, origin y contexto. HMAC request-bound sigue vigente; PASETO Console no implica migración embed.
- Mamamia360 aprobado según cierre productivo previo. HTTP 200/MIME no prueban montaje: gate exige ejecución hasta `mount()`.
- Diagnosticador/Vera y embed productivo son `PRODUCTION_PROTECTED`; esta documentación no autoriza cambios de código o deployment.
- Package npm, Web Component, plugin WordPress, UI de clientes y migración de tokens siguen como capacidades futuras.

## Autoridades y evidencia

Consultar contratos para comportamiento vigente e históricos para resultados fechados; el README conserva las fases dev sin redefinir el runtime público.

- [Política runtime](../../../../lat.md/team360-runtime-operational-policy.md), [arquitectura embed](../../../../lat.md/diagnosticador-embeddable-component-architecture.md).
- [Guía de instalación](../../../docs/diagnosticador_embed_installation_guide_v1.md), [contrato protegido](../../../docs/public_home_vera_protection_contract_v1.md).
- [Fases históricas dev](README.md), [cierres preservados](../../../docs/status_historico_hasta_normalizacion_2026-10-06.md), [estado GLOBAL](../../../docs/status_actual.md).

## Fix post-cierre

`TEAM360_DIAGNOSIS_POST_CLOSE_STATE_FIX_PASS` registra el cierre confirmado previo; el Full Gate debe revalidarlo sobre la composición actual, sin modificar producción.

- No existía pérdida de persistencia: `human_approval=required` es política, no evento de aprobación; `diagnosis_status=completed` representa el cierre.
- El bloqueo incondicional de `diagnose` para completed y el prompt que forzaba preguntas causaban el defecto post-cierre.
- Una solicitud explícita del diagnóstico final permite renderizarlo nuevamente manteniendo completed; no hay reapertura implícita ni se creó estado `approved`.
- [Replay y persist/reload](../../tests/test_sales_diagnosis_post_close.py), [Full Gate y evidencia](../../../docs/team360_full_gate_v1.md).

## Aislamiento de tests Diagnosis

La investigación del 2026-10-09 reprodujo los 14 fallos y confirmó `TEST_ISOLATION_ONLY`; la corrección sólo modifica el test DEV LiteLLM y su regresión de teardown, sin cambiar runtime ni producción.

- Primera fuga: el test DEV eliminaba `LITELLM_MASTER_KEY` heredada en su `finally`; el router posterior fallaba construyendo el classifier por falta de API key. Setup temporal ahora reversible con `monkeypatch`.
- Suite ampliada: antes 769 PASS / 14 FAIL / 10 skips; después 785 PASS / 0 FAIL / 10 skips en dos corridas y una tercera con archivos invertidos (dos casos de regresión nuevos).
- Los 14 afectados PASS; router/embed 91 PASS; subset Diagnosis del Full Gate 362 PASS / 1 skip; post-close 11 PASS / 1 skip. PostgreSQL real opt-in no ejecutado; no es un nuevo gate operacional ni promoción Srv05.
- [Comando, mínimo causal, tests y evidencia](../../../../data/reports/diagnosis/test-isolation-20261009/report.json). Estado GLOBAL preservado para reconciliación posterior.

## Próximo paso

Cualquier nueva validación real requiere preflight y regresión protegida específicos. No inferir una nueva garantía productiva de los tests ni de esta normalización documental.
