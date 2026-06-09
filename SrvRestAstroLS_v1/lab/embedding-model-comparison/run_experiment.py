#!/usr/bin/env python3
"""Compare embedding models for Team360 knowledge retrieval.

Usage:
  python lab/embedding-model-comparison/run_experiment.py --mock
  python lab/embedding-model-comparison/run_experiment.py --models openai
  python lab/embedding-model-comparison/run_experiment.py

Environment variables:
  OPENAI_API_KEY
  OPENROUTER_API_KEY
  PERPLEXITY_API_KEY
"""

import argparse
import json
import math
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

EXPERIMENT_DIR = Path(__file__).parent
GOLDEN_FILE = EXPERIMENT_DIR / "golden_answers" / "embedding_retrieval_cases.json"
RESULTS_DIR = EXPERIMENT_DIR / "results"

CANDIDATE_MODELS = [
    {
        "provider": "openai",
        "model": "text-embedding-3-small",
        "requested_dimensions": 1536,
        "env_key": "OPENAI_API_KEY",
        "url": "https://api.openai.com/v1/embeddings",
        "supports_dimensions_param": True,
    },
    {
        "provider": "openrouter",
        "model": "qwen/qwen3-embedding-8b",
        "requested_dimensions": 1536,
        "env_key": "OPENROUTER_API_KEY",
        "url": "https://openrouter.ai/api/v1/embeddings",
        "supports_dimensions_param": True,
    },
    {
        "provider": "perplexity",
        "model": "pplx-embed-v1-0.6b",
        "requested_dimensions": None,
        "env_key": "PERPLEXITY_API_KEY",
        "url": "https://api.perplexity.ai/embeddings",
        "supports_dimensions_param": False,
    },
]

MOCK_DIMENSIONS = 1536


def cosine_similarity(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _mock_deterministic_embedding(texts, seed_offset=0):
    import hashlib
    result = []
    for i, text in enumerate(texts):
        h = hashlib.sha256(f"{seed_offset}:{i}:{text}".encode()).hexdigest()
        vec = [(int(h[j:j+2], 16) / 255.0 - 0.5) * 2 for j in range(0, min(128, len(h)), 2)]
        vec = vec * (MOCK_DIMENSIONS // len(vec)) + vec[:MOCK_DIMENSIONS % len(vec)]
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            vec = [x / norm for x in vec]
        result.append(vec)
    return result


def _call_embedding_api(url, api_key, model, texts, dimensions=None):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {"input": texts, "model": model}
    if dimensions is not None:
        body["dimensions"] = dimensions

    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        err_body = e.read().decode(errors="replace")[:500]
        return {"error": f"HTTP {e.code}: {err_body}"}
    except urllib.error.URLError as e:
        return {"error": f"URL error: {e.reason}"}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def _detect_encoding_format(response, embeddings):
    if not embeddings:
        return "unknown"
    if "encoding_format" in response:
        return response["encoding_format"]
    sample = embeddings[0]
    if isinstance(sample, list):
        if all(isinstance(x, float) for x in sample):
            return "float"
        if all(isinstance(x, int) for x in sample):
            return "int8"
        return "unknown"
    if isinstance(sample, str):
        return "base64"
    return "unknown"


def run_model(model_config, dataset, mock_mode):
    provider = model_config["provider"]
    model = model_config["model"]
    requested_dim = model_config["requested_dimensions"]
    env_key = model_config["env_key"]
    supports_dims = model_config["supports_dimensions_param"]

    api_key = os.environ.get(env_key, "")

    result = {
        "provider": provider,
        "model": model,
        "requested_dimensions": requested_dim,
        "actual_dimensions": None,
        "encoding_format": "unknown",
        "api_compatible": True,
        "error": None,
        "skipped": False,
        "latency_ms": {},
        "retrieval": {},
        "top1_hits": 0,
        "top3_hits": 0,
        "top5_hits": 0,
        "total_queries": len(dataset["queries"]),
    }

    if not api_key and not mock_mode:
        result["error"] = f"No API key found in env var {env_key}"
        result["api_compatible"] = False
        result["skipped"] = True
        return result

    chunks = dataset["chunks"]
    queries = dataset["queries"]
    chunk_texts = [c["content"] for c in chunks]
    query_texts = [q["query"] for q in queries]

    if mock_mode:
        chunk_embeddings = _mock_deterministic_embedding(chunk_texts, seed_offset=0)
        query_embeddings = _mock_deterministic_embedding(query_texts, seed_offset=1000)
        result["actual_dimensions"] = MOCK_DIMENSIONS
        result["encoding_format"] = "float"
        result["latency_ms"]["batch_chunks"] = 0
        result["latency_ms"]["batch_queries"] = 0
    else:
        dims = requested_dim if supports_dims else None
        t0 = time.time()
        response = _call_embedding_api(
            model_config["url"], api_key, model, chunk_texts, dimensions=dims
        )
        t1 = time.time()
        result["latency_ms"]["batch_chunks"] = round((t1 - t0) * 1000, 2)

        if "error" in response:
            result["error"] = response["error"]
            result["api_compatible"] = False
            return result

        if "data" not in response:
            result["error"] = f"Unexpected response (no 'data' key): {json.dumps(response)[:300]}"
            result["api_compatible"] = False
            return result

        chunk_embeddings = [item["embedding"] for item in response["data"]]
        result["actual_dimensions"] = len(chunk_embeddings[0]) if chunk_embeddings else None
        result["encoding_format"] = _detect_encoding_format(response, chunk_embeddings)

        t0 = time.time()
        response_q = _call_embedding_api(
            model_config["url"], api_key, model, query_texts, dimensions=dims
        )
        t1 = time.time()
        result["latency_ms"]["batch_queries"] = round((t1 - t0) * 1000, 2)

        if "data" not in response_q:
            err_detail = json.dumps(response_q)[:300]
            result["error"] = f"Query embedding failed: {err_detail}"
            result["api_compatible"] = False
            return result

        query_embeddings = [item["embedding"] for item in response_q["data"]]

    result["chunk_embeddings"] = chunk_embeddings
    result["query_embeddings"] = query_embeddings

    for qi, query in enumerate(queries):
        qid = query["id"]
        qvec = query_embeddings[qi]
        scores = []
        for ci, cvec in enumerate(chunk_embeddings):
            sim = cosine_similarity(qvec, cvec)
            scores.append((ci, sim))
        scores.sort(key=lambda x: x[1], reverse=True)

        expected = set(query["expected_relevant_chunk_ids"])
        acceptable = set(query["acceptable_chunk_ids"])

        top1_ids = [chunks[scores[0][0]]["id"]]
        top3_ids = [chunks[scores[i][0]]["id"] for i in range(min(3, len(scores)))]
        top5_ids = [chunks[scores[i][0]]["id"] for i in range(min(5, len(scores)))]

        top1_hit = bool(set(top1_ids) & expected)
        top3_hit = bool(set(top3_ids) & (expected | acceptable))
        top5_hit = bool(set(top5_ids) & (expected | acceptable))

        if top1_hit:
            result["top1_hits"] += 1
        if top3_hit:
            result["top3_hits"] += 1
        if top5_hit:
            result["top5_hits"] += 1

        result["retrieval"][qid] = {
            "query": query["query"],
            "expected": list(expected),
            "acceptable": list(acceptable),
            "top1": top1_ids,
            "top1_hit": top1_hit,
            "top3": top3_ids,
            "top3_hit": top3_hit,
            "top5": top5_ids,
            "top5_hit": top5_hit,
            "scores": [
                {
                    "chunk_id": chunks[scores[i][0]]["id"],
                    "similarity": round(scores[i][1], 6),
                }
                for i in range(min(10, len(scores)))
            ],
        }

    return result


def generate_summary(all_results, dataset, mock_mode):
    lines = []
    lines.append("# Embedding Model Comparison Summary")
    lines.append("")
    lines.append(f"**Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"**Mode:** {'MOCK (synthetic embeddings)' if mock_mode else 'REAL (API calls)'}")
    lines.append(f"**Dataset:** {len(dataset['chunks'])} chunks, {len(dataset['queries'])} queries")
    lines.append("")
    lines.append("## Models evaluated")
    lines.append("")
    lines.append("| Provider | Model | Requested Dims | Actual Dims | Encoding | Compatible | Error |")
    lines.append("|----------|-------|---------------|-------------|----------|------------|-------|")
    for r in all_results:
        err = (r.get("error") or "—")[:60]
        compat = "✓" if r.get("api_compatible") else "✗"
        actual = str(r.get("actual_dimensions") or "—")
        requested = str(r.get("requested_dimensions") or "—")
        enc = r.get("encoding_format") or "—"
        lines.append(f"| {r['provider']} | {r['model']} | {requested} | {actual} | {enc} | {compat} | {err} |")
    lines.append("")

    lines.append("## Retrieval performance")
    lines.append("")
    lines.append("| Provider | Model | Top-1 Hits | Top-3 Hits | Top-5 Hits | Total Queries |")
    lines.append("|----------|-------|-----------|-----------|-----------|--------------|")
    for r in all_results:
        if r.get("skipped") or r.get("error"):
            continue
        lines.append(f"| {r['provider']} | {r['model']} | {r['top1_hits']} | {r['top3_hits']} | {r['top5_hits']} | {r['total_queries']} |")
    lines.append("")

    lines.append("## Latency")
    lines.append("")
    lines.append("| Provider | Model | Chunks batch (ms) | Queries batch (ms) |")
    lines.append("|----------|-------|-------------------|--------------------|")
    for r in all_results:
        if r.get("skipped") or r.get("error"):
            continue
        chunk_ms = r.get("latency_ms", {}).get("batch_chunks", "—")
        query_ms = r.get("latency_ms", {}).get("batch_queries", "—")
        lines.append(f"| {r['provider']} | {r['model']} | {chunk_ms} | {query_ms} |")
    lines.append("")

    active = [r for r in all_results if not r.get("skipped") and not r.get("error")]
    if active:
        lines.append("## Detailed retrieval by query")
        lines.append("")
        for r in active:
            lines.append(f"### {r['provider']} / {r['model']}")
            lines.append("")
            lines.append("| Query | Top-1 | Top-1 Hit | Top-3 Hit | Top-5 Hit |")
            lines.append("|-------|-------|----------|----------|----------|")
            for qid, ret in sorted(r["retrieval"].items()):
                top1 = ret["top1"][0] if ret["top1"] else "—"
                lines.append(f"| {ret['query'][:50]} | {top1} | {'✓' if ret['top1_hit'] else '✗'} | {'✓' if ret['top3_hit'] else '✗'} | {'✓' if ret['top5_hit'] else '✗'} |")
            lines.append("")

    lines.append("## Conclusión preliminar")
    lines.append("")

    if mock_mode:
        lines.append("**⚠️ Este resultado fue generado en modo mock.** Los embeddings son sintéticos deterministas, no representan calidad semántica real. Sirve exclusivamente para validar:")
        lines.append("")
        lines.append("- Estructura del experimento (formato JSON, Markdown, HTML)")
        lines.append("- Ranking y top-k retrieval funcionan correctamente")
        lines.append("- Reporte y reproducibilidad del pipeline")
        lines.append("- La decisión real requiere corrida con APIs auténticas.")
        lines.append("")
        lines.append("**Preguntas que la corrida real debe responder:**")
        lines.append("")
        lines.append("- ¿Conviene mantener text-embedding-3-small como default?")
        lines.append("- ¿Qwen merece prueba ampliada?")
        lines.append("- ¿Perplexity merece prueba ampliada o requiere validación de formato?")
        lines.append("- ¿Algún modelo debe descartarse por error, dimensión, formato o latencia?")
        lines.append("- ¿Hace falta re-embeddizar/reprocesar documentos si se cambia de modelo?")
        lines.append("- ¿La dimensión vectorial actual (1536) queda afectada?")
    else:
        lines.append("*Resultados reales pendientes de interpretación.*")
        lines.append("")
        lines.append("**Criterios de decisión:**")
        lines.append("")
        lines.append("- **Top-3 hits:** el modelo debe ≥ 8/10 para ser considerado")
        lines.append("- **Latencia:** batch chunks debe ser < 2000 ms para ser viable")
        lines.append("- **Dimensión:** debe coincidir con la esperada (1536) o requerir reprocesamiento")
        lines.append("- **Formato:** debe ser float para integración directa con pgvector")
        lines.append("- **Costo:** debe ser comparable o menor al modelo default actual")

    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Compare embedding models for Team360")
    parser.add_argument("--mock", action="store_true", help="Use synthetic embeddings (no API calls)")
    parser.add_argument("--models", nargs="*", default=[], help="Filter providers: openai openrouter perplexity")
    args = parser.parse_args()

    if not GOLDEN_FILE.exists():
        print(f"ERROR: Golden dataset not found at {GOLDEN_FILE}")
        sys.exit(1)

    with open(GOLDEN_FILE) as f:
        dataset = json.load(f)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    mode_tag = "mock" if args.mock else "real"

    models_to_run = CANDIDATE_MODELS
    if args.models:
        models_to_run = [m for m in CANDIDATE_MODELS if m["provider"] in args.models]

    all_results = []
    for model_cfg in models_to_run:
        label = f"{model_cfg['provider']} / {model_cfg['model']}"
        print(f"Evaluating {label} ...")
        result = run_model(model_cfg, dataset, mock_mode=args.mock)
        all_results.append(result)
        if result.get("skipped"):
            print(f"  SKIPPED ({result['error']})")
        elif result.get("error"):
            print(f"  ERROR: {result['error'][:80]}")
        else:
            print(f"  OK  Top-1: {result['top1_hits']}/{result['total_queries']}  "
                  f"Top-3: {result['top3_hits']}/{result['total_queries']}  "
                  f"Top-5: {result['top5_hits']}/{result['total_queries']}  "
                  f"Dims: {result['actual_dimensions']}  "
                  f"Format: {result['encoding_format']}")

    cleaned_results = []
    for r in all_results:
        clean = {k: v for k, v in r.items() if k not in ("chunk_embeddings", "query_embeddings")}
        cleaned_results.append(clean)

    output = {
        "experiment": "embedding-model-comparison",
        "timestamp": timestamp,
        "mode": mode_tag,
        "dataset": {
            "total_chunks": len(dataset["chunks"]),
            "total_queries": len(dataset["queries"]),
        },
        "models": cleaned_results,
    }

    json_file = RESULTS_DIR / f"{timestamp}_{mode_tag}_embedding-comparison.json"
    with open(json_file, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    summary = generate_summary(all_results, dataset, mock_mode=args.mock)
    md_file = json_file.with_suffix(".md")
    with open(md_file, "w") as f:
        f.write(summary)

    print(f"\nJSON:    {json_file}")
    print(f"Summary: {md_file}")


if __name__ == "__main__":
    main()
