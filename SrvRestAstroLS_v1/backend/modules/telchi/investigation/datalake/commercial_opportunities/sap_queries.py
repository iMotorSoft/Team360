"""TELCHI — SAP HANA queries READ ONLY para trazabilidad comercial.

Semántica reutilizada de extractores legacy validados (sql/current/*,
validation/stock, docs/query_catalog.md, proforma_pricing_inventory.md):

  - OQUT/QUT1 = proforma (DocEntry, DocNum). Vinculación a factura vía
    INV1.BaseType=23 AND INV1.BaseEntry=OQUT.DocEntry (89.5% mismo precio
    validado en workspace, docs/proforma_pricing_inventory.md).
  - OINM = movimientos de inventario; OITW.OnHand == SUM(InQty)-SUM(OutQty)
    reconstruct_historical_stock demuestra conservación por ItemCode+Whs.
  - OINV/INV1 = facturas de venta; ODLN/DLN1 = entregas; ORDR/RDR1 = pedidos.
  - OWTR/WTR1 = transferencias entre almacenes (validado en
    warehouse_transfer_traceability_v1_report.md).
  - Retail One: @SO1_01FACTURA (join OINV.U_SO1_01FOLIORETAIL1 = Name, 1:1).
  - canales: OINV.U_ORIGIN ('SAP','DMS','R1'), U_SO1_01RETAILONE.
TODAS las funciones son READ ONLY sobre HANA.
"""
from __future__ import annotations

from datetime import date

from modules.telchi.investigation.atomic.connection import connect

SCHEMA = "TELCHI"


def _quote(s: str) -> str:
    return s.replace("'", "''")


def get_item(item_code: str) -> dict | None:
    with _conn() as (conn, cur):
        cur.execute(
            f'SELECT "ItemCode","ItemName","ItmsGrpCod","InvntryUom" FROM "{SCHEMA}"."OITM" WHERE "ItemCode"=?',
            (item_code,),
        )
        row = cur.fetchone()
        return dict(zip([d[0] for d in cur.description], row)) if row else None


def get_warehouse_role_map() -> dict[str, str]:
    """OWHS: WhsCode -> (WhsName, U_TIPO/U_TYPE) básico para rol de almacén."""
    with _conn() as (conn, cur):
        cur.execute(f'SELECT "WhsCode","WhsName","U_TIPO","U_TYPE" FROM "{SCHEMA}"."OWHS"')
        return {r[0]: {"name": r[1], "tipo": r[2], "type": r[3]} for r in cur.fetchall()}


def get_quotations_for_item(item_codes: list[str], start: date | None = None, end: date | None = None) -> list[dict]:
    """Proformas (OQUT/QUT1) para items dados, ventana opcional."""
    if not item_codes:
        return []
    item_list = ",".join(f"'{_quote(c)}'" for c in item_codes)
    where = f'l."ItemCode" IN ({item_list})'
    params: list = []
    if start:
        where += ' AND q."DocDate" >= ?'
        params.append(start)
    if end:
        where += ' AND q."DocDate" <= ?'
        params.append(end)
    sql = f"""
        SELECT q."DocEntry", q."DocNum", q."DocDate", q."CardCode", q."CardName",
               q."SlpCode", q."DocTotal", q."DocStatus", q."CANCELED",
               l."LineNum", l."ItemCode", l."Dscription", l."Quantity", l."Price",
               l."LineTotal", l."WhsCode", l."BaseType", l."BaseEntry"
        FROM "{SCHEMA}"."OQUT" q
        JOIN "{SCHEMA}"."QUT1" l ON l."DocEntry" = q."DocEntry"
        WHERE {where}
        ORDER BY q."DocDate", q."DocNum", l."LineNum"
    """
    with _conn() as (conn, cur):
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def get_invoices_for_item(item_codes: list[str], start: date | None = None, end: date | None = None, customers: list[str] | None = None) -> list[dict]:
    """Facturas OINV/INV1 para items, ventana y clientes opcionales."""
    if not item_codes:
        return []
    item_list = ",".join(f"'{_quote(c)}'" for c in item_codes)
    where = f'i."ItemCode" IN ({item_list})'
    params: list = []
    if start:
        where += ' AND h."DocDate" >= ?'
        params.append(start)
    if end:
        where += ' AND h."DocDate" <= ?'
        params.append(end)
    if customers:
        cust_list = ",".join(f"'{_quote(c)}'" for c in customers)
        where += f' AND h."CardCode" IN ({cust_list})'
    sql = f"""
        SELECT h."DocEntry", h."DocNum", h."DocDate", h."CardCode", h."CardName",
               h."SlpCode", h."U_ORIGIN", h."U_SO1_01RETAILONE", h."U_SO1_01FOLIORETAIL1",
               i."LineNum", i."ItemCode", i."Dscription", i."Quantity", i."Price",
               i."LineTotal", i."WhsCode", i."BaseType", i."BaseEntry", i."BaseLine", i."BaseRef"
        FROM "{SCHEMA}"."OINV" h
        JOIN "{SCHEMA}"."INV1" i ON i."DocEntry" = h."DocEntry"
        WHERE {where}
        ORDER BY h."DocDate", h."DocNum", i."LineNum"
    """
    with _conn() as (conn, cur):
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def get_deliveries_for_item(item_codes: list[str], start: date | None = None, end: date | None = None) -> list[dict]:
    if not item_codes:
        return []
    item_list = ",".join(f"'{_quote(c)}'" for c in item_codes)
    where = f'i."ItemCode" IN ({item_list})'
    params: list = []
    if start:
        where += ' AND h."DocDate" >= ?'
        params.append(start)
    if end:
        where += ' AND h."DocDate" <= ?'
        params.append(end)
    sql = f"""
        SELECT h."DocEntry", h."DocNum", h."DocDate", h."CardCode", h."CardName",
               h."SlpCode", i."LineNum", i."ItemCode", i."Quantity", i."Price",
               i."LineTotal", i."WhsCode", i."BaseType", i."BaseEntry", i."BaseLine"
        FROM "{SCHEMA}"."ODLN" h
        JOIN "{SCHEMA}"."DLN1" i ON i."DocEntry" = h."DocEntry"
        WHERE {where}
        ORDER BY h."DocDate", h."DocNum", i."LineNum"
    """
    with _conn() as (conn, cur):
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def get_transfers_for_item(item_codes: list[str], start: date | None = None, end: date | None = None) -> list[dict]:
    """Transferencias OWTR/WTR1 entre almacenes (semántica validada legacy)."""
    if not item_codes:
        return []
    item_list = ",".join(f"'{_quote(c)}'" for c in item_codes)
    where = f'l."ItemCode" IN ({item_list})'
    params: list = []
    if start:
        where += ' AND w."DocDate" >= ?'
        params.append(start)
    if end:
        where += ' AND w."DocDate" <= ?'
        params.append(end)
    sql = f"""
        SELECT w."DocEntry", w."DocNum", w."DocDate", w."DocStatus", w."CANCELED",
               l."LineNum", l."ItemCode", l."Quantity", l."FromWhsCod", l."WhsCode", l."SlpCode"
        FROM "{SCHEMA}"."OWTR" w
        JOIN "{SCHEMA}"."WTR1" l ON l."DocEntry" = w."DocEntry"
        WHERE {where}
        ORDER BY w."DocDate", w."DocNum", l."LineNum"
    """
    with _conn() as (conn, cur):
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def get_movements(item_codes: list[str], start: date | None = None, end: date | None = None) -> list[dict]:
    """OINM movimientos (grain TransNum, ItemCode, Warehouse) ventana opcional."""
    if not item_codes:
        return []
    item_list = ",".join(f"'{_quote(c)}'" for c in item_codes)
    where = f'"ItemCode" IN ({item_list})'
    params: list = []
    if start:
        where += ' AND "DocDate" >= ?'
        params.append(start)
    if end:
        where += ' AND "DocDate" <= ?'
        params.append(end)
    sql = f"""
        SELECT "TransNum","TransType","BASE_REF","DocLineNum","DocDate","ItemCode",
               "Dscription","InQty","OutQty","Warehouse","CardCode","SlpCode",
               "Balance","Ref1","Ref2","UserSign"
        FROM "{SCHEMA}"."OINM"
        WHERE {where}
        ORDER BY "DocDate","TransNum"
    """
    with _conn() as (conn, cur):
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def get_stock_now(item_codes: list[str]) -> list[dict]:
    if not item_codes:
        return []
    item_list = ",".join(f"'{_quote(c)}'" for c in item_codes)
    sql = f"""
        SELECT "ItemCode","WhsCode","OnHand","IsCommited","OnOrder"
        FROM "{SCHEMA}"."OITW" WHERE "ItemCode" IN ({item_list}) ORDER BY "ItemCode","WhsCode"
    """
    with _conn() as (conn, cur):
        cur.execute(sql)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def get_customer_sales(customer_codes: list[str], start: date | None = None, end: date | None = None, item_codes: list[str] | None = None) -> list[dict]:
    """Ventas a clientes (por CardCode o CardName LIKE) en ventana, opcional item."""
    if not customer_codes:
        return []
    params: list = []
    conds = []
    for c in customer_codes:
        conds.append('UPPER("CardName") LIKE ?')
        params.append(f"%{c.upper()}%")
    where = "(" + " OR ".join(conds) + ")"
    if start:
        where += ' AND h."DocDate" >= ?'
        params.append(start)
    if end:
        where += ' AND h."DocDate" <= ?'
        params.append(end)
    sql = f"""
        SELECT h."DocEntry", h."DocNum", h."DocDate", h."CardCode", h."CardName", h."SlpCode",
               h."U_ORIGIN", h."U_SO1_01RETAILONE", i."LineNum", i."ItemCode",
               i."Quantity", i."Price", i."LineTotal", i."WhsCode"
        FROM "{SCHEMA}"."OINV" h JOIN "{SCHEMA}"."INV1" i ON i."DocEntry"=h."DocEntry"
        WHERE {where}
        ORDER BY h."DocDate", h."DocNum"
    """
    if item_codes:
        item_list = ",".join(f"'{_quote(c)}'" for c in item_codes)
        # NOTE: item filter can't be injected into WHERE built above with ORs
        # without parens; do it in python instead (small universes).
    with _conn() as (conn, cur):
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    if item_codes:
        rows = [r for r in rows if r["ItemCode"] in item_codes]
    return rows


def get_retail_one_invoices(customer_name_like: str | None = None, folio: str | None = None, start: date | None = None, end: date | None = None) -> list[dict]:
    """Retail One: @SO1_01FACTURA — ventas POS/Sucursales (canal R1)."""
    where: list[str] = []
    params: list = []
    if customer_name_like:
        where.append('UPPER("U_SO1_NOMBRE") LIKE ?')
        params.append(f"%{customer_name_like.upper()}%")
    if folio:
        where.append('"U_SO1_FOLIOFACTURA" = ?')
        params.append(folio)
    if start:
        where.append('"U_SO1_FECHA" >= ?')
        params.append(start)
    if end:
        where.append('"U_SO1_FECHA" <= ?')
        params.append(end)
    wsql = (" WHERE " + " AND ".join(where)) if where else ""
    sql = f"""
        SELECT "Code","U_SO1_FOLIOFACTURA","U_SO1_FECHA","U_SO1_NOMBRE","U_SO1_CODIGOCLIENTE",
               "U_SO1_REFERENCIA","U_SO1_STATUS"
        FROM "{SCHEMA}"."@SO1_01FACTURA" {wsql}
        ORDER BY "U_SO1_FECHA" LIMIT 2000
    """
    with _conn() as (conn, cur):
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


class _conn:
    def __enter__(self):
        self.conn, self.cur = connect()
        return self.conn, self.cur

    def __exit__(self, *exc):
        self.cur.close()
        self.conn.close()
        return False