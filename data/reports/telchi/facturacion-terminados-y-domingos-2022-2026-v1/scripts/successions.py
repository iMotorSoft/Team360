"""Detect possible product successions/renames between DROPPED (2022) and NEW (2026) SKUs.

Flag only: no merging, no reclassification. Uses name similarity on the legacy/SAP
descriptions plus size tokens, and reports the amount involved.
"""
import json
import re
import unicodedata

import duckdb

OUT = "/tmp/opencode/telchi-hist"

con = duckdb.connect()
con.execute("SET threads=3")
con.execute("SET memory_limit='3GB'")
con.execute(f"CREATE VIEW cmp AS SELECT * FROM read_parquet('{OUT}/out/products_cmp.parquet')")
con.execute(f"CREATE VIEW cw AS SELECT * FROM read_parquet('{OUT}/out/crosswalk_sap_legacy.parquet')")

rows = con.execute("""
SELECT c.product_key, c.item_code, c.status, c.amount_placeholder
FROM (SELECT product_key, item_code, status, 0.0 amount_placeholder FROM cmp
      WHERE btype='LAB_FINISHED_PRODUCT') c
""").fetchall()
# rebuild with amounts and names
rows = con.execute("""
SELECT c.product_key, c.item_code, c.status, c.amt22, c.amt26, c.legacy_name,
       cw.sap_name
FROM cmp c LEFT JOIN cw ON cw.sap_item_code=c.item_code AND cw.link_status='MAPPED_BY_SAP_U_CODACTIVE'
WHERE c.btype='LAB_FINISHED_PRODUCT'
""").fetchall()

SIZE_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(ml|m\.l\.?|l|lt|lts|litros?|g|gr|grs|kg|cc|oz|un|und|unid|fco|frasco)\b", re.I)
STOP = {"x", "de", "del", "la", "el", "los", "las", "con", "para", "por", "y", "en", "al",
        "frasco", "fco", "bolsa", "caja", "cja", "pote", "sachet", "sobre", "tubo", "lata",
        "botella", "envase", "pack", "unidad", "unidades", "lt", "lts", "ml", "gr", "g", "kg"}


def norm(name):
    if not name:
        return ""
    t = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"[^a-z0-9%. ]+", " ", t)
    tokens = [w for w in t.split() if w and w not in STOP and not re.fullmatch(r"[\d.,]+", w)]
    return " ".join(tokens)


def sizes(text):
    if not text:
        return []
    t = str(text).replace(",", ".").lower()
    mult = {"ml": 1, "m.l.": 1, "m.l": 1, "l": 1000, "lt": 1000, "lts": 1000, "litro": 1000,
            "litros": 1000, "g": 1, "gr": 1, "grs": 1, "kg": 1000, "cc": 1, "oz": 29.5735,
            "un": 1, "und": 1, "unid": 1, "fco": 1, "frasco": 1}
    out = []
    for a, u in SIZE_RE.findall(t):
        out.append(round(float(a) * mult.get(u, 1), 4))
    return sorted(set(out))


def bigrams(s):
    s = s.replace(" ", "")
    return {s[i:i + 2] for i in range(len(s) - 1)} or {s}


def dice(a, b):
    A, B = bigrams(a), bigrams(b)
    if not A or not B:
        return 0.0
    return 2 * len(A & B) / (len(A) + len(B))


dropped = [r for r in rows if r[2] == "DROPPED_2026"]
new = [r for r in rows if r[2] == "NEW_2026"]
print(f"dropped={len(dropped)} new={len(new)}")

pairs = []
for d in dropped:
    dn = norm(d[5] or d[6])
    dsz = sizes(d[5] or d[6])
    for n in new:
        nn = norm(n[5] or n[6])
        score = dice(dn, nn)
        if score < 0.6:
            continue
        nsz = sizes(n[5] or n[6])
        if dsz and nsz and dsz != nsz:
            score -= 0.15          # different presentation weakens the match
            sizeflag = f"{dsz}->{nsz}"
        else:
            sizeflag = "same/none"
        pairs.append({
            "dropped_item": d[1], "dropped_name": d[5] or d[6], "dropped_amt22": float(d[3] or 0),
            "new_item": n[1], "new_name": n[5] or n[6], "new_amt26": float(n[4] or 0),
            "score": round(score, 3), "size": sizeflag,
        })
pairs.sort(key=lambda p: (-p["score"], -p["dropped_amt22"]))
print(f"candidate pairs >=0.60: {len(pairs)}")
for p in pairs[:25]:
    print(f"{p['score']:.2f} {p['dropped_item']} -> {p['new_item']} | {p['dropped_name'][:38]} -> {p['new_name'][:38]} | {p['size']} | {p['dropped_amt22']:,.0f} -> {p['new_amt26']:,.0f}")

# greedy best match per dropped SKU (reporting only)
best = {}
for p in pairs:
    cur = best.get(p["dropped_item"])
    if cur is None or p["score"] > cur["score"]:
        best[p["dropped_item"]] = p
sel = sorted(best.values(), key=lambda p: -p["score"])
matched_amt = sum(p["dropped_amt22"] for p in sel if p["score"] >= 0.75)
total_dropped = sum(float(d[3] or 0) for d in dropped)
summary = {
    "dropped_skus": len(dropped),
    "new_skus": len(new),
    "dropped_amt22": round(total_dropped, 2),
    "new_amt26": round(sum(float(n[4] or 0) for n in new), 2),
    "candidate_successions_075": sum(1 for p in sel if p["score"] >= 0.75),
    "candidate_succession_amt22": round(matched_amt, 2),
}
print("== summary", summary)

json.dump({"summary": summary, "best_matches": sel, "all_pairs": pairs},
          open(f"{OUT}/out/successions.json", "w"), indent=1, ensure_ascii=False)
