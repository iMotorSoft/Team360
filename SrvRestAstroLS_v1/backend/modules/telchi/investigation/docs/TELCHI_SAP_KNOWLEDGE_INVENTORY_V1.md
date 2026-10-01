# TELCHI DATA LAKE — SAP KNOWLEDGE INVENTORY V1

## A. Gate

**DEGRADED — `TELCHI_SAP_KNOWLEDGE_INVENTORY_V1_DEGRADED`**

La revisión documental y de evidencia cerró el inventario, pero no puede declararse
PASS porque permanecen gaps materiales de lineage/snapshots, autorización histórica,
uso operacional de MRP/forecast, nómina detallada, WHT transaccional y algunos vínculos
físicos/temporales. No se inventaron conclusiones para compensarlos.

**Scope:** `ENTITY=TELCHI`; `STAGE=INVESTIGATION`; `SOURCE=SAP_HANA + LEGACY_DS + EXTERNAL_FILES`.
El gate consultó primero código, SQL, tests, reportes, JSON/YAML y manifests. No se
abrió una sesión SAP/HANA nueva.

## B. Resumen ejecutivo

- Se revisaron sistemáticamente los artefactos bajo `investigation/docs` y `investigation/validation`, además del manifest externo Telchi.
- Se catalogaron **116 identificadores de gates** (incluye estados históricos y gates referenciados; no se deduplican estados PASS/DEGRADED/FAIL como si fueran la misma evidencia).
- El catálogo contiene **79 tablas/objetos SAP**, **31 relaciones**, **26 reglas** y **19 métricas baseline**.
- Ventas, crédito/as-of, compras, producción, stock/transferencias, usuarios y contabilidad tienen evidencia HANA previa reproducible.
- Las piezas críticas del Gate 1, `movProductSB1` y `saleSB1Product`, conservan correspondencias probables pero no equivalencias confirmadas automáticamente.
- La cadena de compras `PO→AP→GR` y la cadena de producción `BOM→OWOR→IGE1/IGN1→OINM` están especialmente bien cerradas.
- `OITW` es estado actual; `OINM` permite reconstrucción histórica, pero la correspondencia con snapshots legacy aún requiere política temporal.
- MRP/forecast registra configuración y observaciones, no prueba de ejecución operacional ni de vigencia histórica.
- El histórico de autorización SAP no existe en la evidencia; la seguridad futura queda pendiente y no se implementó.
- Los números baseline se preservan para regresión futura, no se proponen como filas de Parquet nuevas.
- El siguiente gate debe aprobar modelo canónico, lineage, snapshots y fronteras de producto antes de diseñar físico.

## C. Método, seguridad y fuentes

Orden aplicado:

```text
EVIDENCIA EXISTENTE → CONOCIMIENTO VALIDADO → GAPS/UNKNOWN → SAP puntual si imprescindible
```

Fuentes revisadas:

- Workspace: `SrvRestAstroLS_v1/backend/modules/telchi/investigation/`.
- Gate 1, sin modificar: `docs/TELCHI_HISTORICAL_DATA_INVENTORY_V1.md`.
- Evidencia externa disponible: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi/investigation-consolidation-v1`; archivos visibles en manifest/árbol: **162**.
- Se inspeccionaron Markdown, Python, SQL, JSON, YAML y manifests CSV/TSV cuando eran evidencia o investigación.

```text
SAP_ACCESSED=NO
SAP_ACCESS_PURPOSE=NONE
SAP_WRITE_COUNT=0
SOURCE_EVIDENCE_MODIFIED=0
```

Este gate no ejecuta conectores SAP y no escribe Data Root, Legacy Root ni Private Root.

## D. Gates/investigaciones encontrados

El inventario completo, con `gate_id,title,domain,status,date_if_known,source_document,
source_code,evidence_path,sap_access,read_only,tables,business_question,main_result,
confidence`, está en `sap_gates_inventory.csv`. Los estados explícitos encontrados son:

```text
{'DEGRADED': 14, 'FAIL': 6, 'PARTIAL': 3, 'PASS': 93}
```

Muestras de gates principales y su alcance:

| Gate | Estado | Dominio | Fuente |
|---|---|---|---|
| TEAM360_TELCHI_CORPORATE_SALES_AUGUST_2026_PASS | PASS | VENTAS | SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/corporate_sales/CORPORATE_SALES_FINAL_REPORT.md |
| TEAM360_TELCHI_CUSTOMER_CHANNEL_HISTORY_PASS | PASS | TELCHI_SAP_CROSS_DOMAIN | SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/corporate_sales/CHANNEL_HISTORY_FINAL_REPORT.md |
| TEAM360_TELCHI_DOCUMENTATION_HANDOFF_PASS | PASS | TELCHI_SAP_CROSS_DOMAIN | UNKNOWN |
| TEAM360_TELCHI_FINANCIAL_AUDIT_MODEL_PASS | PASS | CONTABILIDAD | SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/financial_audit/financial_005_final_report.md; SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/financial_reporting/reporting_contract_final_report.md |
| TEAM360_TELCHI_FINANCIAL_REPORTING_CONTRACT_PASS | PASS | CONTABILIDAD | SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/financial_reporting/reporting_contract_final_report.md |
| TEAM360_TELCHI_INVENTORY_MOVEMENTS_CURRENT_PASS | PASS | MOVIMIENTOS_DE_INVENTARIO | UNKNOWN |
| TEAM360_TELCHI_INVENTORY_TRANSTYPE_MAP_FAIL | FAIL | MOVIMIENTOS_DE_INVENTARIO | UNKNOWN |
| TEAM360_TELCHI_INVENTORY_TRANSTYPE_MAP_PASS | PASS | MOVIMIENTOS_DE_INVENTARIO | SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/inventory_movements/TRANSTYPE_MAP_FINAL_REPORT.md |
| TEAM360_TELCHI_REAL_SALES_CHANNEL_RULE_PASS | PASS | VENTAS | SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/corporate_sales/CHANNEL_RULE_FINAL_REPORT.md |
| TEAM360_TELCHI_TEMPORAL_SALES_DIMENSIONS_PASS | PASS | VENTAS | SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/sales_dimensions/SALES_DIMENSIONS_FINAL_REPORT.md |
| TELCHI_AP_PAYABLES_PAYMENT_RECONCILIATION_V1_PASS | PASS | COMPRAS_Y_ABASTECIMIENTO | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/telchi_ap_payables_payment_reconciliation_v1_report.md |
| TELCHI_ATOMIC_CASH_ACCOUNTING_TRACEABILITY_H4_V1_PASS | PASS | CAJA_BANCOS | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/traceability_cash_accounting_h4_v1_report.md |
| TELCHI_ATOMIC_CONTRACTS_NUCLEUS_V1_PASS | PASS | TELCHI_SAP_CROSS_DOMAIN | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/atomic_nucleus_v1_report.md |
| TELCHI_ATOMIC_SALES_CASH_STOCK_TRACEABILITY_V1_PASS | PASS | STOCK_E_INVENTARIOS | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/traceability_cash_accounting_h4_v1_report.md; SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/traceability_sales_cash_stock_v1_report.md |
| TELCHI_AVAILABILITY_BACKTEST_V1_PASS | PASS | TELCHI_SAP_CROSS_DOMAIN | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/telchi_replenishment_gate_5b_availability_based_backtest_v1_report.md; SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/telchi_replenishment_level_b_100_l_products_v1_report.md |
| TELCHI_BALANCE_SHEET_PNL_RECONSTRUCTION_V1_PASS | PASS | TELCHI_SAP_CROSS_DOMAIN | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/telchi_balance_sheet_pnl_reconstruction_v1_report.md |
| TELCHI_C010341_LA_REJA_OPERATIONAL_IDENTITY_V1_PASS | PASS | TELCHI_SAP_CROSS_DOMAIN | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/credit_risk_ex_la_reja_v1_report.md; SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/la_reja_c010341_operational_identity_v1_report.md |
| TELCHI_CASH_DEPOSIT_CONTROL_V1_PASS | PASS | CAJA_BANCOS | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/telchi_cash_deposit_control_v1_report.md |
| TELCHI_CHANNEL_SELLER_NOT_TRANSACTION_PROOF_PASS | PASS | TELCHI_SAP_CROSS_DOMAIN | UNKNOWN |
| TELCHI_COMMERCIAL_LOST_SALES_SOURCE_NORMALIZATION_V1_PASS | PASS | VENTAS | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/commercial_opportunity_traceability_v1_report.md |
| TELCHI_COMMERCIAL_OPPORTUNITY_P0_PRODUCTS_V1_PASS | PASS | VENTAS | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/commercial_opportunity_traceability_v1_report.md |
| TELCHI_COMMERCIAL_OPPORTUNITY_STOCK_PRICE_SALE_TRACEABILITY_V1_PASS | PASS | STOCK_E_INVENTARIOS | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/commercial_opportunity_traceability_v1_report.md |
| TELCHI_CREDIT_CONTROL_AUTHORIZATION_TRACEABILITY_V1_PASS | PASS | CRÉDITO_Y_DEUDORES | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/credit_control_authorization_traceability_v1_report.md; SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/credit_exception_cases_v1_report.md; SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/credit_explained_cases_economic_grouping_v1_report.md; SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/credit_open_risk_aging_v1_report.md; SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/la_reja_c010341_operational_identity_v1_report.md |
| TELCHI_CREDIT_EXCEPTION_CASES_V1_PASS | PASS | CRÉDITO_Y_DEUDORES | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/credit_exception_cases_v1_report.md; SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/credit_explained_cases_economic_grouping_v1_report.md; SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/credit_open_risk_aging_v1_report.md; SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/la_reja_c010341_operational_identity_v1_report.md |
| TELCHI_CREDIT_EXPLAINED_CASES_ECONOMIC_GROUPING_V1_PASS | PASS | CRÉDITO_Y_DEUDORES | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/credit_explained_cases_economic_grouping_v1_report.md; SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/credit_open_risk_aging_v1_report.md; SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/la_reja_c010341_operational_identity_v1_report.md |
| TELCHI_CREDIT_OPEN_RISK_AGING_V1_PASS | PASS | CRÉDITO_Y_DEUDORES | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/credit_open_risk_aging_v1_report.md; SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/la_reja_c010341_operational_identity_v1_report.md |
| TELCHI_CREDIT_RISK_EX_LA_REJA_V1_PASS | PASS | CRÉDITO_Y_DEUDORES | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/credit_risk_ex_la_reja_v1_report.md |
| TELCHI_DAILY_STOCK_RESOURCE_SMOKE_TEST_V1_PASS | PASS | STOCK_E_INVENTARIOS | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/telchi_branch_replenishment_daily_stock_demand_v1_report.md |
| TELCHI_EQUIVALENT_MATERIAL_COVERAGE_V1_DEGRADED | DEGRADED | TELCHI_SAP_CROSS_DOMAIN | UNKNOWN |
| TELCHI_EQUIVALENT_MATERIAL_COVERAGE_V1_PASS | PASS | TELCHI_SAP_CROSS_DOMAIN | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/equivalent_material_coverage_v1_report.md; SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/purchase_material_planning_v1_final_report.md |
| TELCHI_EXTERNAL_PAYROLL_TO_SAP_RECONCILIATION_V1_DEGRADED | DEGRADED | COMPRAS_Y_ABASTECIMIENTO | UNKNOWN |
| TELCHI_EXTERNAL_PAYROLL_TO_SAP_RECONCILIATION_V1_PASS | PASS | COMPRAS_Y_ABASTECIMIENTO | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/telchi_external_payroll_to_sap_reconciliation_v1_report.md |
| TELCHI_FINANCIAL_ACCOUNTING_FOUNDATION_V1_PASS | PASS | CONTABILIDAD | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/telchi_financial_accounting_foundation_v1_report.md |
| TELCHI_FINANCIAL_AGING_PASS | PASS | CONTABILIDAD | UNKNOWN |
| TELCHI_FINANCIAL_AR_AUDIT_FLAGS_PASS | PASS | CONTABILIDAD | UNKNOWN |
| TELCHI_FINANCIAL_AR_DIMENSION_RECONCILIATION_PASS | PASS | CONTABILIDAD | UNKNOWN |
| TELCHI_FINANCIAL_AR_SAP_TRACEABILITY_PASS | PASS | CONTABILIDAD | UNKNOWN |
| TELCHI_FINANCIAL_AR_SETTLEMENT_AGGREGATION_PASS | PASS | CONTABILIDAD | UNKNOWN |
| TELCHI_FINANCIAL_CHANNEL_AR_PASS | PASS | CONTABILIDAD | UNKNOWN |
| TELCHI_FINANCIAL_CREDIT_NOTE_FAIL | FAIL | CRÉDITO_Y_DEUDORES | UNKNOWN |
| TELCHI_FINANCIAL_CREDIT_NOTE_PASS | PASS | CRÉDITO_Y_DEUDORES | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/README.md; SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/session_backup_2026_08_23.md; SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/financial_audit/financial_005_final_report.md |
| TELCHI_FINANCIAL_CURRENT_AR_PASS | PASS | CONTABILIDAD | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/README.md; SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/session_backup_2026_08_23.md; SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/financial_audit/financial_005_final_report.md |
| TELCHI_FINANCIAL_CUSTOMER_AR_PASS | PASS | CONTABILIDAD | UNKNOWN |
| TELCHI_FINANCIAL_DEBT_AND_FINANCIAL_RESULT_TRACEABILITY_V1_PASS | PASS | CONTABILIDAD | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/telchi_financial_debt_and_financial_result_v1_report.md |
| TELCHI_FINANCIAL_FORECAST_LIQUIDITY_SCENARIOS_V1_PASS | PASS | CONTABILIDAD | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/telchi_financial_forecast_liquidity_scenarios_v1_report.md |
| TELCHI_FINANCIAL_HISTORICAL_ASOF_AR_PASS | PASS | CONTABILIDAD | UNKNOWN |
| TELCHI_FINANCIAL_INVOICE_BALANCE_RECONCILIATION_PASS | PASS | CONTABILIDAD | UNKNOWN |
| TELCHI_FINANCIAL_INVOICE_CONTRACT_FAIL | FAIL | CONTABILIDAD | UNKNOWN |
| TELCHI_FINANCIAL_INVOICE_CONTRACT_PASS | PASS | CONTABILIDAD | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/README.md; SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/session_backup_2026_08_23.md; SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/financial_audit/financial_005_final_report.md |
| TELCHI_FINANCIAL_MARCH_2023_RECON_OUTLIER_EXPLAINED_PASS | PASS | CONTABILIDAD | UNKNOWN |
| TELCHI_FINANCIAL_PAYMENT_APPLICATION_FAIL | FAIL | CONTABILIDAD | UNKNOWN |
| TELCHI_FINANCIAL_PAYMENT_APPLICATION_PASS | PASS | CONTABILIDAD | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/README.md; SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/session_backup_2026_08_23.md; SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/financial_audit/financial_005_final_report.md |
| TELCHI_FINANCIAL_POSITION_CASH_FLOW_V1_1_PASS | PASS | CONTABILIDAD | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/telchi_financial_forecast_liquidity_scenarios_v1_report.md; SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/telchi_financial_position_cash_flow_v1_1_report.md |
| TELCHI_FINANCIAL_POSITION_CASH_FLOW_V1_DEGRADED | DEGRADED | CONTABILIDAD | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/telchi_financial_position_cash_flow_v1_report.md |
| TELCHI_FINANCIAL_RECONCILIATION_FAIL | FAIL | CONTABILIDAD | UNKNOWN |
| TELCHI_FINANCIAL_RECONCILIATION_PASS | PASS | CONTABILIDAD | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/README.md; SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/session_backup_2026_08_23.md; SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/financial_audit/financial_005_final_report.md |
| TELCHI_FINANCIAL_REPORTING_KPI_CONTRACT_PASS | PASS | CONTABILIDAD | UNKNOWN |
| TELCHI_FINANCIAL_SELLER_AR_PASS | PASS | CONTABILIDAD | UNKNOWN |
| TELCHI_FINISHED_GOODS_MATERIAL_EQUIVALENCE_V1_DEGRADED | DEGRADED | TELCHI_SAP_CROSS_DOMAIN | UNKNOWN |
| TELCHI_FINISHED_GOODS_MATERIAL_EQUIVALENCE_V1_PASS | PASS | TELCHI_SAP_CROSS_DOMAIN | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/finished_goods_material_equivalence_v1_report.md; SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/purchase_material_planning_v1_final_report.md |
| TELCHI_GL_TRANS_TYPE_ACCOUNT_BEHAVIOR_V1_PASS | PASS | CONTABILIDAD | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/telchi_gl_trans_type_account_behavior_v1_report.md |
| TELCHI_HISTORICAL_DATA_INVENTORY_V1_PASS | PASS | MOVIMIENTOS_DE_INVENTARIO | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/TELCHI_HISTORICAL_DATA_INVENTORY_V1.md |
| TELCHI_HISTORICAL_STOCK_RECONSTRUCTION_V1_PASS | PASS | STOCK_E_INVENTARIOS | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/commercial_opportunity_traceability_v1_report.md |
| TELCHI_HR_PAYROLL_ACCOUNTING_TRACEABILITY_V1_PASS | PASS | RRHH | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/telchi_hr_payroll_accounting_traceability_v1_report.md |
| TELCHI_INVENTORY_CURRENT_BASE_PASS | PASS | MOVIMIENTOS_DE_INVENTARIO | UNKNOWN |
| TELCHI_INVENTORY_CURRENT_BASE_REGRESSION_FAIL | FAIL | MOVIMIENTOS_DE_INVENTARIO | UNKNOWN |
| TELCHI_INVENTORY_CURRENT_BASE_REGRESSION_PASS | PASS | MOVIMIENTOS_DE_INVENTARIO | UNKNOWN |
| TELCHI_MATERIAL_STOCK_POSITION_V1_DEGRADED | DEGRADED | STOCK_E_INVENTARIOS | UNKNOWN |
| TELCHI_MATERIAL_STOCK_POSITION_V1_PASS | PASS | STOCK_E_INVENTARIOS | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/material_stock_position_v1_report.md; SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/purchase_material_planning_v1_final_report.md |
| TELCHI_MAX_PRODUCIBLE_BY_COMPONENT_V1_DEGRADED | DEGRADED | TELCHI_SAP_CROSS_DOMAIN | UNKNOWN |
| TELCHI_MAX_PRODUCIBLE_BY_COMPONENT_V1_PASS | PASS | TELCHI_SAP_CROSS_DOMAIN | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/max_producible_by_component_v1_report.md; SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/purchase_material_planning_v1_final_report.md |
| TELCHI_MRP_CONFIGURATION_AUDIT_V1_PASS | PASS | FORECAST_Y_ESTACIONALIDAD | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/telchi_mrp_configuration_audit_v1_report.md |
| TELCHI_PRICE_REALITY_TRACEABILITY_V1_PASS | PASS | TELCHI_SAP_CROSS_DOMAIN | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/commercial_opportunity_traceability_v1_report.md |
| TELCHI_PRODUCED_COMPONENT_DEPENDENCY_V1_PASS | PASS | TELCHI_SAP_CROSS_DOMAIN | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/produced_component_dependency_v1_report.md |
| TELCHI_PRODUCTION_COMPONENT_CONSUMPTION_V1_PASS | PASS | PRODUCCIÓN | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/production_component_consumption_v1_report.md |
| TELCHI_PRODUCTION_OUTPUT_TRACEABILITY_V1_PASS | PASS | PRODUCCIÓN | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/production_output_traceability_v1_report.md |
| TELCHI_PRODUCTION_RECONCILIATION_V1_PASS | PASS | PRODUCCIÓN | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/production_reconciliation_v1_report.md |
| TELCHI_PRODUCTION_SCHEMA_DISCOVERY_V1_PASS | PASS | PRODUCCIÓN | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/production_schema_discovery_v1_report.md |
| TELCHI_PRODUCT_SEASONALITY_V1_DEGRADED | DEGRADED | FORECAST_Y_ESTACIONALIDAD | UNKNOWN |
| TELCHI_PRODUCT_SEASONALITY_V1_PASS | PASS | FORECAST_Y_ESTACIONALIDAD | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/product_seasonality_v1_report.md; SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/purchase_material_planning_v1_final_report.md |
| TELCHI_PROFORMA_SEMANTICS_V1_PASS | PASS | COTIZACIONES_PROFORMAS | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/commercial_opportunity_traceability_v1_report.md |
| TELCHI_PROFORMA_TO_SALE_TRACEABILITY_V1_PASS | PASS | COTIZACIONES_PROFORMAS | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/commercial_opportunity_traceability_v1_report.md |
| TELCHI_PURCHASE_DATA_DISCOVERY_V1_DEGRADED | DEGRADED | COMPRAS_Y_ABASTECIMIENTO | UNKNOWN |
| TELCHI_PURCHASE_DATA_DISCOVERY_V1_PASS | PASS | COMPRAS_Y_ABASTECIMIENTO | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/purchase_data_discovery_v1_report.md; SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/purchase_material_planning_v1_final_report.md |
| TELCHI_PURCHASE_DECISION_BACKTEST_V1_PASS | PASS | COMPRAS_Y_ABASTECIMIENTO | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/purchase_decision_backtest_v1_report.md; SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/purchase_material_planning_v1_final_report.md |
| TELCHI_PURCHASE_EXECUTIVE_CASES_V1_PASS | PASS | COMPRAS_Y_ABASTECIMIENTO | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/purchase_material_planning_v1_final_report.md |
| TELCHI_PURCHASE_LEAD_TIME_V1_DEGRADED | DEGRADED | COMPRAS_Y_ABASTECIMIENTO | UNKNOWN |
| TELCHI_PURCHASE_LEAD_TIME_V1_PASS | PASS | COMPRAS_Y_ABASTECIMIENTO | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/purchase_lead_time_v1_report.md; SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/purchase_material_planning_v1_final_report.md |
| TELCHI_PURCHASE_MATERIAL_PLANNING_V1_DEGRADED | DEGRADED | COMPRAS_Y_ABASTECIMIENTO | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/purchase_material_planning_v1_final_report.md |
| TELCHI_PURCHASE_MATERIAL_PLANNING_V1_PASS | PASS | COMPRAS_Y_ABASTECIMIENTO | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/purchase_material_planning_v1_final_report.md |
| TELCHI_PURCHASE_RISK_ENGINE_V1_DEGRADED | DEGRADED | COMPRAS_Y_ABASTECIMIENTO | UNKNOWN |
| TELCHI_PURCHASE_RISK_ENGINE_V1_PASS | PASS | COMPRAS_Y_ABASTECIMIENTO | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/purchase_material_planning_v1_final_report.md; SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/purchase_risk_engine_v1_report.md |
| TELCHI_RECIPE_BOM_TRACEABILITY_V1_PASS | PASS | BOM_PRODUCCIÓN | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/recipe_bom_traceability_v1_report.md |
| TELCHI_REPLENISHMENT_BACKTEST_ENGINE_V1_DEGRADED | DEGRADED | TELCHI_SAP_CROSS_DOMAIN | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/telchi_branch_replenishment_backtest_engine_v1_report.md |
| TELCHI_REPLENISHMENT_LEVEL_B_100_L_PRODUCTS_V1_PASS | PASS | TELCHI_SAP_CROSS_DOMAIN | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/telchi_physical_lead_time_v1_report.md; SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/telchi_replenishment_level_b_100_l_products_v1_report.md |
| TELCHI_REPLENISHMENT_POLICY_SELECTION_UNCERTAIN_LT_V1_PASS | PASS | TELCHI_SAP_CROSS_DOMAIN | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/telchi_replenishment_policy_selection_uncertain_lt_v1_report.md |
| TELCHI_RETAIL_ONE_DMS_USER_ATTRIBUTION_V1_PASS | PASS | USUARIOS_ROLES_Y_PERMISOS | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/credit_exception_cases_v1_report.md; SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/credit_explained_cases_economic_grouping_v1_report.md; SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/retail_one_dms_user_attribution_v1_report.md; SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/users_roles_applications_documentation_index.md |
| TELCHI_SAP_CANCELLED_INVOICE_AUDIT_V1_PASS | PASS | COMPRAS_Y_ABASTECIMIENTO | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/session_backup_2026_08_23.md |
| TELCHI_SAP_MODULE_IDENTITY_PASS | PASS | COMPRAS_Y_ABASTECIMIENTO | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/identity_verification.md; SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/session_backup_2026_08_23.md |
| TELCHI_SAP_USERS_ROLES_MODULES_APPLICATIONS_V1_DEGRADED | DEGRADED | USUARIOS_ROLES_Y_PERMISOS | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/users_roles_authorizations_v1_report.md |
| TELCHI_SAP_USERS_ROLES_MODULES_APPLICATIONS_V1_PASS | PASS | USUARIOS_ROLES_Y_PERMISOS | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/credit_exception_cases_v1_report.md; SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/credit_explained_cases_economic_grouping_v1_report.md; SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/users_roles_applications_documentation_index.md; SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/users_roles_authorizations_v1_report.md |
| TELCHI_TEMPORAL_CANCELLATION_SEMANTICS_PASS | PASS | TRAZABILIDAD_DOCUMENTAL | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/README.md; SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/fase0_summary.md; SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/session_backup_2026_08_23.md; SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/temporal_investigation_complete.md |
| TELCHI_TEMPORAL_MODEL_ARCHITECTURE_PASS | PASS | TRAZABILIDAD_DOCUMENTAL | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/README.md; SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/session_backup_2026_08_23.md |
| TELCHI_TEMPORAL_PAYMENT_CANCELLATION_PASS | PASS | TRAZABILIDAD_DOCUMENTAL | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/README.md; SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/session_backup_2026_08_23.md |
| TELCHI_TEMPORAL_RECONCILIATION_CANCELLATION_PASS | PASS | TRAZABILIDAD_DOCUMENTAL | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/README.md; SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/session_backup_2026_08_23.md |
| TELCHI_TREASURY_CASH_BANK_DEPOSIT_V1_PASS | PASS | CAJA_BANCOS | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/telchi_treasury_cash_bank_deposit_v1_report.md |
| TELCHI_USERS_DOCUMENTATION_AUDIT_V1_PASS | PASS | USUARIOS_ROLES_Y_PERMISOS | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/users_roles_applications_documentation_index.md |
| TELCHI_USERS_PHASE10_AUTHORIZED_ACTUAL_PASS | PASS | USUARIOS_ROLES_Y_PERMISOS | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/users_roles_authorizations_v1_report.md |
| TELCHI_USERS_PHASE13_CROSS_TRACEABILITY_PASS | PASS | USUARIOS_ROLES_Y_PERMISOS | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/users_roles_authorizations_v1_report.md |
| TELCHI_USERS_PHASE6_BUSINESS_CAPABILITIES_PASS | PASS | USUARIOS_ROLES_Y_PERMISOS | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/users_roles_authorizations_v1_report.md |
| TELCHI_USERS_PHASE9_APPLICATION_ORIGIN_PASS | PASS | USUARIOS_ROLES_Y_PERMISOS | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/users_roles_authorizations_v1_report.md |
| TELCHI_WAREHOUSE_TRANSFER_TRACEABILITY_V1_PASS | PASS | TRANSFERENCIAS_Y_DEPÓSITOS | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/warehouse_transfer_traceability_v1_report.md |
| TELCHI_WITHHOLDING_TAX_ACCOUNTING_TRACEABILITY_V1_DEGRADED | DEGRADED | TELCHI_SAP_CROSS_DOMAIN | SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/telchi_withholding_tax_accounting_traceability_v1_report.md |

Los estados históricos se conservan: un `FAIL` previo no se transforma en PASS por la
existencia de un PASS posterior; la vigencia se lee en el documento fechado y en el
`STATUS_ACTUAL.md`.

## E. Mapa funcional SAP

| Dominio | Conocimiento ya validado | Núcleo SAP | Estado |
|---|---|---|---|
| Ventas / documentos | factura, NC, proforma, pedido, entrega, cancelación, canal | OINV/INV1, ORIN/RIN1, OQUT/QUT1, ORDR/RDR1, ODLN/DLN1 | CONFIRMED con temporalidad parcial |
| Crédito / cobranzas | saldo as-of, vencido, límite, excepción, aging, reconciliación | OCRD, OINV, ORIN, ORCT, ITR1/OITR, OADM | CONFIRMED; autorizaciones históricas UNKNOWN |
| Compras | solicitud, PO, AP, recepción, devolución, proveedor, tipo, lead time | OPRQ/PRQ1, OPOR/POR1, OPCH/PCH1, OPDN/PDN1, ORPD/RPD1 | CONFIRMED |
| Stock / transferencias | stock actual, ledger, roles de almacén, transferencia contable | OITW, OINM, OWHS, OWTR/WTR1 | CONFIRMED; físico no demostrado |
| Producción / BOM | receta histórica, consumo, output, reconciliación, dependencia | OITT/ITT1, OWOR/WOR1, OIGE/IGE1, OIGN/IGN1 | CONFIRMED con links parciales |
| MRP / forecast | parámetros, cobertura, forecasts observados, seasonality | OITM/OITW, OFCT/FCT1 | CONFIGURED/OBSERVED; operación UNKNOWN |
| Usuarios / permisos | usuarios, grupos, capabilities, actividad, atribución de canal | OUSR/USR3/UGR1/OUGR/USR5/OHEM/OSLP/OUPT | CONFIRMED current-only |
| Finanzas / tesorería | GL, AR/AP, cash, bancos, depósitos, deuda, resultado | OACT/OJDT/JDT1, ORCT/OVPM/ODPS, OBNK | CONFIRMED/PARTIAL |
| RRHH / WHT | maestro empleado y costo GL; configuración WHT | OHEM/OACT/JDT1, OWHT/PCH5/PCH6/VPM6 | DEGRADED |

## F. Catálogo de tablas

El catálogo completo y sus ocho campos contractuales está en `sap_tables_inventory.csv`
(**79 objetos**). Se conservan campos de configuración y UDF relevantes
sin confundirlos con una prueba de uso operacional. Entre los UDT/UDF externos detectados
se preservan como objetos auxiliares en los reportes: `@SO1_01LOGAUTORIZA`,
`@SO1_01VENCREVENC`, `@SO1_01COMPRA*` y `@SO1_01SUGERENCOMPRA`, además de
`U_TIPOCOMPRA`, `U_ORIGIN`, `U_SO1_01RETAILONE` y `U_LOTE`.

| Tabla | Dominio | Propósito | Clave candidata | Confianza |
|---|---|---|---|---|
| OITM | PRODUCTOS | item master and MRP/product attributes | ItemCode | CONFIRMED |
| OITW | STOCK_E_INVENTARIOS | current item-by-warehouse position and policy | ItemCode+WhsCode | CONFIRMED |
| OWHS | ALMACENES | warehouse master | WhsCode | CONFIRMED |
| OITB | PRODUCTOS | item group used in product/business classification | ItmsGrpCod | CONFIRMED |
| OINV | VENTAS | sales invoice header | DocEntry | CONFIRMED |
| INV1 | VENTAS | sales invoice lines and document lineage | DocEntry+LineNum | CONFIRMED |
| INV6 | CRÉDITO_Y_DEUDORES | invoice installment/due-date mirror | DocEntry+InstlmntID | CONFIRMED |
| ORIN | NOTAS_DE_CREDITO | credit note header | DocEntry | CONFIRMED |
| RIN1 | NOTAS_DE_CREDITO | credit note lines and base document lineage | DocEntry+LineNum | CONFIRMED |
| ODLN | VENTAS | delivery header | DocEntry | CONFIRMED |
| DLN1 | VENTAS | delivery lines | DocEntry+LineNum | CONFIRMED |
| ORDR | VENTAS | sales order header | DocEntry | CONFIRMED |
| RDR1 | VENTAS | sales order lines | DocEntry+LineNum | CONFIRMED |
| OQUT | COTIZACIONES_PROFORMAS | quotation/proforma header | DocEntry | CONFIRMED |
| QUT1 | COTIZACIONES_PROFORMAS | quotation/proforma lines | DocEntry+LineNum | CONFIRMED |
| OCRD | CLIENTES_PROVEEDORES | business partner master for customers and suppliers | CardCode | CONFIRMED |
| OCRG | CLIENTES_PROVEEDORES | business partner group | GroupCode | CONFIRMED |
| OCTG | CRÉDITO_Y_DEUDORES | payment terms/group | GroupNum | CONFIRMED |
| OSLP | VENDEDORES | salesperson master | SlpCode | CONFIRMED |
| ORCT | COBRANZAS | incoming payment header | DocEntry | CONFIRMED |
| RCT2 | COBRANZAS | incoming payment invoice references (not settlement authority) | DocNum+InvType+DocEntry | CONFIRMED |
| OITR | RECONCILIACIONES | internal reconciliation header and as-of date | ReconNum | CONFIRMED |
| ITR1 | RECONCILIACIONES | reconciliation members and settlement amounts | ReconNum+LineSeq | CONFIRMED |
| OPOR | COMPRAS_Y_ABASTECIMIENTO | purchase order header | DocEntry | CONFIRMED |
| POR1 | COMPRAS_Y_ABASTECIMIENTO | purchase order lines | DocEntry+LineNum | CONFIRMED |
| OPRQ | SOLICITUDES_DE_COMPRA | purchase request header | DocEntry | CONFIRMED |
| PRQ1 | SOLICITUDES_DE_COMPRA | purchase request lines | DocEntry+LineNum | CONFIRMED |
| OPCH | FACTURAS_DE_PROVEEDOR | AP/vendor invoice header | DocEntry | CONFIRMED |
| PCH1 | FACTURAS_DE_PROVEEDOR | AP/vendor invoice lines | DocEntry+LineNum | CONFIRMED |
| OPDN | RECEPCIONES | goods receipt header | DocEntry | CONFIRMED |
| PDN1 | RECEPCIONES | goods receipt lines | DocEntry+LineNum | CONFIRMED |
| ORPD | DEVOLUCIONES | purchase return header | DocEntry | CONFIRMED |
| RPD1 | DEVOLUCIONES | purchase return lines | DocEntry+LineNum | CONFIRMED |
| OITT | BOM_PRODUCCIÓN | current bill-of-material header | Code | CONFIRMED |
| ITT1 | BOM_PRODUCCIÓN | current BOM components | Father,Code | CONFIRMED |
| OWOR | PRODUCCIÓN | production order header | DocEntry | CONFIRMED |
| WOR1 | PRODUCCIÓN | historical order component snapshot | DocEntry+LineNum | CONFIRMED |
| OIGE | PRODUCCIÓN | goods issue header | DocEntry | CONFIRMED |
| IGE1 | PRODUCCIÓN | actual component issue lines | DocEntry+LineNum | CONFIRMED |
| OIGN | PRODUCCIÓN | goods receipt/output header | DocEntry | CONFIRMED |
| IGN1 | PRODUCCIÓN | actual finished-good output lines | DocEntry+LineNum | CONFIRMED |
| OINM | MOVIMIENTOS_DE_INVENTARIO | inventory movement ledger | TransNum+TransSeq | CONFIRMED |
| OWTR | TRANSFERENCIAS_Y_DEPÓSITOS | inventory transfer header | DocEntry | CONFIRMED |
| WTR1 | TRANSFERENCIAS_Y_DEPÓSITOS | inventory transfer lines | DocEntry+LineNum | CONFIRMED |
| IBT1 | LOTES_SERIES | batch transaction ledger | ItemCode+BatchNum+BaseEntry+BaseLinNum | CONFIRMED |
| OBTN | LOTES_SERIES | batch master | AbsEntry | LIKELY |
| OFCT | FORECAST_Y_ESTACIONALIDAD | forecast header | AbsID | CONFIRMED |
| FCT1 | FORECAST_Y_ESTACIONALIDAD | forecast rows | AbsID+LineId | CONFIRMED |
| OUSR | USUARIOS_ROLES_Y_PERMISOS | SAP user master | USERID | CONFIRMED |
| USR3 | USUARIOS_ROLES_Y_PERMISOS | direct user permissions | USERID+PermId | CONFIRMED |
| UGR1 | USUARIOS_ROLES_Y_PERMISOS | group permissions | GroupId+PermId | CONFIRMED |
| USR5 | ACTIVIDAD_DE_USUARIOS | user activity/session log | USERID+LineNum | CONFIRMED |
| OUGR | USUARIOS_ROLES_Y_PERMISOS | user groups | GroupId | CONFIRMED |
| OUPT | USUARIOS_ROLES_Y_PERMISOS | permission tree | PermId | LIKELY |
| OHEM | RRHH | employee master | empID | CONFIRMED |
| OADM | CONFIGURACIÓN_SAP | company-level credit and configuration | singleton | CONFIRMED |
| OJDT | CONTABILIDAD | journal entry header | TransId | CONFIRMED |
| JDT1 | CONTABILIDAD | journal entry lines | TransId+Line_ID | CONFIRMED |
| OACT | CONTABILIDAD | chart of accounts and balances | AcctCode | CONFIRMED |
| ODPS | CAJA_BANCOS | deposit header | DeposId | CONFIRMED |
| OCHH | CAJA_BANCOS | check history/deposit linkage | CheckKey | CONFIRMED |
| OCHO | CAJA_BANCOS | outgoing checks | CheckKey | LIKELY |
| ODSC | CAJA_BANCOS | bank/house bank configuration | AbsEntry | CONFIRMED |
| DSC1 | CAJA_BANCOS | bank account configuration | AbsEntry+LineId | CONFIRMED |
| OBNK | CAJA_BANCOS | bank statement/reconciliation source | BankMatchNo | CONFIRMED |
| OVPM | CAJA_BANCOS | outgoing payment header | DocEntry | CONFIRMED |
| VPM2 | CAJA_BANCOS | outgoing payment invoice application | DocNum+InvType+DocEntry | CONFIRMED |
| PCH5 | RETENCIONES | AP withholding detail | AbsEntry+LineNum | CONFIRMED |
| PCH6 | RETENCIONES | AP withholding totals | AbsEntry | CONFIRMED |
| VPM6 | RETENCIONES | payment withholding totals | DocNum | CONFIRMED |
| OWHT | RETENCIONES | withholding configuration | WTCode | CONFIRMED |
| @SO1_01LOGAUTORIZA | USUARIOS_ROLES_Y_PERMISOS | Retail One authorization/activity log | event/folio candidate | CONFIRMED |
| @SO1_01VENCREVENC | CRÉDITO_Y_DEUDORES | Retail One customer exception flag UDT | CardCode candidate | LIKELY |
| @SO1_01COMPRA | COMPRAS_Y_ABASTECIMIENTO | Retail One purchase UDT (observed empty) | DocEntry candidate | CONFIRMED |
| @SO1_01COMPRADETALLE | COMPRAS_Y_ABASTECIMIENTO | Retail One purchase detail UDT (observed empty) | DocEntry+LineNum candidate | CONFIRMED |
| @SO1_01DEVOLCOMPRA | COMPRAS_Y_ABASTECIMIENTO | Retail One purchase return UDT (observed empty) | DocEntry candidate | CONFIRMED |
| @SO1_01COMPRAWEB | COMPRAS_Y_ABASTECIMIENTO | Retail One web purchase UDT (observed empty) | DocEntry candidate | CONFIRMED |
| @SO1_01FAVPROVEEDOR | COMPRAS_Y_ABASTECIMIENTO | Retail One preferred supplier UDT (observed empty) | supplier/item candidate | CONFIRMED |
| @SO1_01SUGERENCOMPRA | COMPRAS_Y_ABASTECIMIENTO | Retail One purchase suggestion UDT (observed empty) | item candidate | CONFIRMED |

## G. Relaciones confirmadas y no confirmadas

No se elevó un join a `CONFIRMED` solo por ser estándar SAP: cada relación confirmada
abajo tiene evidencia Telchi, SQL, test o reporte inequívoco. `LIKELY/POSSIBLE` queda
separada para el siguiente gate.

| Izquierda | Clave | Derecha | Clave | Tipo | Significado | Confianza |
|---|---|---|---|---|---|---|
| OINV | DocEntry | INV1 | DocEntry | 1:N | invoice header to lines | sales/financial gates + SQL invoice contract | CONFIRMED |
| ORIN | DocEntry | RIN1 | DocEntry | 1:N | credit note header to lines | financial credit-note gate | CONFIRMED |
| OQUT | DocEntry | QUT1 | DocEntry | 1:N | quotation header to lines | proforma/pricing investigation | CONFIRMED |
| OWOR | DocEntry | WOR1 | DocEntry | 1:N | production order to historical component snapshot | production schema + BOM gates | CONFIRMED |
| OITT | Code | ITT1 | Father | 1:N | current BOM header to components | recipe/BOM gate | CONFIRMED |
| OPOR | DocEntry | PCH1 | BaseEntry | 1:N | PO to vendor invoice lines, BaseType=22 | purchase discovery P0.1 | CONFIRMED |
| OPCH | DocEntry | PDN1 | BaseEntry | 1:N | vendor invoice to goods receipt lines, BaseType=18 | purchase discovery P0.1 | CONFIRMED |
| OPOR | DocEntry | PDN1 | BaseEntry | 1:N | direct PO to goods receipt, BaseType=22 | purchase discovery | CONFIRMED |
| OINV | DocEntry | ITR1 | SrcObjAbs | 1:N | invoice settlement member, SrcObjTyp=13 | financial reconciliation + credit gates | CONFIRMED |
| ORCT | DocEntry | ITR1 | SrcObjAbs | 1:N | incoming payment settlement member, SrcObjTyp=24 | financial reconciliation gate | CONFIRMED |
| OITR | ReconNum | ITR1 | ReconNum | 1:N | reconciliation header to members and ReconDate | financial reconciliation gate | CONFIRMED |
| OINV | TransId | OJDT | TransId | 1:1 | invoice accounting entry when present | financial/traceability gates | LIKELY |
| ORCT | TransId | OJDT | TransId | 1:1 | incoming payment accounting entry | treasury and cross traceability | CONFIRMED |
| OVPM | TransId | OJDT | TransId | 1:1 | outgoing payment accounting entry | AP/treasury gates | CONFIRMED |
| ODPS | TransAbs | OJDT | TransId | 1:1 | deposit accounting entry | treasury gate | CONFIRMED |
| IGE1 | BaseEntry | OWOR | DocEntry | N:1 | actual component issue to production order, BaseType=202 | production schema gate | CONFIRMED |
| IGN1 | BaseEntry | OWOR | DocEntry | N:1 | actual finished output to production order, BaseType=202 | production schema gate | CONFIRMED |
| IGE1 | BaseRef | OINM | BASE_REF | N:0..1 | issue to inventory ledger where populated | production output/consumption gates | LIKELY |
| IGN1 | BaseRef | OINM | BASE_REF | N:0..1 | receipt to inventory ledger where populated | production output/consumption gates | LIKELY |
| OWTR | DocEntry | WTR1 | DocEntry | 1:N | transfer header to lines | warehouse transfer gate | CONFIRMED |
| WTR1 | DocEntry+LineNum | OINM | source movement | 1:2 | transfer origin out and destination in | warehouse transfer gate TT67 | CONFIRMED |
| OITW | ItemCode+WhsCode | OINM | ItemCode+Warehouse | 1:N | current stock reconciled to movement ledger | material stock gate | CONFIRMED |
| OUSR | USERID | OHEM | userCode/employee link | 0..1:0..1 | SAP user to employee where populated | users and attribution gate | CONFIRMED |
| OHEM | salesPrson | OSLP | SlpCode | N:1 | employee to salesperson | users and attribution gate | CONFIRMED |
| OUSR | USERID | USR5 | USERID | 1:N | user to activity events | users gate; aggregate before joins | CONFIRMED |
| OUSR | USERID | USR3 | USERID | 1:N | direct permissions | users gate; current only | CONFIRMED |
| OUGR | GroupId | UGR1 | GroupId | 1:N | group permissions | users gate; current only | CONFIRMED |
| OINV | CardCode | OCRD | CardCode | N:1 | invoice business partner | sales/credit/customer gates | CONFIRMED |
| OWTR | DocEntry | IBT1 | BaseEntry | 1:N | batch trace for transfer when batch data exists | transfer gate | LIKELY |
| OPCH | DocEntry | ITR1 | SrcObjAbs | 1:N | AP settlement members | AP reconciliation gate | CONFIRMED |
| OVPM | DocEntry | ITR1 | SrcObjAbs | 1:N | outgoing payment settlement members | AP reconciliation gate | CONFIRMED |

La cardinalidad anti-fanout es parte del conocimiento: en usuarios y documentos 1:N se
agrega antes de cruzar importes; el caso `OINV→OINM` es multi-línea y no debe sumarse por
join ingenuo.

## H. Reglas de negocio validadas

Las reglas centrales, su evidencia y confianza están en `sap_business_rules_inventory.csv`.
Resumen de las reglas que no deben perderse:

1. **Settlement:** `OITR/ITR1` es autoridad de liquidación; `RCT2` es referencia de aplicación.
2. **As-of credit:** saldo, vencimiento y cobros se evalúan con fecha de reconciliación y estado de documentos al corte; no con `PaidToDate` aislado.
3. **Purchases:** `BaseEntry→DocEntry` es el link canónico; el flujo observado es predominantemente invoice-first.
4. **Inventory:** `OnHand`, `IsCommited` y `OnOrder` son capas semánticas distintas; no se suma `OITW.OnOrder` con PO abierta sin reconciliación.
5. **Production:** `WOR1` conserva receta de la orden; `IGE1` es consumo real y `IGN1` output real; `CmpltQty` no reemplaza output.
6. **Transfers:** `FromWhsCod→WhsCode` conserva el evento contable TT67, no prueba tránsito físico.
7. **MRP:** `CONFIGURED`, `VALIDATED` y `OBSERVED` deben permanecer separados.
8. **Users:** `OJDT.UserSign` suele ser usuario de transacción origen; una fila USR5 no equivale a una operación.
9. **Finance/WHT/HR:** configuración, movimiento GL y proceso externo son conceptos distintos; no se afirma nómina detallada ni WHT activo sin evidencia.

## I. Métricas baseline

Estas métricas son **VALIDATION BASELINE**, no diseño ni carga propuesta. Cada fila tiene
universo/filtros, tablas, gate y reproducibilidad en `sap_validated_metrics.csv`.

| ID | Métrica | Dominio | Valor | Período | Reproducible |
|---|---|---|---|---|---|
| M-SALES-VOLUME | sales invoices | VENTAS | 1.81M invoices; channel split 86.1% Retail One / 8.5% DMS / 5.4% SAP direct | 2026-08 | YES |
| M-CREDIT-BASELINE | sales with overdue unpaid at sale date | CRÉDITO_Y_DEUDORES | 2,318 exact; 287 prior baseline revalidated; 19 unresolved in the 287 operational subset | 2026-01-01..2026-09-01 | YES |
| M-CREDIT-OPEN | open risk | CRÉDITO_Y_DEUDORES | Bs 252,973 open; Bs 175,928.88 not due; Bs 77,044.12 overdue | 2026-09-01 | YES |
| M-PURCHASE-CHAIN | purchase chain coverage | COMPRAS_Y_ABASTECIMIENTO | PO→AP 90,959/90,959; AP→GR 87,577/87,577; direct PO→GR 54/54 | 2026-08-27 | YES |
| M-PURCHASE-LEAD | purchase lead time p90 | COMPRAS_Y_ABASTECIMIENTO | LF 4d; LP 43d; IMP 82d; SAA 34d; global first receipt p90 5d | 2022-01..2026-08 | YES |
| M-STOCK | stock position | STOCK_E_INVENTARIOS | 16,793 items; 82 warehouses; OnOrder 1,790,139; IsCommited 487,292 | 2026-08-27 | YES |
| M-TRANSFER | transfer conservation | TRANSFERENCIAS_Y_DEPÓSITOS | 36,210/36,210 transfer lines conserved in OINM TT67; 0 same-warehouse | 2026-08-26 | YES |
| M-PROD-ORDERS | production census | PRODUCCIÓN | 20,777 OWOR; 140,391 WOR1 lines; 20,487 standard orders | 2022-04..2026-08 | YES |
| M-PROD-CONSUMPTION | production issue method | PRODUCCIÓN | 67.5% manual / 32.5% backflush; 134,291/134,292 IssuedQty reconciled | 2026-08-26 | YES |
| M-PROD-OUTPUT | production output | PRODUCCIÓN | 19,654/20,487 orders with CmpltQty reconciled to IGN1; 842 without output | 2026-08-26 | YES |
| M-MRP-COVERAGE | MRP configuration coverage | FORECAST_Y_ESTACIONALIDAD | LeadTime 69.5%; SafetyStock 0%; forecast 29.1%; BOM 6.2% of item universe | 2026-08-26 | YES |
| M-SEASONALITY | product seasonality coverage | FORECAST_Y_ESTACIONALIDAD | 10,775 items; high/medium volume coverage 90.0%; 4,168 insufficient | 2026-08-27 | YES |
| M-USERS | SAP users/activity | USUARIOS_ROLES_Y_PERMISOS | 170 users; 78 active; 92 blocked; 3,176,076 USR5 rows; 16 superusers | 2026-08-26 | YES |
| M-FIN-AR | open AR | CONTABILIDAD | 2,067 documents; Bs 4,092,786.95; overdue Bs 1,477,647.75 | 2026-09-10 | YES |
| M-FIN-AP | open AP | CONTABILIDAD | 636 documents; Bs 9,547,420.94 + USD 148,291.25 | 2026-09-10 | YES |
| M-FIN-BS | balance sheet reconciliation | CONTABILIDAD | Assets Bs 86,107,745.15; liabilities Bs 21,498,186.57; equity Bs 64,609,558.58; gap 0 | 2026-09-10 | YES |
| M-FIN-RESULT | financial result | CONTABILIDAD | −Bs 1,414,305.12 reproduced; bridge post-close −Bs 104.59 | 2026-09-10 | YES |
| M-TREASURY | treasury document volumes | CAJA_BANCOS | 1,804,931 ORCT; 40,272 OVPM; 14,593 ODPS | 2026-09-09 | YES |
| M-HR-COST | HR expense in GL | RRHH | Bs 13,600,311.25 HR-classified YTD expense; detailed payroll not observed | 2026-09-09 | YES |

## J. Universos especiales

- Gate de crédito: ventanas as-of explícitas; 287 es baseline operativo revalidado y 2,318 es el universo exacto ampliado, no intercambiables.
- Productos `ItemCode LIKE 'L%'`: usado en reposición/producción como universo de análisis, no regla universal de todos los gates.
- Producción: `Type='S'`, `BaseType=202`, y separación de `Released`/`Closed` según evidencia observada.
- Compras: `U_TIPOCOMPRA in {LF,LP,IMP,SERV,SAA}`; `OpenQty>0` para ordenado no recibido.
- Stock: activo/cancelado, almacén por rol, y separación `OnHand-IsCommited` de `OnOrder`.
- Usuarios: activos/bloqueados, superuser, técnico vs persona; `USR5` agregado por usuario/evento.
- Finanzas: `BS` y `USD` no se compensan; P&L excluye asientos de apertura/cierre según contrato.

## K. Correspondencia HISTÓRICO ↔ SAP

Gate 1 se usó literalmente y no se reinterpretó. El detalle está en
`sap_historical_mapping.csv` (**10 correspondencias**).

| Familia histórica | Fuente SAP candidata | Matching | Grano/diferencia | Confianza |
|---|---|---|---|---|
| movProductSB1 | OINM + source documents | TransNum/DocLineNum vs SAP movement keys; ItemCode; Warehouse/WhsCode; TransType/BASE_REF | legacy line movement vs SAP ledger; legacy includes enriched joins and duplicate candidate keys | LIKELY |
| saleSB1Product | OINV + INV1 | DocEntry, ItemCode, document/date/amount fields | legacy enriched invoice-line family; WhsCode optional/null in some -h files | LIKELY |
| ncB1Product | ORIN + RIN1 | DocEntry/line/item/date/amount candidates | legacy NC family with fu_* naming variants; semantic equivalence not fully reconciled | POSSIBLE |
| productSB1 | OITM | ItemCode and product attributes | master snapshot vs current SAP master; validity history absent | LIKELY |
| clientSB1 | OCRD | CardCode/CardName and customer attributes | master snapshot; customer history and as-of validity absent | LIKELY |
| owhsSB1 | OWHS | WhsCode/warehouse names | small historical warehouse master vs 82-warehouse current census | POSSIBLE |
| wareHouseSB1 | OWHS | warehouse code/name fields | enriched warehouse family; likely master/reference | POSSIBLE |
| paymentB1 | ORCT + ITR1/OITR | DocEntry, amount, dates, reconciliation fields | payment snapshot vs settlement ledger; RCT2 must not be assumed sufficient | POSSIBLE |
| reconB1 | OITR + ITR1 | ReconNum/LineSeq and reconciliation amounts/dates | legacy reconciliation family likely closest to SAP settlement grain | LIKELY |
| productTracking | OBTN/IBT1 and/or legacy-only tracking | product/tracking date/lot candidates | no direct complete equivalence demonstrated | UNKNOWN |

Conclusión: `saleSB1Product`, `movProductSB1`, `ncB1Product`, `productSB1`, `clientSB1`,
`owhsSB1`, `wareHouseSB1`, `paymentB1` y `reconB1` tienen candidatos plausibles y
artefactos compatibles, pero solo algunos campos/relaciones son `LIKELY`; no se declara
`CONFIRMED` sin reconciliación de cobertura, grano, fechas y lineage.

## L. Conocimiento no materializado / gaps

La tabla completa, separada por clase solicitada, está en `sap_data_gaps.csv` (**18 gaps**).

| ID | Clase | Conocimiento | Gap | Prioridad |
|---|---|---|---|---|
| GAP-001 | LINEAGE_UNKNOWN | All legacy Parquet | No formal source system, query, extractor identity, watermark, timezone or snapshot contract in footers | next gate lineage contract | HIGH |
| GAP-002 | TEMPORAL_GAP | Snapshot families | Filename date and contained business dates are distinct; concatenation can double count | snapshot/as-of policy | HIGH |
| GAP-003 | SEMANTICS_UNKNOWN | movProductSB1 ↔ OINM | candidate join is rich but not universal; 181,384 duplicate candidate keys | reconcile grain and document coverage | HIGH |
| GAP-004 | HISTORICAL_NOT_AVAILABLE | master Parquet ↔ SAP masters | historical validity of OITM/OCRD/OWHS and warehouse-office mapping is absent | temporal master policy | HIGH |
| GAP-005 | SAP_NOT_YET_INVESTIGATED | Purchasing request approval / MRP execution | tables/configuration discovered, but operational approval and MRP run history are not demonstrated | targeted investigation only if needed | MEDIUM |
| GAP-006 | SEMANTICS_UNKNOWN | OFCT/FCT1 | configured/observed forecast rows do not prove active operational forecast use | forecast contract | HIGH |
| GAP-007 | SEMANTICS_UNKNOWN | OITM/OITW safety stock | SafetyStock field/operational semantics not confirmed; ReorderPnt is only a labeled proxy | MRP semantics decision | HIGH |
| GAP-008 | SAP_NOT_YET_INVESTIGATED | MRP/forecast history | no execution log or historical parameter versioning located | point validation with SAP/process owner | MEDIUM |
| GAP-009 | SAP_NOT_YET_INVESTIGATED | Lotes/series | IBT1/OBTN observed in selected paths; complete sales/production lot/serial coverage not closed | lot/serial scope gate | MEDIUM |
| GAP-010 | SEMANTICS_UNKNOWN | production → dispatch | no BaseType=202 FK; temporal ItemCode/warehouse/date link is heuristic | business model must preserve heuristic | HIGH |
| GAP-011 | SEMANTICS_UNKNOWN | physical lead time | OWTR/OINM accounting event does not prove physical dispatch/receipt | logistics evidence contract | HIGH |
| GAP-012 | SECURITY_PENDING | users/permissions | historical authorization unavailable; future security-before-retrieval not implemented | RBAC/row/column/metric policy | HIGH |
| GAP-013 | SAP_NOT_YET_INVESTIGATED | approvals/exceptions | management approvals external to SAP; retail log linkage is heuristic in part | external evidence contract | MEDIUM |
| GAP-014 | SAP_NOT_YET_INVESTIGATED | detailed payroll | OHEM and GL cost observed, but no detailed SAP payroll object identified | external payroll boundary | HIGH |
| GAP-015 | SEMANTICS_UNKNOWN | WHT | configured OWHT accounts and WHT columns do not establish an active transactional path | WHT source authority | HIGH |
| GAP-016 | SEMANTICS_UNKNOWN | bank reconciliation | OBNK exists but no external bank balance reconciliation was demonstrated | bank statement contract | MEDIUM |
| GAP-017 | HISTORICAL_NOT_AVAILABLE | legacy purchaseExpense/productTransform/cash | SAP equivalents are partial or not yet semantically reconciled | legacy↔SAP mapping gate | MEDIUM |
| GAP-018 | TEMPORAL_GAP | cancellations and payments | current SAP can reconstruct selected as-of states, but historical Parquet coverage and watermarks differ | as-of reconciliation | HIGH |

En particular, SAP actual aporta conocimiento que no aparece completo en el histórico:
BOM/órdenes/consumos/output, stock actual/OINM, transferencias documentales, MRP/forecast,
usuarios/permisos actuales, GL/AP/AR/tesorería y deuda. En sentido inverso, el histórico
aporta familias legacy como `productTracking`, `purchaseExpense`, `productTransform`,
`cash` y `cuentasxCobrar` cuya semántica SAP equivalente es parcial o UNKNOWN.

## M. Candidate Data Products

Son límites semánticos candidatos; no son nombres definitivos de Parquet, particiones,
capas raw/staging/atomic/business/decision ni layout físico.

| Candidato | Dominio | Conocimiento | Estado | security_domain | Sensibilidad |
|---|---|---|---|---|---|
| inventory_movements | STOCK_E_INVENTARIOS | OINM + document lineage; movProductSB1 correspondence | CONFIRMED/PARTIAL | inventory | cost; warehouse scope; movement user |
| sales_lines | VENTAS | OINV/INV1 with cancellation and channel semantics | CONFIRMED | sales | price; cost; margin; customer |
| sales_document_chain | VENTAS | quotation/order/delivery/invoice/credit-note chain | CONFIRMED/PARTIAL | sales | customer; price; discount |
| customer_credit_state | CRÉDITO_Y_DEUDORES | as-of invoice/NC/payment/reconciliation/aging | CONFIRMED | credit | credit_limit; customer_debt; customer |
| purchase_cycle | COMPRAS_Y_ABASTECIMIENTO | request/order/invoice/receipt/return with BaseEntry lineage | CONFIRMED | purchases | purchase_price; supplier |
| production_orders | PRODUCCIÓN | OWOR/WOR1/IGE1/IGN1 and normalized reconciliation | CONFIRMED/PARTIAL | production | cost; output; component |
| bom_and_component_usage | BOM_PRODUCCIÓN | OITT/ITT1 plus order-time WOR1 | CONFIRMED/PARTIAL | production | cost; formulation |
| stock_current_and_history | STOCK_E_INVENTARIOS | OITW current and OINM reconstruction | CONFIRMED | inventory | cost; warehouse |
| warehouse_transfers | TRANSFERENCIAS_Y_DEPÓSITOS | OWTR/WTR1/OINM TT67 | CONFIRMED/HEURISTIC_PHYSICAL | inventory | warehouse; user |
| forecast_and_mrp_parameters | FORECAST_Y_ESTACIONALIDAD | OFCT/FCT1 and OITM/OITW configuration | CONFIGURED_NOT_OPERATIONAL_PROOF | configuration | forecast; policy |
| users_activity_and_capabilities | USUARIOS_ROLES_Y_PERMISOS | OUSR/USR3/UGR1/OUGR/USR5/OHEM/OSLP | CONFIRMED_CURRENT_ONLY | users | user_activity; authorization |
| gl_ar_ap_treasury | CONTABILIDAD | OACT/OJDT/JDT1 plus AR/AP and treasury chains | CONFIRMED/PARTIAL | finance | bank_account; salary; debt |

## N. Seguridad futura

En esta fase se consideró `administrator/administrators`, scope ALL. No se implementaron
permisos. La matriz futura está en `sap_security_domains.csv` y etiqueta dominios, alcance
organizacional candidato y campos sensibles.

| security_domain | Dominio | Campos sensibles | Row scope candidato | Fase |
|---|---|---|---|---|
| inventory | inventory | warehouse, ItemCode, cost | candidate warehouse/organizational scope | administrator/all in this gate |
| sales | sales | customer, price, cost, margin | customer/branch/channel candidate | administrator/all in this gate |
| purchases | purchases | supplier, purchase_price, cost | supplier/branch candidate | administrator/all in this gate |
| production | production | formulation, cost, output | plant/warehouse candidate | administrator/all in this gate |
| credit | credit | credit_limit, customer_debt | customer/portfolio candidate | administrator/all in this gate |
| finance | finance | bank_account, debt, margin | company/legal-entity candidate | administrator/all in this gate |
| hr | hr | salary, employee identity | organizational candidate | administrator/all in this gate |
| users | users | user_activity, authorization | organizational candidate | administrator/all in this gate |
| configuration | configuration | MRP/credit configuration | company/warehouse candidate | administrator/all in this gate |

Invariante futura: **SECURITY BEFORE RETRIEVAL**; debe combinar RBAC, scope organizacional,
filtros de fila, políticas de columna y políticas de métrica.

## O. Tracking de lineage

La materia prima queda en los CSV y en cada fuente primaria: reporte, script/SQL, test y
evidencia externa. El contrato aún no está cerrado. Cada métrica y regla apunta a tablas,
gate y documento; cada mapping conserva matching, grano, cobertura y diferencia semántica.
No existe todavía un `source_query_or_code` universal ni watermark de extracción para los
Parquet legacy; por eso `LINEAGE_UNKNOWN` es un gap material y no se oculta.

## P. Limitaciones y decisión del gate

```text
HISTORICAL_INVENTORY_USED=YES
SAP_ACCESSED=NO
SAP_ACCESS_PURPOSE=NONE
SAP_WRITE_COUNT=0
SAP_GATES_FOUND=116
SAP_TABLES_CATALOGUED=79
SAP_RELATIONSHIPS_CATALOGUED=31
SAP_BUSINESS_RULES_CATALOGUED=26
SAP_METRICS_BASELINED=19
HISTORICAL_SAP_MAPPINGS=10
UNRESOLVED_GAPS=18
SOURCE_EVIDENCE_MODIFIED=0
PRODUCTION_PARQUETS_CREATED=0
DATALAKE_PHYSICAL_DESIGN_CREATED=0
```

`TELCHI_SAP_KNOWLEDGE_INVENTORY_V1_DEGRADED`

## Q. Recomendación para el siguiente gate

No implementarla en este gate. El siguiente gate debe aprobar, usando estos catálogos como
fuente:

```text
CANONICAL BUSINESS MODEL
+ LINEAGE CONTRACT
+ SNAPSHOT POLICY
+ DATA PRODUCT BOUNDARIES
```

Debe resolver primero el grano de `movProductSB1`/`saleSB1Product`, la política as-of y
los snapshots acumulativos, equivalencias legacy↔SAP, seguridad antes de retrieval y qué
baselines serán regresiones. Recién después corresponde diseñar formatos/particiones y
producir datasets físicos.

## R. Archivos reproducibles

- `validation/sap_knowledge_inventory_v1/inventory.py`
- `validation/sap_knowledge_inventory_v1/sap_gates_inventory.csv`
- `validation/sap_knowledge_inventory_v1/sap_tables_inventory.csv`
- `validation/sap_knowledge_inventory_v1/sap_relationships_inventory.csv`
- `validation/sap_knowledge_inventory_v1/sap_business_rules_inventory.csv`
- `validation/sap_knowledge_inventory_v1/sap_validated_metrics.csv`
- `validation/sap_knowledge_inventory_v1/sap_historical_mapping.csv`
- `validation/sap_knowledge_inventory_v1/sap_data_gaps.csv`
- `validation/sap_knowledge_inventory_v1/sap_candidate_data_products.csv`
- `validation/sap_knowledge_inventory_v1/sap_security_domains.csv`

El runner solo genera esos inventarios pequeños, un resumen JSON y este informe. No crea Parquet
productivos, no mueve históricos y no accede SAP.
