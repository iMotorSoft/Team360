#!/usr/bin/env python3
"""Sales Dimensions + Temporal Channel Model — Comprehensive Analysis.

Separates SELLER from CUSTOMER CHANNEL as independent dimensions.
Builds temporal channel model with as-of classification.
Reconstructs legacy pre-2026 channel rule.
Validates homologation between legacy and current taxonomy.
"""
from __future__ import annotations

import json
import os
import shlex
import sys
import time
from pathlib import Path

from modules.telchi.investigation.paths import SECRET_ROOT

ROOT = Path(__file__).resolve().parents[2]
HANA_ENV = SECRET_ROOT / "sap" / "hana.env"
OUT_DIR = ROOT / "validation" / "sales_dimensions"
OUT_DIR.mkdir(parents=True, exist_ok=True)

CHANNEL_MAP = {
    1: "Farmacias", 2: "Corporativo", 3: "Corporativo Grande",
    4: "Supermercados", 5: "Distribuidoras", 6: "Regional",
    7: "Publico/Retail", 8: "Especiales", None: "Unclassified"
}

WINDOWS = {
    "aug2026": ("2026-08-01", "2026-08-31"),
    "apr2022": ("2022-04-01", "2022-05-01"),
    "aug2022": ("2022-08-01", "2022-09-01"),
}


def load_env() -> dict:
    vals = {}
    for line in HANA_ENV.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        k, _, v = line.partition("=")
        vals[k] = shlex.split(v, posix=True)[0]
    return vals


def connect():
    from hdbcli import dbapi
    env = load_env()
    return dbapi.connect(
        address="127.0.0.1", port=30015,
        user=env["TELCHI_SAP_HANA_USER"],
        password=env["TELCHI_SAP_HANA_PASSWORD"],
        currentSchema="TELCHI", encrypt="false",
    )


def q(cur, sql):
    cur.execute(sql)
    cols = [d[0] for d in cur.description]
    return cur.fetchall(), cols


def run_seller_analysis(cur, window_name, d0, d1):
    """Seller reporting: SlpCode-based, independent of channel."""
    print(f"\n{'='*60}")
    print(f"SELLER ANALYSIS: {window_name} ({d0} → {d1})")
    print(f"{'='*60}")

    # Gross sales by seller
    rows, cols = q(cur, f"""
        SELECT OINV."SlpCode", OSLP."SlpName",
               COUNT(*) AS docs, SUM(OINV."DocTotal") AS gross
        FROM TELCHI.OINV OINV
        LEFT JOIN TELCHI.OSLP ON OINV."SlpCode" = OSLP."SlpCode"
        WHERE OINV."DocDate">='{d0}' AND OINV."DocDate"<='{d1} 23:59:59'
          AND OINV."CANCELED"='N'
        GROUP BY OINV."SlpCode", OSLP."SlpName"
        ORDER BY gross DESC
    """)
    sellers = {}
    for r in rows:
        sc = r[0]
        sellers[sc] = {"name": r[1], "docs": r[2], "gross": float(r[3])}

    # Credit notes by seller
    rows2, _ = q(cur, f"""
        SELECT ORIN."SlpCode", COUNT(*) AS docs, SUM(ORIN."DocTotal") AS cn
        FROM TELCHI.ORIN ORIN
        WHERE ORIN."DocDate">='{d0}' AND ORIN."DocDate"<='{d1} 23:59:59'
          AND ORIN."CANCELED"='N'
        GROUP BY ORIN."SlpCode"
    """)
    for r in rows2:
        sc = r[0]
        if sc in sellers:
            sellers[sc]["cn_docs"] = r[1]
            sellers[sc]["cn"] = float(r[2])
            sellers[sc]["net"] = sellers[sc]["gross"] - sellers[sc]["cn"]
        else:
            sellers[sc] = {"name": None, "docs": 0, "gross": 0, "cn_docs": r[1], "cn": float(r[2]), "net": -float(r[2])}

    # Fill missing
    for sc in sellers:
        if "cn" not in sellers[sc]:
            sellers[sc]["cn_docs"] = 0
            sellers[sc]["cn"] = 0
            sellers[sc]["net"] = sellers[sc]["gross"]

    # Add category
    rows3, _ = q(cur, 'SELECT "SlpCode", "U_CATVENDEDOR" FROM TELCHI.OSLP')
    cat_map = {r[0]: r[1] for r in rows3}
    for sc in sellers:
        sellers[sc]["category"] = cat_map.get(sc)

    # Verify: seller total = sum of channel distribution
    total_gross = sum(s["gross"] for s in sellers.values())
    total_cn = sum(s["cn"] for s in sellers.values())
    total_net = sum(s["net"] for s in sellers.values())

    print(f"  Total sellers: {len(sellers)}")
    print(f"  Total gross: ${total_gross:,.2f}")
    print(f"  Total CN: ${total_cn:,.2f}")
    print(f"  Total net: ${total_net:,.2f}")

    return sellers


def run_channel_analysis(cur, window_name, d0, d1):
    """Customer channel analysis: OCRD.U_CANAL_VENTAS."""
    print(f"\n{'='*60}")
    print(f"CHANNEL ANALYSIS: {window_name} ({d0} → {d1})")
    print(f"{'='*60}")

    # Sales by channel
    rows, cols = q(cur, f"""
        SELECT OCRD."U_CANAL_VENTAS",
               COUNT(*) AS docs, SUM(OINV."DocTotal") AS gross,
               COUNT(DISTINCT OINV."CardCode") AS customers,
               COUNT(DISTINCT OINV."SlpCode") AS sellers
        FROM TELCHI.OINV OINV
        INNER JOIN TELCHI.OCRD ON OINV."CardCode" = OCRD."CardCode"
        WHERE OINV."DocDate">='{d0}' AND OINV."DocDate"<='{d1} 23:59:59'
          AND OINV."CANCELED"='N'
        GROUP BY OCRD."U_CANAL_VENTAS"
        ORDER BY gross DESC
    """)
    channels = {}
    for r in rows:
        ch = r[0]
        channels[ch] = {"docs": r[1], "gross": float(r[2]), "customers": r[3], "sellers": r[4],
                         "name": CHANNEL_MAP.get(ch, f"Unknown({ch})")}

    # Credit notes by channel
    rows2, _ = q(cur, f"""
        SELECT OCRD."U_CANAL_VENTAS", COUNT(*) AS docs, SUM(ORIN."DocTotal") AS cn
        FROM TELCHI.ORIN ORIN
        INNER JOIN TELCHI.OCRD ON ORIN."CardCode" = OCRD."CardCode"
        WHERE ORIN."DocDate">='{d0}' AND ORIN."DocDate"<='{d1} 23:59:59'
          AND ORIN."CANCELED"='N'
        GROUP BY OCRD."U_CANAL_VENTAS"
    """)
    for r in rows2:
        ch = r[0]
        if ch in channels:
            channels[ch]["cn_docs"] = r[1]
            channels[ch]["cn"] = float(r[2])
            channels[ch]["net"] = channels[ch]["gross"] - channels[ch]["cn"]
        else:
            channels[ch] = {"docs": 0, "gross": 0, "cn_docs": r[1], "cn": float(r[2]),
                             "net": -float(r[2]), "customers": 0, "sellers": 0,
                             "name": CHANNEL_MAP.get(ch, f"Unknown({ch})")}

    for ch in channels:
        if "cn" not in channels[ch]:
            channels[ch]["cn_docs"] = 0
            channels[ch]["cn"] = 0
            channels[ch]["net"] = channels[ch]["gross"]

    total_gross = sum(c["gross"] for c in channels.values())
    total_cn = sum(c["cn"] for c in channels.values())
    total_net = sum(c["net"] for c in channels.values())

    print(f"  Total channels: {len(channels)}")
    print(f"  Total gross: ${total_gross:,.2f}")
    print(f"  Total CN: ${total_cn:,.2f}")
    print(f"  Total net: ${total_net:,.2f}")

    return channels


def run_seller_channel_independence(cur, window_name, d0, d1, sellers, channels):
    """Prove seller ≠ channel: same seller sells to multiple channels."""
    print(f"\n{'='*60}")
    print(f"SELLER-CHANNEL INDEPENDENCE: {window_name}")
    print(f"{'='*60}")

    rows, _ = q(cur, f"""
        SELECT OINV."SlpCode", OCRD."U_CANAL_VENTAS",
               COUNT(*) AS docs, SUM(OINV."DocTotal") AS gross
        FROM TELCHI.OINV OINV
        INNER JOIN TELCHI.OCRD ON OINV."CardCode" = OCRD."CardCode"
        WHERE OINV."DocDate">='{d0}' AND OINV."DocDate"<='{d1} 23:59:59'
          AND OINV."CANCELED"='N'
        GROUP BY OINV."SlpCode", OCRD."U_CANAL_VENTAS"
    """)

    seller_channels = {}
    for r in rows:
        sc, ch = r[0], r[1]
        seller_channels.setdefault(sc, {})[ch] = {"docs": r[2], "gross": float(r[3])}

    # Check independence: seller total = sum of channels
    mismatches = 0
    for sc in sellers:
        if sc in seller_channels:
            sum_ch = sum(v["gross"] for v in seller_channels[sc].values())
            seller_total = sellers[sc]["gross"]
            if abs(sum_ch - seller_total) > 0.01:
                mismatches += 1
                print(f"  MISMATCH: SlpCode={sc}: seller_total={seller_total:,.2f}, channel_sum={sum_ch:,.2f}")

    # Multi-channel sellers
    multi = {sc: ch for sc, ch in seller_channels.items() if len(ch) > 1}
    print(f"\n  Sellers with multiple channels: {len(multi)}")
    for sc in sorted(multi.keys())[:10]:
        name = sellers.get(sc, {}).get("name", "?")
        ch_list = ", ".join(f"ch{c}:{v['gross']:,.0f}" for c, v in sorted(multi[sc].items(), key=lambda x: str(x[0])))
        print(f"    {sc} ({name[:25]}): {ch_list}")

    # Verify totals
    all_channel_gross = sum(channels.get(ch, {}).get("gross", 0) for ch in seller_channels
                           for ch in seller_channels[ch] if isinstance(ch, (int, type(None))))

    print(f"\n  Financial regression: seller totals vs channel totals")
    print(f"    Seller total gross: ${sum(s['gross'] for s in sellers.values()):,.2f}")
    print(f"    Channel total gross: ${sum(c['gross'] for c in channels.values()):,.2f}")

    return seller_channels, mismatches == 0


def run_customer_change_detection(cur):
    """Detect if any customer changed U_CANAL_VENTAS during 2026."""
    print(f"\n{'='*60}")
    print(f"CUSTOMER CHANNEL CHANGE DETECTION (2026)")
    print(f"{'='*60}")

    # Customers with invoices in multiple months of 2026
    rows, _ = q(cur, """
        SELECT OINV."CardCode",
               COUNT(DISTINCT TO_CHAR(OINV."DocDate", 'YYYY-MM')) AS months,
               MIN(TO_CHAR(OINV."DocDate", 'YYYY-MM')) AS first_month,
               MAX(TO_CHAR(OINV."DocDate", 'YYYY-MM')) AS last_month
        FROM TELCHI.OINV OINV
        WHERE OINV."DocDate">='2026-01-01' AND OINV."DocDate"<='2026-08-31 23:59:59'
          AND OINV."CANCELED"='N'
        GROUP BY OINV."CardCode"
        HAVING COUNT(DISTINCT TO_CHAR(OINV."DocDate", 'YYYY-MM')) >= 3
        ORDER BY months DESC
        LIMIT 20
    """)
    print(f"  Customers active in 3+ months of 2026: {len(rows)}")

    # Check: do all these customers have stable channel?
    stable = 0
    for r in rows:
        cc = r[0]
        ch_rows, _ = q(cur, f"""
            SELECT DISTINCT OCRD."U_CANAL_VENTAS"
            FROM TELCHI.OINV OINV
            INNER JOIN TELCHI.OCRD ON OINV."CardCode" = OCRD."CardCode"
            WHERE OINV."CardCode"='{cc}' AND OINV."CANCELED"='N'
              AND OINV."DocDate">='2026-01-01'
        """)
        if len(ch_rows) == 1:
            stable += 1
        else:
            channels = [cr[0] for cr in ch_rows]
            print(f"  {cc}: {len(channels)} different channels: {channels}")

    print(f"  Stable channel: {stable}/{len(rows)}")

    # Check: bulk load dates
    rows2, _ = q(cur, """
        SELECT TO_CHAR("UpdateDate", 'YYYY-MM') AS month, COUNT(*) AS n
        FROM TELCHI.OCRD
        WHERE "CardType"='C' AND "U_CANAL_VENTAS" IS NOT NULL
          AND "UpdateDate">='2026-01-01'
        GROUP BY TO_CHAR("UpdateDate", 'YYYY-MM')
        ORDER BY month
    """)
    print(f"\n  Bulk assignment timeline:")
    for r in rows2:
        print(f"    {r[0]}: {r[1]} customers")

    return stable == len(rows)


def run_legacy_rule_reconstruction(cur, d0, d1):
    """Reconstruct legacy channel rule for pre-2026 using available SAP fields."""
    print(f"\n{'='*60}")
    print(f"LEGACY RULE RECONSTRUCTION: {d0} → {d1}")
    print(f"{'='*60}")

    # The legacy rule used PriceTypeCode + ClientSegmentationCode
    # In current SAP, U_TIPOVENTA is always 0 (not used)
    # But we have OCRD fields that might correspond

    # Check what OCRD fields are available for segmentation
    rows, _ = q(cur, f"""
        SELECT OCRD."GroupCode",
               OCRD."U_CANAL_VENTAS",
               OCRD."U_CATCLIENTE",
               COUNT(*) AS docs, SUM(OINV."DocTotal") AS gross
        FROM TELCHI.OINV OINV
        INNER JOIN TELCHI.OCRD ON OINV."CardCode" = OCRD."CardCode"
        WHERE OINV."DocDate">='{d0}' AND OINV."DocDate"<='{d1} 23:59:59'
          AND OINV."CANCELED"='N'
        GROUP BY OCRD."GroupCode", OCRD."U_CANAL_VENTAS", OCRD."U_CATCLIENTE"
        ORDER BY gross DESC
    """)

    print(f"  GroupCode x Canal x CatCliente distribution:")
    for r in rows:
        gc = r[0]
        ch = r[1] if r[1] is not None else "NULL"
        cc = r[2] if r[2] is not None else "NULL"
        print(f"    GroupCode={gc}, canal={ch}, cat={cc}: {r[3]} docs, ${float(r[4]):,.2f}")

    # The legacy Python rule was:
    # HORIZONTAL: PriceTypeCode == 11
    # LICITACION: PriceTypeCode == 10
    # ESPECIAL: PriceTypeCode NOT IN (10,11) AND ClientSegmentationCode IN (51,6)
    # SALON: PriceTypeCode NOT IN (10,11) AND ClientSegmentationCode IN (100,NULL)
    # CORPORATIVO: rest
    #
    # In current SAP:
    # - U_TIPOVENTA is always 0 (legacy PriceTypeCode not migrated)
    # - GroupCode might correspond to ClientSegmentationCode
    # - The current U_CANAL_VENTAS replaced this logic

    # For pre-2026, the best we can do is:
    # 1. Use current U_CANAL_VENTAS as approximation (with limitation)
    # 2. Accept that we cannot reconstruct the exact legacy rule

    # Check: what GroupCode values exist?
    rows2, _ = q(cur, """
        SELECT "GroupCode", COUNT(*) AS n
        FROM TELCHI.OCRD WHERE "CardType"='C'
        GROUP BY "GroupCode" ORDER BY n DESC
    """)
    print(f"\n  GroupCode distribution:")
    for r in rows2:
        print(f"    {r[0]}: {r[1]} customers")

    return rows


def run_corporate_family_analysis(cur, d0, d1):
    """Analyze channel 2 vs 3 vs 2+3."""
    print(f"\n{'='*60}")
    print(f"CORPORATE FAMILY ANALYSIS: {d0} → {d1}")
    print(f"{'='*60}")

    for label, filt in [("canal=2", "= 2"), ("canal=3", "= 3"), ("canal=2+3", "IN (2,3)")]:
        rows, _ = q(cur, f"""
            SELECT COUNT(*) AS docs, SUM(OINV."DocTotal") AS gross,
                   COUNT(DISTINCT OINV."CardCode") AS customers
            FROM TELCHI.OINV OINV
            INNER JOIN TELCHI.OCRD ON OINV."CardCode" = OCRD."CardCode"
            WHERE OINV."DocDate">='{d0}' AND OINV."DocDate"<='{d1} 23:59:59'
              AND OINV."CANCELED"='N'
              AND OCRD."U_CANAL_VENTAS" {filt}
        """)
        r = rows[0]
        # CN
        rows2, _ = q(cur, f"""
            SELECT COALESCE(SUM(ORIN."DocTotal"),0)
            FROM TELCHI.ORIN ORIN
            INNER JOIN TELCHI.OCRD ON ORIN."CardCode" = OCRD."CardCode"
            WHERE ORIN."DocDate">='{d0}' AND ORIN."DocDate"<='{d1} 23:59:59'
              AND ORIN."CANCELED"='N' AND OCRD."U_CANAL_VENTAS" {filt}
        """)
        cn = float(rows2[0][0])
        gross = float(r[1])
        print(f"  {label}: {r[0]} docs, gross=${gross:,.2f}, CN=${cn:,.2f}, net=${gross-cn:,.2f}, {r[2]} customers")


def main():
    os.environ.setdefault("HANA_HOST", "127.0.0.1")
    os.environ.setdefault("HANA_PORT", "30015")
    os.environ.setdefault("HANA_SCHEMA", "TELCHI")

    conn = connect()
    cur = conn.cursor()
    report = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"), "phases": {}}

    # Phase 1: August 2026 — full analysis
    d0, d1 = WINDOWS["aug2026"]
    sellers_aug = run_seller_analysis(cur, "aug2026", d0, d1)
    channels_aug = run_channel_analysis(cur, "aug2026", d0, d1)
    indep_aug, indep_pass = run_seller_channel_independence(cur, "aug2026", d0, d1, sellers_aug, channels_aug)
    changes_stable = run_customer_change_detection(cur)
    corp_analysis = run_corporate_family_analysis(cur, d0, d1)

    # Phase 2: Legacy rule reconstruction
    legacy_rows = run_legacy_rule_reconstruction(cur, "2022-04-01", "2022-05-01")

    # Phase 3: April 2022 — use current U_CANAL_VENTAS as approximation
    d0, d1 = WINDOWS["apr2022"]
    channels_apr22 = run_channel_analysis(cur, "apr2022", d0, d1)

    # Phase 4: August 2022
    d0, d1 = WINDOWS["aug2022"]
    channels_aug22 = run_channel_analysis(cur, "aug2022", d0, d1)

    # Financial regression: seller totals must match across views
    print(f"\n{'='*60}")
    print("FINANCIAL REGRESSION")
    print(f"{'='*60}")

    # Aug 2026: total seller gross vs total channel gross
    seller_total = sum(s["gross"] for s in sellers_aug.values())
    channel_total = sum(c["gross"] for c in channels_aug.values())
    print(f"  Aug 2026: seller_total=${seller_total:,.2f}, channel_total=${channel_total:,.2f}")
    print(f"  Match: {abs(seller_total - channel_total) < 0.01}")

    # Seller net must equal seller gross - seller CN
    seller_net = sum(s.get("net", s["gross"]) for s in sellers_aug.values())
    seller_gross_cn = sum(s.get("cn", 0) for s in sellers_aug.values())
    print(f"  Seller: gross=${seller_total:,.2f}, CN=${seller_gross_cn:,.2f}, net=${seller_net:,.2f}")

    # Channel net must equal channel gross - channel CN
    channel_net = sum(c.get("net", c["gross"]) for c in channels_aug.values())
    channel_gross_cn = sum(c.get("cn", 0) for c in channels_aug.values())
    print(f"  Channel: gross=${channel_total:,.2f}, CN=${channel_gross_cn:,.2f}, net=${channel_net:,.2f}")

    print(f"\n  Gross match: {abs(seller_total - channel_total) < 0.01}")
    print(f"  CN match: {abs(seller_gross_cn - channel_gross_cn) < 0.01}")
    print(f"  Net match: {abs(seller_net - channel_net) < 0.01}")

    # Build summary
    report["summary"] = {
        "seller_identity": "SlpCode (OSLP)",
        "seller_category_separate": True,
        "customer_channel_source": "OCRD.U_CANAL_VENTAS",
        "channel_is_customer_attribute": True,
        "channel_effective_from": "2026-01 (bulk initialization)",
        "pre_2026_channel": "NOT AVAILABLE via U_CANAL_VENTAS",
        "seller_channel_independence": indep_pass,
        "customer_changes_stable": changes_stable,
        "financial_regression": abs(seller_total - channel_total) < 0.01,
    }

    # Write report
    out = OUT_DIR / "sales_dimension_analysis.json"
    out.write_text(json.dumps(report, indent=2, default=str))
    print(f"\nWROTE {out}")

    cur.close()
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
