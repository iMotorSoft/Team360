"""Read-only extraction of Telchi sales facts into /tmp working parquet.

Sources:
  - Foundation CURRENT (pinned) for 2026 invoices/credit notes.
  - Legacy DS/DS0 Parquet for 2022-2024 (legacy + SAP B1 eras).

No source file is modified. Outputs live under /tmp/opencode/telchi-hist/extract.
"""
import glob
import os

import duckdb

OUT = "/tmp/opencode/telchi-hist/extract"
os.makedirs(OUT, exist_ok=True)

LEGACY = "/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi/raw/legacy/parquet"
DS0 = "/media/issajar/DEVELOP/Projects/telchi/Insiding/DataScience/DS0"


def foundation_extract():
    from modules.telchi.datalake.ducklake import DuckLakeConnector
    from modules.telchi.datalake.foundation_reader import FoundationReader

    connector = DuckLakeConnector()
    with connector.session(read_only=True) as con:
        con.execute("SET threads=3")
        con.execute("SET memory_limit='3GB'")
        access = FoundationReader(connector).resolve_on(con)
        print("FOUNDATION", access.foundation_publication_id, "snapshot", access.ducklake_snapshot_id)
        docs = access.sales("sales_document")
        lines = access.sales("sales_line")
        con.execute(f"""
            COPY (
              SELECT d.doc_date, d.doc_entry, d.doc_num, l.line_num, l.item_code, l.whs_code,
                     l.quantity, l.line_total, l.currency AS line_currency, d.currency AS doc_currency,
                     d.doc_status, d.canceled, l.line_status, d.card_code, d.doc_total,
                     d.sales_channel_code, d.sales_channel_name, d.slp_code
              FROM {lines} l JOIN {docs} d
                ON l.source_system = d.source_system AND l.doc_entry = d.doc_entry
              WHERE d.source_system='SAP_B1_HANA'
            ) TO '{OUT}/foundation_sales_lines.parquet' (FORMAT PARQUET, COMPRESSION ZSTD)
        """)
        cd = access.credit_memo("credit_memo_document")
        cl = access.credit_memo("credit_memo_line")
        con.execute(f"""
            COPY (
              SELECT d.doc_date, d.doc_entry, d.doc_num, l.line_num, l.item_code, l.whs_code,
                     l.quantity, l.line_total, l.currency AS line_currency, d.currency AS doc_currency,
                     d.doc_status, d.canceled, l.line_status, d.card_code, d.doc_total
              FROM {cl} l JOIN {cd} d
                ON l.source_system = d.source_system AND l.doc_entry = d.doc_entry
              WHERE d.source_system='SAP_B1_HANA'
            ) TO '{OUT}/foundation_credit_lines.parquet' (FORMAT PARQUET, COMPRESSION ZSTD)
        """)
        print(con.execute(f"SELECT count(*) FROM '{OUT}/foundation_sales_lines.parquet'").fetchone(),
              con.execute(f"SELECT count(*) FROM '{OUT}/foundation_credit_lines.parquet'").fetchone())


def legacy_extract():
    con = duckdb.connect()
    con.execute("SET threads=3")
    con.execute("SET memory_limit='3GB'")
    # Legacy ERP sales (numeric ProductCode) Jan-Apr 2022
    files = sorted(glob.glob(f"{LEGACY}/saleProduct-*.parq"))
    con.execute(f"""
        COPY (SELECT SaleCode, SaleDate, ProductCode, ProductName, ProductDesc,
                     ProductUnitPriceNet, ProductSaleCant, ProductSalePriceNet, ProductSalePrice,
                     ProductDiscountValue, OfficeCode, OfficeName, Canal, SaleTypeName,
                     SellerCode, SellerName, ClientCode, LineName, Grupo1Name
              FROM read_parquet({files!r})
              WHERE SaleDate >= DATE '2022-01-01' AND SaleDate < DATE '2022-05-01')
        TO '{OUT}/legacy_sales_2022.parquet' (FORMAT PARQUET, COMPRESSION ZSTD)
    """)
    # SAP era sales (ItemCode), 2022-04 .. 2024-06
    files = sorted(f for f in glob.glob(f"{LEGACY}/saleSB1Product-*.parq") if not f.endswith("-h.parq"))
    files += sorted(glob.glob(f"{DS0}/saleSB1Product-2024-06-30.parq"))
    con.execute(f"""
        COPY (SELECT DocEntry, DocNum, DocDate, ItemCode, ItemName, ItemSaleCant,
                     ItemSale, GTotal, SumGTotal, DocTotal, DocStatus, u_estadofc, DocSubType,
                     WhsCode, OfficeName, BaseRef, CardCode, CardName, SellerCodeSB1, Series
              FROM read_parquet({files!r})
              WHERE DocDate >= DATE '2022-04-01' AND DocDate < DATE '2024-07-01')
        TO '{OUT}/sap_sales_2022_2024.parquet' (FORMAT PARQUET, COMPRESSION ZSTD)
    """)
    files = sorted(glob.glob(f"{LEGACY}/ncB1Product-*.parq"))
    files += sorted(glob.glob(f"{DS0}/ncB1Product-2024-06-30.parq"))
    con.execute(f"""
        COPY (SELECT DocEntry, DocNum, DocDate, ItemCode, ItemName, ItemSaleCant,
                     ItemSale, GTotal, SumGTotal, DocTotal, DocStatus, fu_estadofc,
                     WhsCode, OfficeName, BaseRef, CardCode, CardName, SellerCodeSB1
              FROM read_parquet({files!r})
              WHERE DocDate >= DATE '2022-04-01' AND DocDate < DATE '2024-07-01')
        TO '{OUT}/sap_credit_2022_2024.parquet' (FORMAT PARQUET, COMPRESSION ZSTD)
    """)
    for f in ("legacy_sales_2022", "sap_sales_2022_2024", "sap_credit_2022_2024"):
        print(f, con.execute(f"SELECT count(*), min(DocDate) FROM '{OUT}/{f}.parquet'").fetchone() if f != "legacy_sales_2022"
              else con.execute(f"SELECT count(*), min(SaleDate), max(SaleDate) FROM '{OUT}/{f}.parquet'").fetchone())


if __name__ == "__main__":
    foundation_extract()
    legacy_extract()
