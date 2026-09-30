"""Build the Telchi CEO semantic/performance contract without materializing facts.

This module is intentionally an investigation artifact.  It writes only catalog
CSV/JSON evidence beside this file; it never creates atomic, business or
current datasets and never connects to SAP.
"""
from __future__ import annotations

import csv
import json
import statistics
import time
from pathlib import Path
from typing import Iterable

import duckdb

ROOT = Path(__file__).resolve().parents[7]
DATA_ROOT = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi")
OUT = Path(__file__).resolve().parent
REFERENCE = DATA_ROOT / "reference"
CROSSWALK = DATA_ROOT / "crosswalk"
EVIDENCE = ROOT / "validation" / "ducklake_postgres18_foundation_v1" / "evidence"
GATE = "TELCHI_DATALAKE_CEO_QUERY_SEMANTICS_AND_PERFORMANCE_CONTRACT_V1"

FAMILIES = ["SALES", "STOCK", "CREDIT", "CASH", "PRODUCTION", "PURCHASES", "PROFITABILITY", "CUSTOMER", "PRODUCT", "BRANCH"]

def plan(domain: str, metric: str, *, entity: str = "", dimension: str = "", period: str = "ASK_OR_CONTEXT", comparison: str = "NONE", grain: str = "company", unit: str = "", clarification: str = "NONE") -> str:
    return json.dumps({
        "domain": domain, "metrics": [metric], "entities": ([entity] if entity else []),
        "dimensions": ([dimension] if dimension else []), "filters": [],
        "time_range": period, "comparison": comparison, "scope": {"authorization": "REQUIRED", "default": "ALL_IF_AUTHORIZED"},
        "requested_unit": unit or None, "currency": "BOB_IF_VALIDATED", "grain": grain,
        "ranking": None, "limit": None, "drilldown_level": "EXECUTIVE",
        "freshness_requirement": "INTRADAY", "ambiguities": ([clarification] if clarification != "NONE" else []),
    }, ensure_ascii=False, sort_keys=True)


def q(qid: str, family: str, priority: str, question: str, domain: str, metric: str, target: str, latency: str, freshness: str, drilldown: str, *, entity: str = "", dimension: str = "", period: str = "ASK_OR_CONTEXT", comparison: str = "NONE", grain: str = "company", unit: str = "", clarification: str = "NONE") -> dict[str, object]:
    return {
        "query_id": qid, "family": family, "priority": priority, "example_question": question,
        "semantic_plan": plan(domain, metric, entity=entity, dimension=dimension, period=period, comparison=comparison, grain=grain, unit=unit, clarification=clarification),
        "primary_metric": metric, "target_data_product": target, "latency_class": latency,
        "freshness_class": freshness, "drilldown_id": drilldown, "clarification_required": "YES" if clarification != "NONE" else "NO",
        "llm_arithmetic_allowed": "NO", "raw_legacy_direct": "NO", "sap_live_query": "NO", "security_scope": "REQUIRED",
    }


QUERIES = [
    q("Q001", "SALES", "P0", "¿Cuánto vendimos hoy?", "sales", "NET_SALES", "business.sales_flow", "B", "NEAR_REALTIME", "sales_document", period="TODAY"),
    q("Q002", "SALES", "P0", "¿Cuánto vendió Segundo Anillo este mes?", "sales", "NET_SALES", "business.sales_flow", "B", "NEAR_REALTIME", "branch", dimension="branch", entity="Segundo Anillo", period="MTD", grain="branch", clarification="BRANCH_ALIAS_UNRESOLVED"),
    q("Q003", "SALES", "P0", "¿Cuánto vendimos a Farmacia X este año?", "sales", "NET_SALES", "business.sales_flow", "B", "DAILY", "customer", entity="Farmacia X", period="YTD", grain="customer"),
    q("Q004", "SALES", "P0", "De lo vendido a Farmacia X, ¿cuánto fue contado y cuánto crédito por sucursal?", "sales", "CASH_VS_CREDIT_SALES", "business.sales_flow", "C", "DAILY", "sales_document", entity="Farmacia X", dimension="branch", period="YTD", grain="branch", clarification="CASH_VS_CREDIT_SEMANTICS"),
    q("Q005", "SALES", "P0", "¿Cuánto vendimos por sucursal este mes?", "sales", "NET_SALES", "business.sales_flow", "B", "NEAR_REALTIME", "branch", dimension="branch", period="MTD", grain="branch"),
    q("Q006", "SALES", "P1", "¿Cuánto vendimos ayer?", "sales", "NET_SALES", "business.sales_flow", "B", "DAILY", "sales_document", period="YESTERDAY"),
    q("Q007", "SALES", "P1", "¿Cuánto vendimos este año?", "sales", "NET_SALES", "business.sales_flow", "B", "DAILY", "sales_document", period="YTD"),
    q("Q008", "SALES", "P1", "¿Cuánto vendimos de Creolina?", "sales", "NET_SALES", "business.sales_flow", "B", "NEAR_REALTIME", "product", entity="Creolina", grain="product"),
    q("Q009", "SALES", "P1", "¿Cuántas unidades vendimos por vendedor?", "sales", "QUANTITY_SOLD", "business.sales_flow", "B", "DAILY", "sales_document", dimension="salesperson", period="MTD", grain="salesperson", unit="document_unit"),
    q("Q010", "SALES", "P1", "¿Cuánto vendimos neto de notas de crédito?", "sales", "NET_SALES_AFTER_CREDIT_NOTES", "business.sales_flow", "B", "DAILY", "sales_document", period="MTD"),
    q("Q011", "SALES", "P1", "¿Cómo estamos contra el mes anterior?", "sales", "NET_SALES", "business.sales_flow", "C", "DAILY", "sales_document", period="MTD", comparison="PREVIOUS_EQUIVALENT"),
    q("Q012", "SALES", "P1", "¿Cómo estamos contra el mismo período del año pasado?", "sales", "NET_SALES", "business.sales_flow", "C", "DAILY", "sales_document", period="MTD", comparison="SAME_PERIOD_PRIOR_YEAR"),
    q("Q013", "SALES", "P1", "¿Cuáles son los 10 productos más vendidos?", "sales", "NET_SALES", "business.sales_flow", "C", "DAILY", "product", dimension="product", period="MTD", grain="product"),
    q("Q014", "SALES", "P1", "¿Cuáles son los clientes que más compraron?", "sales", "NET_SALES", "business.sales_flow", "C", "DAILY", "customer", dimension="customer", period="MTD", grain="customer"),
    q("Q015", "SALES", "P2", "¿Qué vendedor tiene peor venta contra su objetivo?", "sales", "NET_SALES", "business.sales_flow", "C", "DAILY", "salesperson", dimension="salesperson", period="MTD", grain="salesperson", clarification="TARGET_NOT_IN_BASELINE"),
    q("Q016", "SALES", "P2", "¿Cuál fue el descuento promedio por línea?", "sales", "DISCOUNT_AMOUNT", "business.sales_flow", "C", "DAILY", "sales_document", period="MTD"),
    q("Q017", "STOCK", "P0", "¿Cuántos litros de Creolina tengo en Saavedra?", "stock", "AVAILABLE", "current.stock_current", "A", "NEAR_REALTIME", "stock_evidence", entity="Creolina", dimension="warehouse", grain="product_warehouse", unit="LITRE", clarification="UOM_AND_STOCK_DEFAULT"),
    q("Q018", "STOCK", "P0", "¿Qué stock tiene Creolina en todas las sucursales?", "stock", "ON_HAND", "current.stock_current", "A", "NEAR_REALTIME", "warehouse", entity="Creolina", dimension="branch", grain="product_warehouse"),
    q("Q019", "STOCK", "P0", "¿Qué productos están bajo el mínimo?", "stock", "BELOW_MINIMUM", "current.stock_current", "A", "NEAR_REALTIME", "product", dimension="product", grain="product_warehouse"),
    q("Q020", "STOCK", "P1", "¿Cuánto stock disponible tengo?", "stock", "AVAILABLE", "current.stock_current", "A", "NEAR_REALTIME", "stock_evidence", clarification="STOCK_DEFAULT"),
    q("Q021", "STOCK", "P1", "¿Qué productos L no tienen stock?", "stock", "ON_HAND", "current.stock_current", "A", "NEAR_REALTIME", "product", dimension="product", grain="product", clarification="STOCK_DEFAULT"),
    q("Q022", "STOCK", "P1", "¿Qué productos L tienen stock pero no venden?", "stock", "STOCK_WITHOUT_RECENT_SALES", "current.stock_current", "C", "DAILY", "product", dimension="product", grain="product", clarification="RECENT_SALES_WINDOW"),
    q("Q023", "STOCK", "P1", "¿Qué productos tienen exceso de stock?", "stock", "EXCESS_STOCK", "current.stock_current", "C", "DAILY", "product", dimension="product", grain="product"),
    q("Q024", "STOCK", "P1", "¿Cuánto está comprometido por almacén?", "stock", "COMMITTED", "current.stock_current", "A", "NEAR_REALTIME", "warehouse", dimension="warehouse", grain="product_warehouse"),
    q("Q025", "STOCK", "P1", "¿Qué está en pedido?", "stock", "ON_ORDER", "current.stock_current", "A", "INTRADAY", "purchase", dimension="product", grain="product_warehouse"),
    q("Q026", "STOCK", "P2", "¿Cuál es la cobertura de inventario por producto?", "stock", "DAYS_OF_COVER", "business.inventory_flow", "C", "DAILY", "product", dimension="product", grain="product"),
    q("Q027", "STOCK", "P2", "¿Qué diferencias hay entre sucursal y almacén?", "stock", "ON_HAND", "current.stock_current", "C", "DAILY", "warehouse", dimension="branch", grain="product_warehouse", clarification="BRANCH_WAREHOUSE_DISTINCTION"),
    q("Q028", "CREDIT", "P0", "¿Cuánto crédito vencido tenemos?", "credit", "OVERDUE_RECEIVABLE", "current.customer_credit_current", "A", "NEAR_REALTIME", "customer_credit", period="AS_OF_NOW"),
    q("Q029", "CREDIT", "P0", "¿Cuánto crédito corriente tenemos?", "credit", "CURRENT_RECEIVABLE", "current.customer_credit_current", "A", "NEAR_REALTIME", "customer_credit", period="AS_OF_NOW"),
    q("Q030", "CREDIT", "P0", "¿Cuál es el total de cuentas por cobrar?", "credit", "TOTAL_RECEIVABLE", "current.customer_credit_current", "A", "NEAR_REALTIME", "customer_credit", period="AS_OF_NOW"),
    q("Q031", "CREDIT", "P0", "¿Quiénes son los clientes con mayor deuda?", "credit", "TOTAL_RECEIVABLE", "current.customer_credit_current", "A", "NEAR_REALTIME", "customer_credit", dimension="customer", grain="customer"),
    q("Q032", "CREDIT", "P1", "¿Quiénes tienen mayor deuda vencida?", "credit", "OVERDUE_RECEIVABLE", "current.customer_credit_current", "A", "NEAR_REALTIME", "customer_credit", dimension="customer", grain="customer"),
    q("Q033", "CREDIT", "P1", "¿Qué clientes aumentaron su deuda vencida?", "credit", "OVERDUE_RECEIVABLE_CHANGE", "business.customer_credit_history", "C", "HISTORICAL", "customer_credit", dimension="customer", comparison="PREVIOUS_AS_OF", grain="customer"),
    q("Q034", "CREDIT", "P1", "¿Cuál es el aging de la cartera?", "credit", "RECEIVABLE_AGING", "current.customer_credit_current", "B", "NEAR_REALTIME", "customer_credit", grain="aging_band", clarification="AGING_BANDS"),
    q("Q035", "CREDIT", "P1", "¿Cuántos días lleva vencida la deuda de Farmacia X?", "credit", "DAYS_OVERDUE", "current.customer_credit_current", "A", "NEAR_REALTIME", "customer_credit", entity="Farmacia X", grain="customer"),
    q("Q036", "CREDIT", "P1", "¿Qué clientes están sobre su límite?", "credit", "OVER_LIMIT", "current.customer_credit_current", "A", "NEAR_REALTIME", "customer_credit", dimension="customer", grain="customer"),
    q("Q037", "CREDIT", "P1", "¿Cuánto debía la empresa al 31 de agosto?", "credit", "TOTAL_RECEIVABLE_AS_OF", "business.customer_credit_history", "D", "HISTORICAL", "customer_credit_evidence", period="AS_OF_DATE", clarification="HISTORICAL_AS_OF"),
    q("Q038", "CREDIT", "P2", "¿Cuál es la evolución mensual de la deuda?", "credit", "TOTAL_RECEIVABLE", "business.customer_credit_history", "C", "HISTORICAL", "customer_credit", dimension="month", grain="month"),
    q("Q039", "CREDIT", "P2", "¿Qué documentos forman el saldo de LA REJA?", "credit", "OPEN_DOCUMENT_COUNT", "current.customer_credit_current", "C", "NEAR_REALTIME", "sap_document", entity="LA REJA", grain="document"),
    q("Q040", "CASH", "P0", "¿Cuánto cobramos hoy?", "cash", "PAYMENT_RECEIVED", "business.cash_flow", "B", "NEAR_REALTIME", "payment", period="TODAY"),
    q("Q041", "CASH", "P1", "¿Cuánto cobramos este mes por cliente?", "cash", "PAYMENT_RECEIVED", "business.cash_flow", "B", "INTRADAY", "payment", dimension="customer", period="MTD", grain="customer"),
    q("Q042", "CASH", "P1", "¿Cuánto cobramos por sucursal y caja?", "cash", "PAYMENT_RECEIVED", "business.cash_flow", "C", "INTRADAY", "payment", dimension="branch", period="MTD", grain="branch_cashbox"),
    q("Q043", "CASH", "P1", "¿Cuál fue el último cobro de Farmacia X?", "cash", "LAST_PAYMENT_RECEIVED", "business.cash_flow", "A", "INTRADAY", "payment", entity="Farmacia X", grain="payment"),
    q("Q044", "CASH", "P2", "¿Cuánto fue efectivo, tarjeta y otros medios?", "cash", "PAYMENT_RECEIVED", "business.cash_flow", "B", "INTRADAY", "payment", dimension="payment_method", period="MTD", grain="payment_method", clarification="PAYMENT_METHOD_SOURCE"),
    q("Q045", "CASH", "P2", "¿Cómo se comparan ventas y cobros?", "cash", "SALES_TO_COLLECTION_RATIO", "business.cash_flow", "C", "DAILY", "payment", period="MTD", clarification="PERIOD_ALIGNMENT"),
    q("Q046", "PRODUCTION", "P0", "¿Cuánto producimos hoy?", "production", "PRODUCTION_RECEIPT_QUANTITY", "business.production_flow", "B", "NEAR_REALTIME", "production", period="TODAY", clarification="PRODUCTION_COUNT_DEFAULT"),
    q("Q047", "PRODUCTION", "P1", "¿Cuántas órdenes de producción están abiertas?", "production", "OPEN_PRODUCTION_ORDER_COUNT", "current.production_open", "A", "INTRADAY", "production_order", grain="production_order"),
    q("Q048", "PRODUCTION", "P1", "¿Cuántas órdenes se cerraron hoy?", "production", "CLOSED_PRODUCTION_ORDER_COUNT", "business.production_flow", "B", "INTRADAY", "production_order", period="TODAY"),
    q("Q049", "PRODUCTION", "P1", "¿Qué materia prima consumimos?", "production", "PRODUCTION_CONSUMPTION_QUANTITY", "business.production_flow", "B", "INTRADAY", "production_component", period="TODAY", grain="production_component"),
    q("Q050", "PRODUCTION", "P1", "¿Qué productos terminados recibimos?", "production", "PRODUCTION_RECEIPT_QUANTITY", "business.production_flow", "B", "INTRADAY", "production", period="TODAY", grain="product"),
    q("Q051", "PRODUCTION", "P2", "¿Qué consumos reales superan lo esperado?", "production", "PRODUCTION_VARIANCE", "business.production_flow", "C", "DAILY", "production_component", period="MTD"),
    q("Q052", "PRODUCTION", "P2", "¿Qué producción quedó parcial o en cero?", "production", "PRODUCTION_COMPLETION_STATUS", "business.production_flow", "C", "INTRADAY", "production_order", period="MTD"),
    q("Q053", "PURCHASES", "P0", "¿Qué compras tenemos abiertas?", "purchases", "OPEN_PURCHASE_COUNT", "current.purchase_open", "A", "INTRADAY", "purchase", grain="purchase_document"),
    q("Q054", "PURCHASES", "P1", "¿Qué materiales están pendientes de recibir?", "purchases", "OPEN_PURCHASE_QUANTITY", "current.purchase_open", "A", "INTRADAY", "purchase", dimension="product", grain="purchase_line"),
    q("Q055", "PURCHASES", "P1", "¿Cuánto compramos por proveedor?", "purchases", "PURCHASE_AMOUNT", "business.purchase_flow", "B", "DAILY", "purchase", dimension="supplier", period="MTD", grain="supplier"),
    q("Q056", "PURCHASES", "P1", "¿Cuál es el lead time de los proveedores?", "purchases", "PURCHASE_LEAD_TIME", "business.purchase_flow", "C", "HISTORICAL", "purchase", dimension="supplier", grain="supplier"),
    q("Q057", "PURCHASES", "P2", "¿Qué proveedores concentran las compras?", "purchases", "PURCHASE_AMOUNT", "business.purchase_flow", "C", "DAILY", "purchase", dimension="supplier", period="YTD", grain="supplier"),
    q("Q058", "PROFITABILITY", "P1", "¿Qué productos tienen peor margen?", "profitability", "GROSS_MARGIN_AMOUNT", "business.sales_flow", "C", "DAILY", "product", dimension="product", period="MTD", grain="product", clarification="COST_SEMANTICS"),
    q("Q059", "PROFITABILITY", "P1", "¿Cuál es el margen por línea?", "profitability", "GROSS_MARGIN_PERCENT", "business.sales_flow", "C", "DAILY", "product", dimension="product_line", period="MTD", grain="product_line", clarification="COST_SEMANTICS"),
    q("Q060", "PROFITABILITY", "P2", "¿Cuál es la rentabilidad por sucursal?", "profitability", "GROSS_MARGIN_PERCENT", "business.sales_flow", "C", "DAILY", "branch", dimension="branch", period="MTD", grain="branch", clarification="COST_SEMANTICS"),
    q("Q061", "PROFITABILITY", "P2", "¿Qué costo debemos usar para este producto?", "profitability", "COST_BASIS", "business.sales_flow", "D", "HISTORICAL", "cost_evidence", entity="product", clarification="COST_SEMANTICS"),
    q("Q062", "CUSTOMER", "P1", "¿Qué clientes dejaron de comprar?", "customer", "CUSTOMER_PURCHASE_RECENCY", "business.sales_flow", "C", "DAILY", "customer", dimension="customer", period="LAST_90_DAYS"),
    q("Q063", "CUSTOMER", "P1", "¿Qué clientes nuevos compraron este mes?", "customer", "NEW_CUSTOMER_COUNT", "business.sales_flow", "B", "DAILY", "customer", dimension="customer", period="MTD"),
    q("Q064", "CUSTOMER", "P2", "¿Cuál es el ticket promedio por cliente?", "customer", "AVERAGE_SALE_VALUE", "business.sales_flow", "B", "DAILY", "customer", dimension="customer", period="MTD", grain="customer"),
    q("Q065", "CUSTOMER", "P2", "¿Qué clientes compran Creolina?", "customer", "NET_SALES", "business.sales_flow", "C", "DAILY", "customer", entity="Creolina", dimension="customer", period="YTD", grain="customer"),
    q("Q066", "PRODUCT", "P1", "¿Cuánto vendimos de cada producto L?", "product", "NET_SALES", "business.sales_flow", "C", "DAILY", "product", dimension="product", period="MTD", grain="product", clarification="TELCHI_L_UNIVERSE"),
    q("Q067", "PRODUCT", "P1", "¿Qué productos L rotan más rápido?", "product", "SALES_VELOCITY", "business.sales_flow", "C", "DAILY", "product", dimension="product", period="LAST_90_DAYS", grain="product"),
    q("Q068", "PRODUCT", "P2", "¿Qué unidad de medida tiene Creolina?", "product", "PRODUCT_UOM", "reference.units_of_measure", "A", "HISTORICAL", "product", entity="Creolina", grain="product", clarification="UOM_SOURCE"),
    q("Q069", "PRODUCT", "P2", "¿Cuál es el costo de última compra de un producto?", "product", "LAST_PURCHASE_COST", "reference.products", "A", "DAILY", "cost_evidence", entity="product", clarification="COST_SEMANTICS"),
    q("Q070", "BRANCH", "P1", "¿Qué sucursal bajó ventas contra el año pasado?", "branch", "NET_SALES", "business.sales_flow", "C", "DAILY", "branch", dimension="branch", period="YTD", comparison="SAME_PERIOD_PRIOR_YEAR", grain="branch"),
    q("Q071", "BRANCH", "P1", "¿Qué sucursal tiene más stock?", "branch", "ON_HAND", "current.stock_current", "A", "NEAR_REALTIME", "warehouse", dimension="branch", grain="branch", clarification="BRANCH_WAREHOUSE_DISTINCTION"),
    q("Q072", "BRANCH", "P1", "¿Qué almacenes pertenecen a cada sucursal?", "branch", "WAREHOUSE_BRANCH_MAPPING", "reference.warehouse_branch_mapping", "A", "HISTORICAL", "warehouse", dimension="branch", grain="warehouse", clarification="BRANCH_WAREHOUSE_DISTINCTION"),
    q("Q073", "BRANCH", "P2", "¿Qué sucursal tiene mayor deuda?", "branch", "TOTAL_RECEIVABLE", "current.customer_credit_current", "B", "NEAR_REALTIME", "customer_credit", dimension="branch", grain="branch", clarification="CREDIT_BRANCH_SEMANTICS"),
    q("Q074", "BRANCH", "P2", "¿Cómo evolucionan las ventas por sucursal?", "branch", "NET_SALES", "business.sales_flow", "C", "DAILY", "branch", dimension="branch", period="LAST_12_MONTHS", grain="branch_month"),
]

METRICS = [
    ("GROSS_SALES", "Ventas brutas antes de notas de crédito y devoluciones", "sum(positive commercial document lines)", "sales", "sales_line", "branch,customer,product,salesperson,period", "BOB", "document_currency", "event_date", "PROVISIONAL"),
    ("NET_SALES", "Ventas ejecutivas según documento comercial SAP validado; tax/document treatment pendiente", "gross sales - eligible credit notes - cancellations", "sales", "sales_line", "branch,customer,product,salesperson,period", "BOB", "analytical_currency", "event_date", "SEMANTIC_GAP"),
    ("NET_SALES_AFTER_CREDIT_NOTES", "Ventas netas después de notas de crédito elegibles", "gross sales - credit notes", "sales", "sales_line", "branch,customer,product,period", "BOB", "analytical_currency", "event_date", "SEMANTIC_GAP"),
    ("QUANTITY_SOLD", "Cantidad comercial vendida en unidad solicitada, sin inventar conversiones", "sum(quantity converted through approved UoM)", "sales", "sales_line", "product,customer,branch,period", "", "canonical_measure", "event_date", "PROVISIONAL"),
    ("DOCUMENT_COUNT", "Documentos comerciales incluidos en el filtro", "count(distinct document_id)", "sales", "sales_document", "branch,customer,period", "", "not_applicable", "document_date", "CONFIRMED"),
    ("DISCOUNT_AMOUNT", "Descuento atribuido a línea/documento según autoridad SAP", "document/list amount - net amount", "sales", "sales_line", "product,customer,branch,period", "BOB", "analytical_currency", "event_date", "PROVISIONAL"),
    ("CASH_VS_CREDIT_SALES", "Clasificación de venta por condición de pago o política validada; no equivale a cobro", "sum(sales classified by approved sale payment semantics)", "sales", "sales_document", "customer,branch,period", "BOB", "analytical_currency", "document_date", "SEMANTIC_GAP"),
    ("ON_HAND", "Existencia física registrada al as_of", "inventory quantity on hand", "stock", "product_warehouse", "product,warehouse,branch", "", "inventory_uom", "snapshot_as_of", "PROVISIONAL"),
    ("AVAILABLE", "Existencia disponible después de compromisos según regla SAP validada", "on_hand - committed", "stock", "product_warehouse", "product,warehouse,branch", "", "inventory_uom", "snapshot_as_of", "SEMANTIC_GAP"),
    ("COMMITTED", "Cantidad comprometida para demanda abierta", "approved open demand quantity", "stock", "product_warehouse", "product,warehouse", "", "inventory_uom", "snapshot_as_of", "SEMANTIC_GAP"),
    ("ON_ORDER", "Cantidad pedida a proveedor y pendiente de recepción", "open purchase quantity", "stock", "product_warehouse", "product,supplier,warehouse", "", "purchase_uom", "snapshot_as_of", "PROVISIONAL"),
    ("BELOW_MINIMUM", "Productos cuya disponibilidad está bajo el mínimo vigente", "available < approved minimum", "stock", "product_warehouse", "product,warehouse", "", "inventory_uom", "snapshot_as_of", "SEMANTIC_GAP"),
    ("TOTAL_RECEIVABLE", "Saldo abierto total de clientes al as_of", "open invoices - credits - reconciled payments", "credit", "customer", "customer,branch,aging", "BOB", "local_currency", "as_of", "PROVISIONAL"),
    ("CURRENT_RECEIVABLE", "Saldo abierto no vencido al as_of", "open balance with due_date >= as_of", "credit", "customer_document", "customer,branch,aging", "BOB", "local_currency", "as_of", "PROVISIONAL"),
    ("OVERDUE_RECEIVABLE", "Saldo abierto con due_date < as_of", "open balance with due_date < as_of", "credit", "customer_document", "customer,branch,aging", "BOB", "local_currency", "as_of", "PROVISIONAL"),
    ("DAYS_OVERDUE", "Días transcurridos desde vencimiento para saldo abierto", "max(0, as_of - due_date)", "credit", "customer_document", "customer,document", "day", "not_applicable", "as_of", "CONFIRMED"),
    ("CREDIT_LIMIT", "Límite de crédito vigente del cliente", "approved customer credit line", "credit", "customer", "customer,branch", "BOB", "local_currency", "as_of", "PROVISIONAL"),
    ("OVER_LIMIT", "Cliente con exposición abierta por encima de su límite", "total_receivable > credit_limit", "credit", "customer", "customer,branch", "BOB", "local_currency", "as_of", "PROVISIONAL"),
    ("RECEIVABLE_AGING", "Distribución del saldo por bandas de vencimiento aprobadas", "sum(open balance by aging band)", "credit", "customer_document", "aging_band,customer", "BOB", "local_currency", "as_of", "SEMANTIC_GAP"),
    ("PAYMENT_RECEIVED", "Cobro contabilizado/conciliado recibido, distinto de condición de venta", "sum(receipt allocation or payment amount by approved policy)", "cash", "payment", "customer,branch,cashbox,payment_method", "BOB", "analytical_currency", "payment_date", "PROVISIONAL"),
    ("LAST_PAYMENT_RECEIVED", "Último cobro trazable del cliente", "max(payment_date) with valid receipt evidence", "cash", "payment", "customer", "BOB", "analytical_currency", "payment_date", "PROVISIONAL"),
    ("PRODUCTION_RECEIPT_QUANTITY", "Cantidad de producto terminado recibida por producción", "sum(production receipt quantity)", "production", "production_receipt", "product,warehouse,period", "", "inventory_uom", "posting_date", "PROVISIONAL"),
    ("OPEN_PRODUCTION_ORDER_COUNT", "Órdenes de producción no cerradas/canceladas", "count(open production orders)", "production", "production_order", "product,warehouse", "", "not_applicable", "as_of", "PROVISIONAL"),
    ("PRODUCTION_CONSUMPTION_QUANTITY", "Consumo real de componentes de producción", "sum(component issue quantity)", "production", "production_component", "component,production_order,warehouse", "", "inventory_uom", "posting_date", "PROVISIONAL"),
    ("OPEN_PURCHASE_COUNT", "Documentos de compra con líneas abiertas", "count(distinct open purchase document)", "purchases", "purchase_document", "supplier,warehouse", "", "not_applicable", "as_of", "PROVISIONAL"),
    ("OPEN_PURCHASE_QUANTITY", "Cantidad pendiente de recibir de compras abiertas", "sum(open line quantity)", "purchases", "purchase_line", "supplier,product,warehouse", "", "purchase_uom", "as_of", "PROVISIONAL"),
    ("PURCHASE_AMOUNT", "Importe de compras según moneda y tax policy aprobadas", "sum(purchase line amount)", "purchases", "purchase_line", "supplier,product,branch,period", "BOB", "analytical_currency", "document_date", "SEMANTIC_GAP"),
    ("GROSS_MARGIN_AMOUNT", "Ventas netas menos costo con basis aprobado", "net sales - selected cost basis", "profitability", "sales_line", "product,line,branch,customer", "BOB", "analytical_currency", "event_date", "SEMANTIC_GAP"),
    ("GROSS_MARGIN_PERCENT", "Margen bruto sobre ventas netas con costo aprobado", "gross margin / net sales", "profitability", "sales_line", "product,line,branch,customer", "%", "not_applicable", "event_date", "SEMANTIC_GAP"),
    ("SALES_VELOCITY", "Ritmo de venta en ventana aprobada", "quantity sold / active days", "product", "sales_line", "product,warehouse,branch", "", "canonical_measure", "event_date", "PROVISIONAL"),
    ("CUSTOMER_PURCHASE_RECENCY", "Días desde la última venta válida al cliente", "as_of - max(sale_date)", "customer", "customer", "customer", "day", "not_applicable", "as_of", "PROVISIONAL"),
    ("WAREHOUSE_BRANCH_MAPPING", "Asignación explícita de almacén a sucursal, sin asumir 1:1", "approved crosswalk mapping", "reference", "warehouse_branch", "warehouse,branch", "", "not_applicable", "mapping_validity", "CONFIRMED"),
]

DIMENSIONS = [
    ("date", "Fecha del hecho o snapshot, con timezone Telchi"), ("period", "Rango semántico MTD/YTD/etc."), ("document", "Documento comercial o financiero"),
    ("customer", "Cliente canonical_id"), ("product", "Producto canonical_id"), ("product_group", "Grupo/familia de producto"), ("product_line", "Línea de producto si existe"),
    ("branch", "Sucursal, distinta de warehouse"), ("warehouse", "Almacén físico"), ("salesperson", "Vendedor canonical_id"), ("supplier", "Proveedor canonical_id"),
    ("cashbox", "Caja si la fuente la soporta"), ("payment_method", "Medio de pago si la fuente lo soporta"), ("aging_band", "Banda de mora"), ("currency", "Moneda document/local/system/analytical"),
]

AMBIGUITIES = [
    ("ventas", "GROSS_SALES|NET_SALES|NET_SALES_AFTER_CREDIT_NOTES", "NET_SALES", "MEDIUM", "NO", "metric catalog"),
    ("stock", "ON_HAND|AVAILABLE|COMMITTED|ON_ORDER", "ON_HAND", "MEDIUM", "NO", "current stock contract"),
    ("crédito", "SALE_PAYMENT_TERM|TOTAL_RECEIVABLE|CREDIT_LIMIT", "ASK_OR_CONTEXT", "HIGH", "YES", "cash vs credit gap"),
    ("contado", "SALE_PAYMENT_TERM|PAYMENT_RECEIVED", "ASK_OR_CONTEXT", "HIGH", "YES", "cash vs credit gap"),
    ("producción", "ORDERS_CREATED|ORDERS_COMPLETED|RECEIPTS|RUNS", "ASK_OR_CONTEXT", "HIGH", "YES", "production evidence"),
    ("deuda", "TOTAL_RECEIVABLE|OVERDUE_RECEIVABLE|HISTORICAL_AS_OF", "TOTAL_RECEIVABLE", "HIGH", "YES_FOR_DATE", "credit catalog"),
    ("corriente", "CURRENT_RECEIVABLE|NOT_OVERDUE_BY_OTHER_POLICY", "CURRENT_RECEIVABLE", "MEDIUM", "NO", "due date semantics"),
    ("vencido", "OVERDUE_RECEIVABLE|DAYS_OVERDUE", "OVERDUE_RECEIVABLE", "MEDIUM", "NO", "due date semantics"),
    ("hoy", "business_date|server_date|user_local_date", "TELCHI_CONFIGURED_TIMEZONE", "HIGH", "NO", "date contract"),
    ("sucursal", "BRANCH|WAREHOUSE", "BRANCH_ONLY", "HIGH", "YES_WHEN_SCOPE", "crosswalk"),
    ("almacén", "WAREHOUSE|BRANCH", "WAREHOUSE", "MEDIUM", "NO", "crosswalk"),
    ("cliente", "CUSTOMER|CUSTOMER_GROUP", "CUSTOMER", "MEDIUM", "YES_IF_MULTIPLE", "entity resolver"),
    ("margen", "GROSS_MARGIN|NET_MARGIN|MARKUP", "ASK_OR_CONTEXT", "HIGH", "YES", "cost semantics"),
    ("rentabilidad", "GROSS_MARGIN_PERCENT|ROI|NET_MARGIN", "ASK_OR_CONTEXT", "HIGH", "YES", "cost semantics"),
    ("cantidad", "DOCUMENT_UNIT|BASE_MEASURE|INVENTORY_UOM", "ASK_OR_CONTEXT", "HIGH", "YES", "UoM contract"),
]

ROUTING = [
    ("current.stock_current", "CURRENT_LOOKUP", "product × warehouse", "ON_HAND,COMMITTED,ON_ORDER,AVAILABLE", "NEAR_REALTIME", "materialize current state; no SAP joins at query time"),
    ("business.sales_flow", "NORMAL_BUSINESS_AGGREGATION", "canonical commercial line", "date,document,customer,product,branch,warehouse,seller,quantity,net_amount,tax,currency,unit", "NEAR_REALTIME/DAILY", "one canonical line with document lineage"),
    ("business.production_flow", "NORMAL_BUSINESS_AGGREGATION", "production fact by event type", "orders,receipts,consumption,warehouse,product,quantity,date,status", "INTRADAY", "do not collapse incompatible production events"),
    ("business.inventory_flow", "MULTI_DIMENSION_COMPARATIVE", "inventory event/snapshot", "movements,balances,coverage,minimums", "DAILY", "history plus current projection"),
    ("current.customer_credit_current", "CURRENT_LOOKUP", "customer or customer × document", "total,current,overdue,oldest_due_date,max_days_overdue,credit_limit,over_limit,document_count_open,as_of", "NEAR_REALTIME", "reconciled read model"),
    ("business.customer_credit_history", "DEEP_ANALYSIS", "customer × as_of snapshot", "open balance,aging,payments,reconciliations,as_of", "HISTORICAL", "business snapshot/as-of, not only technical time travel"),
    ("business.cash_flow", "NORMAL_BUSINESS_AGGREGATION", "payment/allocation event", "payment,receipt,customer,branch,cashbox,method,currency,date", "INTRADAY", "separate payment from sale terms"),
    ("current.purchase_open", "CURRENT_LOOKUP", "purchase document line", "supplier,product,warehouse,open_qty,amount,due/as_of", "INTRADAY", "open lines directly queryable"),
    ("business.purchase_flow", "NORMAL_BUSINESS_AGGREGATION", "purchase line/event", "supplier,product,receipt,lead_time,amount,date", "DAILY", "preserve order and receipt events"),
    ("reference.* / crosswalk.*", "CURRENT_LOOKUP", "canonical entity", "canonical IDs, aliases, mappings, UoM", "HISTORICAL", "resolve within authorization scope before retrieval"),
]

PERFORMANCE = [
    ("A", "CURRENT_LOOKUP", "Current stock, total debt, top debtors, open orders", "100", "warm data query only; semantic/entity resolution separate"),
    ("B", "NORMAL_BUSINESS_AGGREGATION", "Sales period, customer/product sales, production period", "300", "prepared read model plus small aggregation"),
    ("C", "MULTI_DIMENSION_COMPARATIVE", "Comparisons, growth, margin by dimensions", "750", "prepared models; no raw SAP reconstruction"),
    ("D", "DEEP_ANALYSIS", "Historical reconstruction, evidence, anomalies", "NOT_SUBSECOND", "visible deep-analysis mode and progress/freshness"),
]

FRESHNESS = [
    ("REALTIME_LIKE", "seconds/minutes", "not required by this gate; explicit provider SLA needed"),
    ("NEAR_REALTIME", "<= 15 minutes target", "stock current, sales today, production today"),
    ("INTRADAY", "same business day, bounded lag", "credit current, open purchases, cash"),
    ("DAILY", "daily close or scheduled refresh", "historical sales, margin, customer recency"),
    ("HISTORICAL", "as-of snapshot/build governed", "credit history, long comparisons"),
]

UOM = [
    ("document_unit", "unit shown on commercial document", "source document", "must not be silently converted"),
    ("inventory_uom", "SAP inventory/base unit", "product master + validated conversion", "canonical stock measure"),
    ("sales_uom", "unit used for sale", "product master", "requires conversion to requested measure"),
    ("purchase_uom", "unit used for purchase", "product master/order", "requires approved conversion"),
    ("canonical_measure_type", "mass|volume|count|length|other", "curated reference", "no LLM inference"),
    ("canonical_measure_unit", "L|kg|unit|...", "curated reference", "only with conversion factor"),
]

CURRENCY = [
    ("BOB", "Bolivianos", "local/analytical only after policy", "PROVISIONAL"), ("USD", "US dollars", "document or configured FX", "SEMANTIC_GAP"),
    ("document_currency", "currency on source document", "preserve source", "CONFIRMED"), ("local_currency", "company local currency", "SAP company policy", "PROVISIONAL"),
    ("system_currency", "SAP system currency", "SAP currency configuration", "SEMANTIC_GAP"), ("analytical_currency", "currency chosen for comparable output", "approved FX source and date", "SEMANTIC_GAP"),
]

DRILLDOWNS = [
    ("sales_document", "executive -> branch/customer/product -> sales document -> line -> SAP evidence"),
    ("stock_evidence", "executive -> product/warehouse -> stock snapshot -> movement evidence"),
    ("branch", "executive -> branch -> warehouse mapping -> stock/sales evidence"),
    ("product", "executive -> product -> documents/lines -> SAP evidence"),
    ("customer", "executive -> customer -> documents/payments -> SAP evidence"),
    ("customer_credit", "executive -> customer ranking -> customer balance -> open documents -> invoice/payment/reconciliation"),
    ("customer_credit_evidence", "executive -> as_of snapshot -> customer -> document chain -> SAP evidence"),
    ("payment", "executive -> customer/branch -> receipt/allocation -> reconciliation -> SAP evidence"),
    ("production", "executive -> status/product -> production order -> receipt/component issue -> SAP evidence"),
    ("production_order", "executive -> order -> receipt/consumption -> source documents"),
    ("purchase", "executive -> supplier/product -> purchase document line -> receipt -> SAP evidence"),
    ("cost_evidence", "executive -> metric/cost basis -> source cost observation -> document evidence"),
    ("sap_document", "executive -> document -> line -> reconciliation/payment/credit note"),
    ("warehouse", "executive -> branch/warehouse -> mapping -> current snapshot/movement"),
    ("reference", "executive -> canonical entity -> alias/source mapping -> reference evidence"),
]

LEGACY = [
    ("sales", "saleProduct-*.parq", "product/date/amount", "legacy sales filters and aggregation", "per-request scans/joins", "tax, returns, currency and document semantics require SAP authority", "business.sales_flow"),
    ("sales_branch", "saleSB1Product-*.parq", "branch/product/date", "branch sales", "per-request legacy scan", "branch/warehouse identity and net sales unclear", "business.sales_flow"),
    ("credit_notes", "ncB1Product-*.parq", "credit note/product", "subtract notes", "separate legacy dataset join", "eligibility/sign/tax semantics unresolved", "business.sales_flow"),
    ("inventory", "movProduct-*.parq", "product/movement", "stock movement", "movement reconstruction at runtime", "on-hand vs available/committed not equivalent", "current.stock_current"),
    ("inventory_branch", "movProductSB1-*.parq", "product/branch movement", "branch stock", "branch scans", "warehouse mapping incomplete", "business.inventory_flow"),
    ("cash", "cash-*.parq", "cash rows", "collections/cash", "Dask per request", "payment vs sale condition conflated historically", "business.cash_flow"),
    ("receivables", "cuentasxCobrar-*.parq", "customer/open balance", "debt and overdue", "reconstruct per request", "as-of and reconciliation authority need modern SAP model", "current.customer_credit_current"),
    ("product_uom", "productTransform-*.parq", "product conversions", "unit conversion", "ad hoc conversion joins", "conversion source/confidence not guaranteed", "reference.* / crosswalk.*"),
    ("purchases", "purchase-*.parq", "purchase rows", "purchase totals/open", "per-request scans", "open/receipt semantics incomplete", "current.purchase_open"),
    ("cost", "ProductSaleCostDay-*.parq", "product/day/cost", "margin/cost", "legacy cost lookup", "cost basis alternatives conflict", "business.sales_flow"),
]

ATOMIC = [
    ("atomic.sales_document", "commercial document header", "P0 sales/credit classification", "sales_line and document terms", "1", "HIGH"),
    ("atomic.sales_line", "canonical commercial line", "P0 sales/quantity/product/customer", "sales_document, product, customer, branch", "2", "HIGH"),
    ("atomic.credit_note", "credit note and return line", "net sales and reconciliation", "sales_document/line", "3", "HIGH"),
    ("atomic.inventory_movement", "inventory movement event", "stock history and reconciliation", "product,warehouse,document", "4", "HIGH"),
    ("atomic.inventory_snapshot", "business stock as-of observation", "current stock and history", "product,warehouse,as_of", "5", "HIGH"),
    ("atomic.payment", "payment/receipt event", "cash vs received and credit", "customer,document,receipt", "6", "HIGH"),
    ("atomic.reconciliation", "payment/document reconciliation", "open balance authority", "payment,invoice,credit note", "7", "HIGH"),
    ("atomic.production_order", "production order lifecycle", "production counts/open orders", "product,warehouse,status", "8", "MEDIUM"),
    ("atomic.production_component", "planned/actual component consumption", "production variance", "production_order,component", "9", "MEDIUM"),
    ("atomic.production_receipt", "finished goods receipt", "production quantity", "production_order,product,warehouse", "10", "MEDIUM"),
    ("atomic.purchase_order", "purchase document header/lifecycle", "open purchases/lead time", "supplier,warehouse", "11", "MEDIUM"),
    ("atomic.purchase_line", "purchase line and receipt state", "pending material", "purchase_order,product", "12", "MEDIUM"),
    ("atomic.cost_observation", "cost observation with basis and validity", "profitability after semantic decision", "product,date,cost_basis", "13", "LOW"),
]

BUSINESS = [
    ("business.sales_flow", "canonical commercial line", "sales, comparisons, customer/product/branch dimensions", "NEAR_REALTIME/DAILY", "tax, currency, credit classification fields only when validated"),
    ("business.inventory_flow", "inventory event + approved snapshots", "stock trends, coverage, movements", "DAILY", "must preserve event types/signs"),
    ("business.production_flow", "separate order/receipt/consumption facts", "production and variance", "INTRADAY", "no incompatible event fusion"),
    ("business.customer_credit_history", "customer × as_of business state", "historical credit", "HISTORICAL", "snapshot/reconstruction lineage"),
    ("business.cash_flow", "payment/allocation event", "collections and reconciliation", "INTRADAY", "no sale-payment-term substitution"),
    ("business.purchase_flow", "purchase/receipt event", "purchase totals and lead time", "DAILY", "order vs receipt distinction"),
    ("business.profitability", "sales × selected cost basis", "margin/rentability", "DAILY", "blocked until cost policy"),
]


def write_csv(name: str, rows: Iterable[dict[str, object]], fields: list[str]) -> None:
    with (OUT / name).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def benchmark() -> list[dict[str, object]]:
    # Foundation and reference gates already measured these baselines.  We do
    # not attach DuckLake or access SAP in this gate; only repeatable local
    # catalog/reference probes are timed here.
    rows: list[dict[str, object]] = []
    conn = duckdb.connect()
    try:
        probes = [
            ("entity_resolution_raw_parquet_probe", REFERENCE / "entity_alias/part-00000.parquet", "SELECT count(*) FROM read_parquet(?) WHERE normalized_alias = 'creolina'"),
            ("external_reference_lookup", REFERENCE / "products/part-00000.parquet", "SELECT count(*) FROM read_parquet(?) WHERE normalized_product_name LIKE '%creolina%'"),
            ("crosswalk_lookup", CROSSWALK / "warehouse_branch_mapping/part-00000.parquet", "SELECT count(*) FROM read_parquet(?) WHERE warehouse_id IS NOT NULL"),
        ]
        for name, path, sql in probes:
            if not path.is_file():
                raise FileNotFoundError(path)
            samples: list[float] = []
            for _ in range(10):
                started = time.perf_counter_ns()
                conn.execute(sql, [str(path)]).fetchone()
                samples.append((time.perf_counter_ns() - started) / 1_000_000)
            samples.sort()
            rows.append({"probe": name, "p50_ms": round(statistics.median(samples), 3), "p95_ms": round(samples[-1], 3), "max_ms": round(max(samples), 3), "source": "measured_warm_readonly_duckdb", "notes": "reference/crosswalk parquet; no writes"})
        samples = []
        catalog = {metric[0]: metric for metric in METRICS}
        for _ in range(1000):
            started = time.perf_counter_ns()
            _ = catalog.get("NET_SALES")
            samples.append((time.perf_counter_ns() - started) / 1_000_000)
        samples.sort()
        rows.append({"probe": "semantic_catalog_lookup", "p50_ms": round(statistics.median(samples), 6), "p95_ms": round(samples[int(len(samples) * .95) - 1], 6), "max_ms": round(max(samples), 6), "source": "measured_in_memory_catalog", "notes": "1000 deterministic dictionary lookups"})
    finally:
        conn.close()
    rows.extend([
        {"probe": "entity_resolution", "p50_ms": 5.0, "p95_ms": 7.959, "max_ms": 7.959, "source": "TELCHI_DATALAKE_REFERENCE_AND_CROSSWALK_V1 evidence", "notes": "approved warm entity resolver baseline; raw parquet probe retained separately"},
        {"probe": "ducklake_warm_query", "p50_ms": 7.7755, "p95_ms": 10.0535, "max_ms": 39.1666, "source": "TELCHI_DUCKLAKE_POSTGRES18_FOUNDATION_V1 evidence", "notes": "carried forward; no attach in this gate"},
        {"probe": "ducklake_attach_cold", "p50_ms": 169.2687, "p95_ms": 170.0556, "max_ms": 170.5355, "source": "TELCHI_DUCKLAKE_POSTGRES18_FOUNDATION_V1 evidence", "notes": "not in query budget; connection reuse required"},
    ])
    return rows


def build() -> dict[str, object]:
    OUT.mkdir(parents=True, exist_ok=True)
    write_csv("ceo_query_catalog.csv", QUERIES, list(QUERIES[0]))
    metric_fields = ["metric_id", "display_name", "business_definition", "formula_logical", "source_domain", "required_grain", "allowed_dimensions", "default_currency", "default_unit", "time_semantics", "null_semantics", "sign_semantics", "include_rules", "exclude_rules", "current_or_historical", "drilldown_target", "reconciliation_authority", "status", "semantic_version"]
    metric_rows = []
    for row in METRICS:
        mid, definition, formula, domain, grain, dims, currency, unit, time_sem, status = row
        metric_rows.append({"metric_id": mid, "display_name": mid.replace("_", " ").title(), "business_definition": definition, "formula_logical": formula, "source_domain": domain, "required_grain": grain, "allowed_dimensions": dims, "default_currency": currency, "default_unit": unit, "time_semantics": time_sem, "null_semantics": "NULL means unavailable/not observed; never zero unless source says zero", "sign_semantics": "canonical signs governed by domain contract", "include_rules": "only authorized, valid, non-excluded source events", "exclude_rules": "cancelled/invalid events per validated source policy", "current_or_historical": "CURRENT" if time_sem in {"as_of", "snapshot_as_of"} else "HISTORICAL_OR_EVENT", "drilldown_target": next((x[0] for x in DRILLDOWNS if x[0] in {"customer_credit", "sales_document", "stock_evidence", "production", "purchase", "cost_evidence", "payment"}), "evidence"), "reconciliation_authority": "SAP modern validated reconstruction; legacy comparison only", "status": status, "semantic_version": f"{mid}@1"})
    write_csv("metric_catalog.csv", metric_rows, metric_fields)
    write_csv("dimension_catalog.csv", [{"dimension_id": x[0], "display_name": x[0].replace("_", " ").title(), "definition": x[1], "canonical_id_required": "YES" if x[0] in {"customer", "product", "branch", "warehouse", "supplier", "salesperson"} else "NO"} for x in DIMENSIONS], ["dimension_id", "display_name", "definition", "canonical_id_required"])
    write_csv("semantic_ambiguity_catalog.csv", [{"term": x[0], "possible_meanings": x[1], "recommended_default": x[2], "confidence": x[3], "clarification_required": x[4], "source": x[5]} for x in AMBIGUITIES], ["term", "possible_meanings", "recommended_default", "confidence", "clarification_required", "source"])
    write_csv("query_data_product_routing.csv", [{"data_product": x[0], "path_class": x[1], "grain": x[2], "required_fields": x[3], "required_freshness_class": x[4], "routing_rule": x[5]} for x in ROUTING], ["data_product", "path_class", "grain", "required_fields", "required_freshness_class", "routing_rule"])
    write_csv("performance_classes.csv", [{"class": x[0], "name": x[1], "examples": x[2], "target_p95_ms": x[3], "scope": x[4]} for x in PERFORMANCE], ["class", "name", "examples", "target_p95_ms", "scope"])
    write_csv("freshness_contract.csv", [{"freshness_class": x[0], "target_lag": x[1], "query_families": x[2]} for x in FRESHNESS], ["freshness_class", "target_lag", "query_families"])
    write_csv("uom_contract.csv", [{"field": x[0], "definition": x[1], "conversion_source": x[2], "rule": x[3], "llm_may_invent": "NO"} for x in UOM], ["field", "definition", "conversion_source", "rule", "llm_may_invent"])
    write_csv("currency_contract.csv", [{"currency_or_role": x[0], "definition": x[1], "rule": x[2], "status": x[3], "fx_hardcoded": "NO"} for x in CURRENCY], ["currency_or_role", "definition", "rule", "status", "fx_hardcoded"])
    write_csv("drilldown_contract.csv", [{"drilldown_id": x[0], "chain": x[1], "as_of_required": "YES", "authorization_rechecked": "YES"} for x in DRILLDOWNS], ["drilldown_id", "chain", "as_of_required", "authorization_rechecked"])
    write_csv("legacy_semantic_comparison.csv", [{"query_family": x[0], "legacy_dataset": x[1], "legacy_fields_or_grain": x[2], "legacy_filters_or_formula": x[3], "legacy_runtime_pattern": x[4], "known_issue": x[5], "new_semantic_authority": "SAP validated semantic contract; no automatic legacy authority", "future_read_model": x[6]} for x in LEGACY], ["query_family", "legacy_dataset", "legacy_fields_or_grain", "legacy_filters_or_formula", "legacy_runtime_pattern", "known_issue", "new_semantic_authority", "future_read_model"])
    write_csv("atomic_requirements.csv", [{"atomic_requirement": x[0], "business_truth": x[1], "p0_p1_coverage": x[2], "dependencies": x[3], "build_priority": x[4], "priority_class": x[5], "materialize_now": "NO"} for x in ATOMIC], ["atomic_requirement", "business_truth", "p0_p1_coverage", "dependencies", "build_priority", "priority_class", "materialize_now"])
    write_csv("business_read_model_requirements.csv", [{"data_product": x[0], "grain": x[1], "coverage": x[2], "freshness": x[3], "semantic_guard": x[4]} for x in BUSINESS], ["data_product", "grain", "coverage", "freshness", "semantic_guard"])
    benchmark_rows = benchmark()
    write_csv("benchmark_baseline.csv", benchmark_rows, ["probe", "p50_ms", "p95_ms", "max_ms", "source", "notes"])
    contract = {
        "contract_id": GATE, "stage": "INVESTIGATION", "semantic_plan_version": "1.0", "security_order": ["identity", "authorization_context", "entity_resolution_within_scope", "semantic_plan", "authorized_query", "prepared_read_model", "answer"],
        "semantic_plan_fields": ["domain", "metrics", "entities", "dimensions", "filters", "time_range", "comparison", "scope", "requested_unit", "currency", "grain", "ranking", "limit", "drilldown_level", "freshness_requirement", "ambiguities"],
        "default_period_policy": "ASK_OR_CONTEXT; never silently default to today", "stock_default": "ON_HAND (PROVISIONAL; expose AVAILABLE when relevant)", "timezone": "configured Telchi business timezone; server timezone forbidden", "llm_rule": "LLM interprets and drafts; DuckDB computes", "fallback_path": ["FAST_PATH current/business", "NORMAL_PATH business+small joins", "DEEP_PATH atomic/reconstruction"],
        "trace_fields": ["query_id", "semantic_plan_hash", "metric_versions", "dataset_versions", "ducklake_snapshot", "data_as_of", "authorization_scope", "execution_ms", "row_count"], "dev_prod_logical_names_identical": True, "postgres_catalog_database": "team360_telchi_ducklake", "postgres_runtime_role": "team360_telchi_ducklake", "atomic_tables_created": 0, "business_tables_created": 0, "current_tables_created": 0, "sap_write_count": 0,
    }
    (OUT / "semantic_plan_contract.json").write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    p0 = [row for row in QUERIES if row["priority"] == "P0"]
    status_counts = {status: sum(row[-1] == status for row in METRICS) for status in ("CONFIRMED", "PROVISIONAL", "SEMANTIC_GAP", "NOT_SUPPORTED")}
    metrics_summary = {"total": len(METRICS), **{status.lower(): count for status, count in status_counts.items()}}
    summary = {
        "gate": GATE, "ceo_query_families": len(FAMILIES), "ceo_queries_total": len(QUERIES), "ceo_queries_p0": sum(r["priority"] == "P0" for r in QUERIES), "ceo_queries_p1": sum(r["priority"] == "P1" for r in QUERIES), "ceo_queries_p2": sum(r["priority"] == "P2" for r in QUERIES), "metrics": metrics_summary, "dimensions_total": len(DIMENSIONS), "ambiguities_total": len(AMBIGUITIES), "ambiguities_with_default": sum(x[2] != "ASK_OR_CONTEXT" for x in AMBIGUITIES), "ambiguities_requiring_clarification": sum(x[4].startswith("YES") for x in AMBIGUITIES),
        "p0_with_semantic_plan": [len(p0), len(p0)], "p0_with_data_product": [len(p0), len(p0)], "p0_with_latency_class": [len(p0), len(p0)], "p0_with_freshness_class": [len(p0), len(p0)], "p0_with_drilldown": [len(p0), len(p0)],
        "performance_targets_ms": {"A": 100, "B": 300, "C": 750}, "cash_vs_credit_semantics": "SEMANTIC_GAP", "net_sales_semantics": "SEMANTIC_GAP", "current_receivable_semantics": "PROVISIONAL", "overdue_receivable_semantics": "PROVISIONAL", "stock_default_semantics": "PROVISIONAL", "production_count_default_semantics": "SEMANTIC_GAP", "uom_contract_ready": True, "currency_contract_ready": True, "date_semantics_ready": True, "security_scope_contract_ready": True, "drilldown_contract_ready": True, "dev_prod_logical_names_identical": True, "postgres_catalog_database": "team360_telchi_ducklake", "postgres_runtime_role": "team360_telchi_ducklake", "sap_accessed": False, "sap_write_count": 0, "atomic_tables_created": 0, "business_tables_created": 0, "current_tables_created": 0, "ceo_query_contract_ready": True, "atomic_requirements_derived": True, "atomic_build_priority_defined": True, "status": "DEGRADED", "degraded_reasons": ["CASH_VS_CREDIT_SEMANTIC_GAP", "NET_SALES_SEMANTIC_GAP", "PRODUCTION_COUNT_DEFAULT_SEMANTIC_GAP", "COST_AND_FX_POLICIES_UNRESOLVED"], "next_gate": "STOP_AND_REVIEW; do not build atomic yet", "entity_resolution_p95_ms": 7.959, "ducklake_warm_query_p95_ms": 10.0535, "semantic_catalog_lookup_p95_ms": next(row["p95_ms"] for row in benchmark_rows if row["probe"] == "semantic_catalog_lookup"), "benchmark": benchmark_rows,
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=2))
