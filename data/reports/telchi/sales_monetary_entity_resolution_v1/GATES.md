# Gates

El incremento monetario está ACTIVATED en DEV: DATA_PASS, SEMANTIC_PASS, AUTH_PASS y BUSINESS_RUNTIME_PASS para el contrato documental acotado. No se declara cierre total de Calenta ni reconciliación contable absoluta.

```text
TELCHI_HISTORICAL_BILLING_RECOVERY=PARTIAL
TELCHI_BILLING_SEMANTICS=PASS
TELCHI_MAY_2026_FOUNDATION_PARITY=PASS
TELCHI_MONETARY_CAPABILITY=PASS
TELCHI_MONETARY_RBAC=PASS
TELCHI_MONETARY_BUSINESS_HTTP=PASS
TELCHI_MONETARY_ACTIVATION=PASS
TELCHI_CALENTA_NAMESPACE_RESOLUTION=PARTIAL
TELCHI_CALENTA_BUSINESS_QUERY=BLOCKED
TELCHI_MULTI_METRIC_RESPONSE=PASS
TELCHI_SALES_EXISTING_CAPABILITIES=PARTIAL
TELCHI_SALES_SECURITY_REGRESSION=PASS
TELCHI_SALES_MONETARY_AND_ENTITY_RESOLUTION_V1=PARTIAL
```

La recuperación histórica es PARTIAL por SQL literal de algunas ejecuciones/monedas originales y recepción externa no acreditados; la definición oficial DocTotal/N/NC sí está recuperada y probada, no inventada. Por eso no bloquea un PASS monetario auténtico.

Semántica y datos: [billing](BILLING_SEMANTICS.md), [historia](HISTORICAL_BILLING_EVIDENCE.md), [reconciliación](MAY_2026_FOUNDATION_RECONCILIATION.md). Activación: [contrato](MONETARY_CAPABILITY_CONTRACT.md), [RBAC](RBAC_ACTIVATION.md), [HTTP](BUSINESS_HTTP_RESULTS.md), [referencia](FOUNDATION_REFERENCE_COMPARISON.md). Entidad: [Calenta](CALENTA_NAMESPACE_RESOLUTION.md).

MULTI_METRIC_RESPONSE=PASS significa intención conservada y respuesta parcial explícita cuando faltan cantidades mensuales; no significa cantidades físicas habilitadas. EXISTING_CAPABILITIES=PARTIAL refleja la intermitencia lingüística B01 con guard funcionando, no un fallo SQL ni RBAC. Los tests focalizados y el ranking/cobertura aceptados preservan sus contratos.

Validación: 179 tests focalizados PASS en [tests.log](tests.log), [validation_commands.log](validation_commands.log), fuentes actuales y estado Git preservados.

Comandos focalizados ejecutados desde backend: `uv run pytest modules/telchi/assistant/tests modules/telchi/provisioning/tests/test_sales_admin.py modules/telchi/provisioning/tests/test_monetary_admin.py -q`; runners `reconcile_foundation.py`, `verify_activation.py`, `security_http.py` y `modules.telchi.assistant.tests.runtime_http.run_battery --only M01,M02,M03,M04,M05,M06,M07,M10,M11,B01` con outputs de este reporte. Gates documentales desde raíz: `lat check md`, `lat check index`, `lat check sections`, `lat check code-refs`, `lat check` y `git diff --check`. Sin commits/push/deploy ni cambios a SAP, Foundation, Messaging horizontal, Srv01, Flow o Diagnosis. State Engine sin cambios.

HOST_PREFLIGHT=SAFE; dos threads DuckDB propios, 512MB por conexión, suites focalizadas sin pools ilimitados. No procesos ajenos terminados. Los runtimes propios reportan pid_reaped; OWN_PROCESSES_LEFT_RUNNING=0 según handles del harness, ENVIRONMENTAL_ABORTS=0. El PASS de recursos no sustituye los controles de datos.

Próximo paso: recuperar el SQL literalmente ejecutado y pruebas externas de entrega si existen; acreditar el crosswalk de ocho SKUs Calenta; resolver presentaciones; reproducir la intermitencia de interpretación sin reparar `/pending` ni debilitar committed.
