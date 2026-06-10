# Fase 1.7d — Detailed Progressive Response Report

**Generated:** 2026-06-10 12:13 UTC
**Source:** progressive_response_20260610_121329.json
**Strategy:** templated-quick-final-llm

## Summary

- **experiment:** Fase 1.7d — Latency / Progressive Response Simulation
- **strategy:** templated-quick-final-llm
- **model:** gpt-5-nano
- **top_n:** 20
- **top_k:** 5
- **max_context_chars:** 6000
- **quick_max_output_tokens:** 120
- **final_max_output_tokens:** 500
- **total_scenarios:** 2
- **total_turns:** 4
- **avg_time_to_first_status_ms:** 0
- **avg_time_to_sources_ready_ms:** 0
- **avg_time_to_quick_answer_ms:** 0.0
- **avg_time_to_final_answer_ms:** 0.0
- **avg_total_time_ms:** 0.0
- **p50_quick_answer_ms:** 0
- **p95_quick_answer_ms:** 0
- **p50_final_answer_ms:** 0.0
- **p95_final_answer_ms:** 0.1
- **p95_total_ms:** 0.1
- **avg_retrieval_latency_ms:** 0
- **quick_answer_safe_rate:** 100.0
- **final_answer_pass_rate:** 100.0
- **combined_pass_rate:** 100.0
- **final_guardrail_failure_count:** 0
- **perceived_latency_gain_ms:** None
- **perceived_latency_gain_percent:** None
- **baseline_avg_total_ms:** 0.0
- **no_llm_mode:** True
- **empty_turn_count:** 0
- **timeout_or_error_count:** 0

## Per-Scenario Event Timeline

### conv_01 — Consulta genérica sobre automatización

- **Strategy:** templated-quick-final-llm
- **Turns:** 2

#### Turn 1

**User:** Quiero automatizar mi negocio.
**Total latency:** 0.1ms
**Quick:** Gracias por tu consulta. Veo que querés automatizar tu negocio. Contame un poco ...
  - Passed: True
**Combined:** PASS

#### Turn 2

**User:** Tengo una empresa de servicios y recibo consultas por WhatsApp.
**Total latency:** 0.0ms
**Quick:** Gracias por tu consulta. Veo que querés automatizar tu negocio. Contame un poco ...
  - Passed: True
**Combined:** PASS

**Result:** 2/2 turns passed (0 failed)

---

### conv_02 — Leads perdidos por falta de seguimiento

- **Strategy:** templated-quick-final-llm
- **Turns:** 2

#### Turn 1

**User:** Tengo muchos leads pero se pierden porque nadie les responde rápido.
**Total latency:** 0.0ms
**Quick:** Entiendo que estás perdiendo leads por demoras en la respuesta. Es un problema f...
  - Passed: True
**Combined:** PASS

#### Turn 2

**User:** Vienen de Facebook e Instagram.
**Total latency:** 0.0ms
**Quick:** Entiendo que estás perdiendo leads por demoras en la respuesta. Es un problema f...
  - Passed: True
**Combined:** PASS

**Result:** 2/2 turns passed (0 failed)

---


_End of detailed report. Source: progressive_response_20260610_121329.json_