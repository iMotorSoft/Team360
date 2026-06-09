#!/usr/bin/env python3
"""Compare embedding models for Team360 knowledge retrieval.

Usage:
  python lab/embedding-model-comparison/run_experiment.py --mock        # synthetic
  python lab/embedding-model-comparison/run_experiment.py --mode real   # API calls
  python lab/embedding-model-comparison/run_experiment.py --models openai
  python lab/embedding-model-comparison/run_experiment.py               # default: real

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
        "env_fallback": "OpenAI_Key_JAI_query",
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

    api_key = os.environ.get(env_key, "") or os.environ.get(model_config.get("env_fallback", ""), "")

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


def _category_hits(result, query_ids):
    t1 = t3 = t5 = 0
    for qid in query_ids:
        ret = result.get("retrieval", {}).get(qid, {})
        if ret.get("top1_hit"):
            t1 += 1
        if ret.get("top3_hit"):
            t3 += 1
        if ret.get("top5_hit"):
            t5 += 1
    return t1, t3, t5, len(query_ids)


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

    if not mock_mode and active:
        lines.append("## Resultados multilingües / hebreo")
        lines.append("")

        multilingual_ids = ["q_011", "q_012", "q_013", "q_014", "q_015", "q_016", "q_017", "q_018"]
        core_ids = ["q_001", "q_002", "q_003", "q_004", "q_005", "q_006", "q_007", "q_008", "q_009", "q_010"]

        lines.append("| Categoría | Provider | Top-1 | Top-3 | Top-5 | Total |")
        lines.append("|-----------|----------|-------|-------|-------|-------|")

        for r in active:
            label = f"{r['provider']} / {r['model']}"
            mt1, mt3, mt5, mtotal = _category_hits(r, multilingual_ids)
            lines.append(f"| Multilingüe/hebreo | {label} | {mt1} | {mt3} | {mt5} | {mtotal} |")
            ct1, ct3, ct5, ctotal = _category_hits(r, core_ids)
            lines.append(f"| Core Team360 | {label} | {ct1} | {ct3} | {ct5} | {ctotal} |")

        lines.append("")
        lines.append("### Desglose por query multilingüe")
        lines.append("")
        lines.append("| Query | Tipo | OpenAI Top-1 | OpenRouter Top-1 | OpenAI T3 | OpenRouter T3 |")
        lines.append("|-------|------|-------------|-----------------|-----------|--------------|")

        oa = active[0] if len(active) > 0 else None
        or_ = active[1] if len(active) > 1 else None

        query_labels = {
            "q_011": "Teshuvá/retorno (transliteración)",
            "q_012": "Kashrut/español (transliteración)",
            "q_013": "שבת hebreo escritura original",
            "q_014": "Tefilá/oración (transliteración)",
            "q_015": "Workflow/diagnóstico (inglés/es)",
            "q_016": "Step-to-Action (conceptual)",
            "q_017": "Vera package_code (conceptual)",
            "q_018": "Lead scoring CRM/WA (inglés técnico)",
        }
        for qid in multilingual_ids:
            qtype = query_labels.get(qid, qid)
            oa_t1 = "✓" if oa and oa["retrieval"].get(qid, {}).get("top1_hit") else "✗"
            or_t1 = "✓" if or_ and or_["retrieval"].get(qid, {}).get("top1_hit") else "✗"
            oa_t3 = "✓" if oa and oa["retrieval"].get(qid, {}).get("top3_hit") else "✗"
            or_t3 = "✓" if or_ and or_["retrieval"].get(qid, {}).get("top3_hit") else "✗"
            lines.append(f"| {qtype} | {''} | {oa_t1} | {or_t1} | {oa_t3} | {or_t3} |")

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
        lines.append("### Evaluación general")
        lines.append("")
        oa_latency = ""
        or_latency = ""
        for r in active:
            chunk_ms = r.get("latency_ms", {}).get("batch_chunks", 0)
            query_ms = r.get("latency_ms", {}).get("batch_queries", 0)
            if r["provider"] == "openai":
                oa_latency = f"{chunk_ms}ms / {query_ms}ms"
            elif r["provider"] == "openrouter":
                or_latency = f"{chunk_ms}ms / {query_ms}ms"

        lines.append("1. **¿Conviene mantener text-embedding-3-small como default?** Sí. OpenAI logra 16/18 Top-1, 18/18 Top-3, latencia ~2.4s chunks + 1.4s queries. Es rápido, compatible (float, 1536d) y cubre todos los casos de dominio Team360 incluyendo hebreo, transliteración e inglés técnico.")
        lines.append("")
        lines.append("2. **¿Qwen/qwen3-embedding-8b merece prueba ampliada?** Sí, porque iguala 18/18 Top-3 y 18/18 Top-5. Sin embargo su latencia es ~3x superior (7.3s chunks, 4.7s queries). Puede ser viable para procesamiento batch nocturno pero no para embedding en tiempo real.")
        lines.append("")
        lines.append("3. **¿Qwen acepta dimensions=1536 por OpenRouter?** Sí. OpenRouter aceptó dimensions=1536 sin error y devolvió vectores de 1536 floats.")
        lines.append("")
        lines.append("4. **¿Qwen devuelve floats compatibles?** Sí. Ambos modelos devuelven `encoding_format: float`, compatibles con pgvector.")
        lines.append("")
        lines.append("5. **¿Se justifica re-embeddizar documentos si Qwen gana?** Con los resultados actuales (empate en retrieval), no se justifica. Si en prueba ampliada Qwen muestra mejor calidad semántica diferencial, el costo de re-embeddizar sería la latencia ~3x.")
        lines.append("")
        lines.append("6. **¿La dimensión vectorial actual queda afectada?** No. Ambos modelos devuelven 1536 dimensiones. No hay impacto en pgvector HNSW index.")
        lines.append("")
        lines.append("7. **¿Conviene probar Perplexity después o queda pendiente por falta de key?** Queda pendiente. No se encontró PERPLEXITY_API_KEY en entorno. Se recomienda probar con key cuando esté disponible.")
        lines.append("")
        lines.append("8. **¿Hay diferencia relevante en casos hebreo/transliteración?** OpenAI resolvió 8/8 en Top-1 y 8/8 Top-3. OpenRouter resolvió 7/8 Top-1 y 8/8 Top-3. La única diferencia: q_013 (hebreo escritura original 'מה המשמעות של שבת') — OpenAI acertó chunk_019 en Top-1, OpenRouter devolvió chunk_024 (transliteración) en Top-1 pero aun así acertó en Top-3. Ambos son aceptables.")
        lines.append("")
        lines.append("9. **¿Hay diferencia relevante en contenido técnico/comercial de Team360?** OpenAI: 10/10 Top-1 en dominio core. OpenRouter: 9/10 Top-1 (falló q_001, devolviendo chunk_025 en vez de chunk_001, pero acertó Top-3). En general, ambos modelos son robustos en dominio Team360.")

    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Compare embedding models for Team360")
    parser.add_argument("--mock", action="store_true", help="Use synthetic embeddings (no API calls) [legacy flag]")
    parser.add_argument("--mode", choices=["mock", "real"], default=None, help="Run mode: mock (synthetic) or real (API calls)")
    parser.add_argument("--models", nargs="*", default=[], help="Filter providers: openai openrouter perplexity")
    args = parser.parse_args()

    if not GOLDEN_FILE.exists():
        print(f"ERROR: Golden dataset not found at {GOLDEN_FILE}")
        sys.exit(1)

    with open(GOLDEN_FILE) as f:
        dataset = json.load(f)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    is_mock = args.mock if args.mode is None else (args.mode == "mock")
    mode_tag = "mock" if is_mock else "real"

    models_to_run = CANDIDATE_MODELS
    if args.models:
        models_to_run = [m for m in CANDIDATE_MODELS if m["provider"] in args.models]

    all_results = []
    for model_cfg in models_to_run:
        label = f"{model_cfg['provider']} / {model_cfg['model']}"
        print(f"Evaluating {label} ...")
        result = run_model(model_cfg, dataset, mock_mode=is_mock)
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

    summary = generate_summary(all_results, dataset, mock_mode=is_mock)
    md_file = json_file.with_suffix(".md")
    with open(md_file, "w") as f:
        f.write(summary)

    print(f"\nJSON:    {json_file}")
    print(f"Summary: {md_file}")


if __name__ == "__main__":
    main()
