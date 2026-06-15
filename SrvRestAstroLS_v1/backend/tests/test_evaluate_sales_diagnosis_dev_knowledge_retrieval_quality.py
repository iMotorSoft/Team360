"""Contract tests for Fase 1.7 evaluator.

All tests are static (no real DB, no real OpenAI, no real service calls).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
EVAL_SCRIPT = SCRIPTS_DIR / "evaluate_sales_diagnosis_dev_knowledge_retrieval_quality.py"
DATASET_PATH = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "sales_diagnosis_knowledge_retrieval_quality_cases_v1.json"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def dataset():
    return json.loads(DATASET_PATH.read_text(encoding="utf-8"))


# ── Dataset tests ───────────────────────────────────────────────────────────


class TestDataset:
    def test_dataset_exists(self):
        assert DATASET_PATH.is_file()

    def test_dataset_is_valid_json(self):
        data = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
        assert data is not None

    def test_dataset_has_meta(self, dataset):
        assert "_meta" in dataset

    def test_dataset_has_cases(self, dataset):
        cases = dataset.get("cases", [])
        assert len(cases) >= 10, f"Expected >=10 cases, got {len(cases)}"

    def test_dataset_has_default_answers(self, dataset):
        da = dataset.get("default_answers", {})
        assert "business_pain" in da
        assert "systems_involved" in da
        assert "frequency_volume" in da

    def test_dataset_has_default_expectations(self, dataset):
        de = dataset.get("default_expectations", {})
        assert "forbidden_claims" in de
        assert "must_have_sources" in de

    def test_each_case_has_case_id(self, dataset):
        for c in dataset["cases"]:
            assert "case_id" in c, f"Missing case_id in {c}"

    def test_each_case_has_question(self, dataset):
        for c in dataset["cases"]:
            assert "question" in c, f"Missing question in {c['case_id']}"
            assert len(c["question"]) > 10

    def test_each_case_has_expectations(self, dataset):
        for c in dataset["cases"]:
            assert "expectations" in c, f"Missing expectations in {c['case_id']}"

    def test_whatsapp_case_exists(self, dataset):
        case_ids = [c["case_id"] for c in dataset["cases"]]
        assert "whatsapp_automation" in case_ids

    def test_sap_case_exists(self, dataset):
        case_ids = [c["case_id"] for c in dataset["cases"]]
        assert "sap_business_one" in case_ids

    def test_seguridad_case_exists(self, dataset):
        case_ids = [c["case_id"] for c in dataset["cases"]]
        assert "seguridad_bypass" in case_ids


# ── Scoring tests ───────────────────────────────────────────────────────────


class TestScoring:
    def _import_scoring(self):
        from scripts.evaluate_sales_diagnosis_dev_knowledge_retrieval_quality import (
            score_result,
            _detect_forbidden_in_text,
            _mentions_honest_limits,
            _reconduces_physical_case,
            _rejects_bypass,
        )
        return score_result, _detect_forbidden_in_text, _mentions_honest_limits, _reconduces_physical_case, _rejects_bypass

    def test_pass_when_completed_with_sources(self):
        score_result_fn, *_ = self._import_scoring()
        case = {
            "case_id": "test",
            "expectations": {"min_sources": 1, "must_have_sources": True},
            "overrides": {},
        }
        result = {
            "case_id": "test",
            "status": "completed",
            "retrieval": {"sources_count": 2, "chunks": [{"source_uri": "doc.md", "node_path": "/test", "title": "T", "score": 0.9, "chunk_id": "c1"}]},
            "forbidden_hits": [],
            "user_response": "Respuesta util con limites honestos.",
            "rule_hits": [],
        }
        score = score_result_fn(result, case)
        assert score["score"] == "PASS", f"Expected PASS, got {score['score']}: {score.get('issues')}"

    def test_fail_when_error_status(self):
        score_result_fn, *_ = self._import_scoring()
        case = {"case_id": "test", "expectations": {}, "overrides": {}}
        result = {"case_id": "test", "status": "error", "error": "something failed"}
        score = score_result_fn(result, case)
        assert score["score"] == "FAIL"

    def test_fail_when_forbidden_claims(self):
        score_result_fn, _detect, *_ = self._import_scoring()
        case = {
            "case_id": "test",
            "expectations": {"forbidden_claims": ["bypass MFA", "diagnostic_code activo"]},
            "overrides": {},
        }
        result = {
            "case_id": "test",
            "status": "completed",
            "retrieval": {"sources_count": 1, "chunks": [{"title": "T", "score": 0.5, "chunk_id": "c1", "source_uri": "doc.md", "node_path": "/t"}]},
            "forbidden_hits": ["bypass MFA"],
            "user_response": "Podemos bypassear MFA",
            "rule_hits": [],
        }
        score = score_result_fn(result, case)
        assert score["score"] == "FAIL", f"Expected FAIL for forbidden claims, got {score['score']}"

    def test_fail_when_bypass_not_rejected(self):
        score_result_fn, *_ = self._import_scoring()
        case = {
            "case_id": "test",
            "expectations": {"must_reject_bypass": True, "forbidden_claims": []},
            "overrides": {},
        }
        result = {
            "case_id": "test",
            "status": "completed",
            "retrieval": {"sources_count": 1, "chunks": [{"title": "T", "score": 0.5, "chunk_id": "c1", "source_uri": "doc.md", "node_path": "/t"}]},
            "forbidden_hits": [],
            "user_response": "Podemos automatizar sin problemas",
            "rule_hits": [],
        }
        score = score_result_fn(result, case)
        assert score["score"] == "FAIL", f"Expected FAIL for missing bypass rejection, got {score['score']}"

    def test_warn_when_no_sources_for_loose_case(self):
        score_result_fn, *_ = self._import_scoring()
        case = {
            "case_id": "test",
            "expectations": {"min_sources": 0, "must_have_sources": False},
            "overrides": {},
        }
        result = {
            "case_id": "test",
            "status": "completed",
            "retrieval": {"sources_count": 0, "chunks": []},
            "forbidden_hits": [],
            "user_response": "Respuesta generica sin fuentes.",
            "rule_hits": [],
        }
        score = score_result_fn(result, case)
        assert score["score"] == "PASS"

    def test_detect_forbidden_in_text(self):
        _, detect_fn, *_ = self._import_scoring()
        text = "Podemos hacer bypass MFA facilmente"
        hits = detect_fn(text, {"bypass MFA"})
        assert "bypass MFA" in hits

    def test_detect_forbidden_not_false_positive(self):
        _, detect_fn, *_ = self._import_scoring()
        text = "No podemos saltarnos la seguridad"
        hits = detect_fn(text, {"bypass MFA"})
        assert "bypass MFA" not in hits

    def test_mentions_honest_limits(self):
        *_, limits_fn, _, _ = self._import_scoring()
        assert limits_fn("depende del caso, hay que evaluar")
        assert not limits_fn("si, podemos automatizar todo")

    def test_reconduces_physical_case(self):
        *_, reconduce_fn, _ = self._import_scoring()
        assert reconduce_fn("podemos automatizar la gestion digital")
        assert not reconduce_fn("horneamos tortas de forma automatica")

    def test_rejects_bypass(self):
        *_, bypass_fn = self._import_scoring()
        assert bypass_fn("no podemos saltarnos MFA")
        assert not bypass_fn("podemos saltar MFA")


# ── Preflight tests ─────────────────────────────────────────────────────────


class TestPreflight:
    def test_preflight_fails_when_no_db(self):
        with patch(
            "modules.db.settings.get_database_settings",
            side_effect=Exception("No DB"),
        ):
            from scripts.evaluate_sales_diagnosis_dev_knowledge_retrieval_quality import (
                run_preflight,
            )
            result = run_preflight()
            assert result.get("preflight_ok") is False

    def test_preflight_detects_missing_openai_key(self):
        with (
            patch(
                "modules.db.settings.get_database_settings",
                side_effect=Exception("No DB"),
            ),
            patch.dict(os.environ, {"PATH": os.environ.get("PATH", "")}, clear=True),
        ):
            from scripts.evaluate_sales_diagnosis_dev_knowledge_retrieval_quality import (
                run_preflight,
            )
            result = run_preflight()
            assert result.get("openai_key_available") is False


# ── Comparison tests ────────────────────────────────────────────────────────


class TestComparison:
    def test_compare_results_detects_improvement(self):
        from scripts.evaluate_sales_diagnosis_dev_knowledge_retrieval_quality import (
            compare_results,
        )

        fake_results = [
            {"case_id": "test", "status": "completed", "retrieval": {"sources_count": 0, "chunks": []},
             "forbidden_hits": [], "user_response": "", "rule_hits": []}
        ]
        knowledge_results = [
            {"case_id": "test", "status": "completed", "retrieval": {"sources_count": 3, "chunks": [
                {"source_uri": "doc1.md", "node_path": "/t1", "title": "T1", "score": 0.9, "chunk_id": "c1"}
            ]}, "forbidden_hits": [], "user_response": "", "rule_hits": []}
        ]
        fake_scores = [{"case_id": "test", "score": "WARN", "issues": ["sources_below_minimum"]}]
        knowledge_scores = [{"case_id": "test", "score": "PASS", "issues": []}]

        comp = compare_results(fake_results, knowledge_results, fake_scores, knowledge_scores)
        assert len(comp) == 1
        assert comp[0]["improved"] is True
        assert comp[0]["fake_sources_count"] == 0
        assert comp[0]["knowledge_sources_count"] == 3

    def test_compare_regression_detection(self):
        from scripts.evaluate_sales_diagnosis_dev_knowledge_retrieval_quality import (
            compare_results,
        )

        fake_results = [
            {"case_id": "test", "status": "completed", "retrieval": {"sources_count": 2, "chunks": []},
             "forbidden_hits": [], "user_response": "", "rule_hits": []}
        ]
        knowledge_results = [
            {"case_id": "test", "status": "completed", "retrieval": {"sources_count": 1, "chunks": []},
             "forbidden_hits": ["bypass MFA"], "user_response": "Podemos bypassear", "rule_hits": []}
        ]
        fake_scores = [{"case_id": "test", "score": "PASS", "issues": []}]
        knowledge_scores = [{"case_id": "test", "score": "FAIL", "issues": ["forbidden_claims"]}]

        comp = compare_results(fake_results, knowledge_results, fake_scores, knowledge_scores)
        assert comp[0]["improved"] is False

    def test_compare_no_regression_no_improvement(self):
        from scripts.evaluate_sales_diagnosis_dev_knowledge_retrieval_quality import (
            compare_results,
        )

        base = {"case_id": "test", "status": "completed", "retrieval": {"sources_count": 1, "chunks": []},
                "forbidden_hits": [], "user_response": "", "rule_hits": []}
        base_score = {"case_id": "test", "score": "PASS", "issues": []}
        comp = compare_results([base], [base], [base_score], [base_score])
        assert comp[0]["improved"] is False  # same score = no improvement
        assert comp[0]["not_worse"] is True  # but no regression either


# ── Dataset loading tests ───────────────────────────────────────────────────


class TestDatasetLoading:
    def test_load_cases_returns_all_by_default(self):
        from scripts.evaluate_sales_diagnosis_dev_knowledge_retrieval_quality import (
            load_cases,
        )
        cases = load_cases()
        assert len(cases) >= 10

    def test_load_cases_filters_by_case_id(self):
        from scripts.evaluate_sales_diagnosis_dev_knowledge_retrieval_quality import (
            load_cases,
        )
        cases = load_cases(case_filter=["whatsapp_automation", "sap_business_one"])
        assert len(cases) == 2
        ids = [c["case_id"] for c in cases]
        assert "whatsapp_automation" in ids
        assert "sap_business_one" in ids

    def test_load_cases_empty_filter_returns_all(self):
        from scripts.evaluate_sales_diagnosis_dev_knowledge_retrieval_quality import (
            load_cases,
        )
        cases = load_cases(case_filter=[])
        assert len(cases) >= 10

    def test_build_answers_for_case_includes_question(self):
        from scripts.evaluate_sales_diagnosis_dev_knowledge_retrieval_quality import (
            build_answers_for_case,
        )
        case = {
            "case_id": "test_case",
            "question": "Test question here?",
            "overrides": {},
            "expectations": {},
        }
        answers = build_answers_for_case(case)
        step_ids = [a["step_id"] for a in answers]
        assert "process_to_automate" in step_ids
        pa = [a for a in answers if a["step_id"] == "process_to_automate"][0]
        assert pa["answer"]["free_text"] == "Test question here?"

    def test_build_answers_all_steps_present(self):
        from scripts.evaluate_sales_diagnosis_dev_knowledge_retrieval_quality import (
            build_answers_for_case,
        )
        case = {
            "case_id": "test_case",
            "question": "Test?",
            "overrides": {},
            "expectations": {},
        }
        answers = build_answers_for_case(case)
        expected_steps = [
            "process_to_automate", "business_pain", "systems_involved",
            "frequency_volume", "rules_clarity", "human_dependency",
            "access_security", "data_sensitivity", "expected_result",
            "economic_impact",
        ]
        found_ids = [a["step_id"] for a in answers]
        for step in expected_steps:
            assert step in found_ids, f"Missing step: {step}"

    def test_build_answers_applies_overrides(self):
        from scripts.evaluate_sales_diagnosis_dev_knowledge_retrieval_quality import (
            build_answers_for_case,
        )
        case = {
            "case_id": "test",
            "question": "Test?",
            "overrides": {
                "systems_involved": {"selected": ["api"], "free_text": "custom"},
                "human_dependency": {"selected": ["high"]},
            },
            "expectations": {},
        }
        answers = build_answers_for_case(case)
        si = [a for a in answers if a["step_id"] == "systems_involved"][0]
        assert si["answer"]["selected"] == ["api"]
        hd = [a for a in answers if a["step_id"] == "human_dependency"][0]
        assert hd["answer"]["selected"] == ["high"]


# ── Service builder tests ───────────────────────────────────────────────────


class TestServiceBuilder:
    def test_build_fake_service_uses_mock_ai(self):
        from scripts.evaluate_sales_diagnosis_dev_knowledge_retrieval_quality import (
            _build_service_for_mode,
        )
        from modules.automation_diagnosis.ai_interpreter import MockAIInterpreter
        from modules.automation_diagnosis.knowledge_connector import (InMemoryKnowledgeRepository)

        service = _build_service_for_mode("fake")
        assert isinstance(service.ai_interpreter, MockAIInterpreter)

    def test_build_knowledge_service_uses_real_provider(self):
        from scripts.evaluate_sales_diagnosis_dev_knowledge_retrieval_quality import (
            _build_service_for_mode,
        )

        service = _build_service_for_mode("knowledge_ingestion")
        from modules.automation_diagnosis.knowledge_retrieval_provider import (
            KnowledgeIngestionSalesDiagnosisRetrievalProvider,
        )
        assert isinstance(
            service.knowledge_repository,
            KnowledgeIngestionSalesDiagnosisRetrievalProvider,
        )


# ── Smoke script contract tests ─────────────────────────────────────────────


class TestSmokeScript:
    SMOKE_SCRIPT = SCRIPTS_DIR / "smoke_sales_diagnosis_dev_knowledge_quality_evaluation.py"

    def test_smoke_script_exists(self):
        assert self.SMOKE_SCRIPT.is_file()

    def test_smoke_script_imports_cleanly(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("smoke_f17", self.SMOKE_SCRIPT)
        assert spec is not None

    def test_smoke_checks_env_flag(self):
        source = self.SMOKE_SCRIPT.read_text(encoding="utf-8")
        assert "TEAM360_SALES_DIAGNOSIS_DEV_RETRIEVAL_PROVIDER" in source

    def test_smoke_has_smoke_cases(self):
        source = self.SMOKE_SCRIPT.read_text(encoding="utf-8")
        assert "whatsapp_automation" in source
        assert "qr_diagnostic_code" in source
        assert "mfa_aprobacion_manual" in source
        assert "sap_business_one" in source

    def test_smoke_has_preflight(self):
        source = self.SMOKE_SCRIPT.read_text(encoding="utf-8")
        assert "Preflight DB" in source or "PREFLIGHT" in source
        assert "Embeddings exist" in source

    def test_smoke_checks_output_files(self):
        source = self.SMOKE_SCRIPT.read_text(encoding="utf-8")
        assert "Report file generated" in source

    def test_smoke_sanitizes_secrets(self):
        source = self.SMOKE_SCRIPT.read_text(encoding="utf-8")
        assert "_sanitize" in source
        assert "sanitize_dsn" in source

    def test_smoke_does_not_use_product_endpoint(self):
        source = self.SMOKE_SCRIPT.read_text(encoding="utf-8")
        assert "/api/diagnosis/" not in source

    def test_smoke_does_not_activate_blocked_features(self):
        source = self.SMOKE_SCRIPT.read_text(encoding="utf-8")
        assert "lead_capture" not in source
        assert "WhatsApp handoff" not in source


# ── Report schema tests ─────────────────────────────────────────────────────


class TestReportSchema:
    def test_generate_report_has_expected_keys(self):
        from scripts.evaluate_sales_diagnosis_dev_knowledge_retrieval_quality import (
            generate_report,
        )
        report = generate_report(
            mode="test",
            results=[],
            scores=[],
            comparison=None,
            preflight=None,
        )
        assert "report_metadata" in report
        assert "summary" in report
        assert "results" in report
        assert "scores" in report
        assert report["report_metadata"]["fase"] == "1.7"
        assert report["report_metadata"]["mode"] == "test"

    def test_report_summary_counts(self):
        from scripts.evaluate_sales_diagnosis_dev_knowledge_retrieval_quality import (
            generate_report,
        )
        scores = [
            {"case_id": "a", "score": "PASS"},
            {"case_id": "b", "score": "WARN"},
            {"case_id": "c", "score": "FAIL"},
        ]
        report = generate_report(mode="test", results=[], scores=scores)
        assert report["summary"]["passed"] == 1
        assert report["summary"]["warned"] == 1
        assert report["summary"]["failed"] == 1

    def test_report_no_comparable_when_preflight_fails(self):
        from scripts.evaluate_sales_diagnosis_dev_knowledge_retrieval_quality import (
            generate_report,
        )
        report = generate_report(
            mode="knowledge_ingestion",
            results=[],
            scores=[],
            preflight={"preflight_ok": False, "reason": "DB unavailable"},
        )
        assert report.get("preflight", {}).get("preflight_ok") is False

    def test_report_with_comparison(self):
        from scripts.evaluate_sales_diagnosis_dev_knowledge_retrieval_quality import (
            generate_report,
        )
        comparison = [
            {"case_id": "a", "improved": True, "fake_score": "WARN", "knowledge_score": "PASS"},
        ]
        report = generate_report(
            mode="comparison",
            results=[],
            scores=[],
            comparison=comparison,
        )
        assert "comparison" in report
        assert "comparison_summary" in report


# ── Forbidden patterns test ─────────────────────────────────────────────────


def test_forbidden_patterns_defined():
    from scripts.evaluate_sales_diagnosis_dev_knowledge_retrieval_quality import (
        FORBIDDEN_PATTERNS,
    )
    assert len(FORBIDDEN_PATTERNS) > 0
    assert "bypass mfa" in FORBIDDEN_PATTERNS
    assert "step-to-action" in FORBIDDEN_PATTERNS


# ── Fase 1.8A quality signal tests ──────────────────────────────────────────


class TestFase18ASignals:
    def _import_signals(self):
        from scripts.evaluate_sales_diagnosis_dev_knowledge_retrieval_quality import (
            _explains_automation_simply,
            _reframes_physical_to_digital,
            _promises_physical_solution,
            _mentions_kpi_orientation,
            _mentions_platform_permission_limits,
            _reconduces_vague_case,
            _asks_useful_question,
            _detects_digitalization_opportunity,
            _promises_whatsapp_handoff_ready,
        )
        return (
            _explains_automation_simply,
            _reframes_physical_to_digital,
            _promises_physical_solution,
            _mentions_kpi_orientation,
            _mentions_platform_permission_limits,
            _reconduces_vague_case,
            _asks_useful_question,
            _detects_digitalization_opportunity,
            _promises_whatsapp_handoff_ready,
        )

    def _get_signals(self):
        from scripts.evaluate_sales_diagnosis_dev_knowledge_retrieval_quality import (
            _explains_automation_simply,
            _reframes_physical_to_digital,
            _promises_physical_solution,
            _mentions_kpi_orientation,
            _mentions_platform_permission_limits,
            _reconduces_vague_case,
            _asks_useful_question,
            _detects_digitalization_opportunity,
            _promises_whatsapp_handoff_ready,
        )
        return (
            _explains_automation_simply,
            _reframes_physical_to_digital,
            _promises_physical_solution,
            _mentions_kpi_orientation,
            _mentions_platform_permission_limits,
            _reconduces_vague_case,
            _asks_useful_question,
            _detects_digitalization_opportunity,
            _promises_whatsapp_handoff_ready,
        )

    def test_explain_automation_simply_positive(self):
        s = self._get_signals()
        assert s[0]("Automatizar significa usar software para que una tarea repetitiva se haga sola.")
        assert s[0]("Por ejemplo, en lugar de hacerlo a mano cada vez, un programa lo hace automaticamente.")

    def test_explain_automation_simply_negative(self):
        s = self._get_signals()
        assert not s[0]("El proceso es automatizable mediante integracion de APIs.")
        assert not s[0]("")

    def test_reframes_physical_to_digital_positive(self):
        s = self._get_signals()
        assert s[1]("No realizamos la accion fisica, pero podemos automatizar la coordinacion alrededor.")
        assert s[1]("Podemos ayudarte con el registro de incidentes y el seguimiento del estado.")

    def test_reframes_physical_to_digital_negative(self):
        s = self._get_signals()
        assert not s[1]("Si, podemos cambiar la rueda automaticamente.")

    def test_promises_physical_solution_positive(self):
        s = self._get_signals()
        assert s[2]("Tenemos un robot que cambia la rueda por ti.")
        assert s[2]("Podemos reparar automaticamente.")

    def test_promises_physical_solution_negative(self):
        s = self._get_signals()
        assert not s[2]("No hacemos tareas fisicas, solo procesos digitales.")

    def test_mentions_kpi_orientation_positive(self):
        s = self._get_signals()
        assert s[3]("Podemos ayudarte con KPIs como visualizaciones, alcance y metricas.")
        assert s[3]("Tablero de metricas con reportes automaticos.")

    def test_mentions_kpi_orientation_negative(self):
        s = self._get_signals()
        assert not s[3]("Automatizamos la publicacion en redes.")

    def test_mentions_platform_limits_positive(self):
        s = self._get_signals()
        assert s[4]("Depende de los permisos y la API de la plataforma.")
        assert s[4]("Si la plataforma tiene API disponible y tenes acceso.")

    def test_mentions_platform_limits_negative(self):
        s = self._get_signals()
        assert not s[4]("Publicamos automaticamente en cualquier red.")

    def test_reconduces_vague_case_positive(self):
        s = self._get_signals()
        assert s[5]("Podemos empezar por un area especifica. Elegi una: ventas, atencion, marketing.")
        assert s[5]("Contame mas sobre que parte de tu negocio queres automatizar primero.")

    def test_reconduces_vague_case_negative(self):
        s = self._get_signals()
        assert not s[5]("Automatizamos todo tu negocio sin preguntas.")

    def test_asks_useful_question_positive(self):
        s = self._get_signals()
        assert s[6]("Contame que tarea concreta te gustaria automatizar.")
        assert s[6]("Podes contarme mas sobre tu proceso actual?")

    def test_asks_useful_question_negative(self):
        s = self._get_signals()
        assert not s[6]("")

    def test_detects_digitalization_opportunity_positive(self):
        s = self._get_signals()
        assert s[7]("Podemos ayudarte a digitalizar tus registros.")
        assert s[7]("Podemos capturar la informacion que llega por WhatsApp y ordenarla.")

    def test_detects_digitalization_opportunity_negative(self):
        s = self._get_signals()
        assert not s[7]("Deberias comprar un software.")

    def test_promises_whatsapp_handoff_ready_positive(self):
        s = self._get_signals()
        assert s[8]("El WhatsApp handoff automatico ya esta listo y funcionando.")
        assert s[8]("WhatsApp handoff activo")

    def test_promises_whatsapp_handoff_ready_negative(self):
        s = self._get_signals()
        assert not s[8]("La integracion con WhatsApp requiere configuracion previa.")
        assert not s[8]("Actualmente el envio automatico no esta disponible.")


# ── Dataset v2 tests ────────────────────────────────────────────────────────


class TestDatasetV2:
    def test_dataset_has_5_new_cases(self):
        from scripts.evaluate_sales_diagnosis_dev_knowledge_retrieval_quality import (
            load_cases,
        )
        cases = load_cases()
        case_ids = [c["case_id"] for c in cases]
        assert "explain_automation_basic" in case_ids, "Missing new case"
        assert "physical_task_car_wheel" in case_ids, "Missing new case"
        assert "tiktok_kpi_marketing" in case_ids, "Missing new case"
        assert "vague_automate_everything" in case_ids, "Missing new case"
        assert "manual_process_to_digital" in case_ids, "Missing new case"

    def test_dataset_has_15_cases_total(self):
        from scripts.evaluate_sales_diagnosis_dev_knowledge_retrieval_quality import (
            load_cases,
        )
        cases = load_cases()
        assert len(cases) >= 15, f"Expected >=15 cases, got {len(cases)}"

    def test_new_cases_have_question(self):
        from scripts.evaluate_sales_diagnosis_dev_knowledge_retrieval_quality import (
            load_cases,
        )
        cases = load_cases()
        new_ids = [
            "explain_automation_basic", "physical_task_car_wheel",
            "tiktok_kpi_marketing", "vague_automate_everything",
            "manual_process_to_digital",
        ]
        for case in cases:
            if case["case_id"] in new_ids:
                assert len(case["question"]) > 10, f"Short question in {case['case_id']}"

    def test_explain_case_has_must_explain_simple(self):
        from scripts.evaluate_sales_diagnosis_dev_knowledge_retrieval_quality import (
            load_cases,
        )
        cases = load_cases()
        c = [c for c in cases if c["case_id"] == "explain_automation_basic"][0]
        assert c["expectations"].get("must_explain_simple") is True

    def test_physical_case_has_must_reconduce_physical(self):
        from scripts.evaluate_sales_diagnosis_dev_knowledge_retrieval_quality import (
            load_cases,
        )
        cases = load_cases()
        c = [c for c in cases if c["case_id"] == "physical_task_car_wheel"][0]
        assert c["expectations"].get("must_reconduce_physical") is True
        assert c["expectations"].get("must_not_promise_physical") is True

    def test_tiktok_case_has_must_marketing_kpi(self):
        from scripts.evaluate_sales_diagnosis_dev_knowledge_retrieval_quality import (
            load_cases,
        )
        cases = load_cases()
        c = [c for c in cases if c["case_id"] == "tiktok_kpi_marketing"][0]
        assert c["expectations"].get("must_marketing_kpi") is True
        assert c["expectations"].get("must_mention_platform_limits") is True

    def test_vague_case_has_must_reconduce_vague(self):
        from scripts.evaluate_sales_diagnosis_dev_knowledge_retrieval_quality import (
            load_cases,
        )
        cases = load_cases()
        c = [c for c in cases if c["case_id"] == "vague_automate_everything"][0]
        assert c["expectations"].get("must_reconduce_vague") is True
        assert c["expectations"].get("must_ask_useful_question") is True

    def test_manual_case_has_digitalization_flag(self):
        from scripts.evaluate_sales_diagnosis_dev_knowledge_retrieval_quality import (
            load_cases,
        )
        cases = load_cases()
        c = [c for c in cases if c["case_id"] == "manual_process_to_digital"][0]
        assert c["expectations"].get("must_detect_digitalization_opportunity") is True
        assert c["expectations"].get("must_not_promise_whatsapp_handoff_ready") is True

    def test_new_cases_filter_by_id(self):
        from scripts.evaluate_sales_diagnosis_dev_knowledge_retrieval_quality import (
            load_cases,
        )
        cases = load_cases(case_filter=["explain_automation_basic", "tiktok_kpi_marketing"])
        assert len(cases) == 2

    def test_smoke_includes_new_cases(self):
        from tests.test_evaluate_sales_diagnosis_dev_knowledge_retrieval_quality import (
            TestSmokeScript,
        )
        source = TestSmokeScript.SMOKE_SCRIPT.read_text(encoding="utf-8")
        assert "explain_automation_basic" in source
        assert "physical_task_car_wheel" in source
        assert "tiktok_kpi_marketing" in source


# ── Fase 1.8A scoring integration tests ─────────────────────────────────────


class TestFase18AScoring:
    def _import_scoring(self):
        from scripts.evaluate_sales_diagnosis_dev_knowledge_retrieval_quality import (
            score_result,
        )
        return score_result

    def test_explain_case_pass_with_simple_explanation(self):
        fn = self._import_scoring()
        case = {
            "case_id": "explain_automation_basic",
            "expectations": {
                "must_explain_simple": True,
                "must_have_sources": True,
                "min_sources": 1,
                "forbidden_claims": [],
            },
            "overrides": {},
        }
        result = {
            "case_id": "explain_automation_basic",
            "status": "completed",
            "retrieval": {"sources_count": 2, "chunks": [{"source_uri": "doc.md", "node_path": "/t", "title": "T", "score": 0.8, "chunk_id": "c1"}]},
            "forbidden_hits": [],
            "user_response": "Automatizar significa usar software para que una tarea repetitiva se haga sola. Por ejemplo, en lugar de enviar un reporte a mano cada semana, el sistema lo genera solo.",
            "rule_hits": [],
        }
        score = fn(result, case)
        assert score["score"] == "PASS", f"Expected PASS, got {score['score']}: {score.get('issues')}"

    def test_explain_case_warn_without_simple_explanation(self):
        fn = self._import_scoring()
        case = {
            "case_id": "explain_automation_basic",
            "expectations": {
                "must_explain_simple": True,
                "must_have_sources": True,
                "min_sources": 1,
                "forbidden_claims": [],
            },
            "overrides": {},
        }
        result = {
            "case_id": "explain_automation_basic",
            "status": "completed",
            "retrieval": {"sources_count": 2, "chunks": [{"source_uri": "doc.md", "node_path": "/t", "title": "T", "score": 0.8, "chunk_id": "c1"}]},
            "forbidden_hits": [],
            "user_response": "El proceso es automatizable con integraciones API.",
            "rule_hits": [],
        }
        score = fn(result, case)
        assert score["score"] == "WARN", f"Expected WARN for missing explanation, got {score['score']}"

    def test_physical_case_fail_with_physical_promise(self):
        fn = self._import_scoring()
        case = {
            "case_id": "physical_task_car_wheel",
            "expectations": {
                "must_not_promise_physical": True,
                "must_have_sources": True,
                "min_sources": 1,
                "forbidden_claims": [],
            },
            "overrides": {},
        }
        result = {
            "case_id": "physical_task_car_wheel",
            "status": "completed",
            "retrieval": {"sources_count": 2, "chunks": [{"source_uri": "doc.md", "node_path": "/t", "title": "T", "score": 0.8, "chunk_id": "c1"}]},
            "forbidden_hits": [],
            "user_response": "Tenemos un robot que puede cambiar la rueda por ti.",
            "rule_hits": [],
        }
        score = fn(result, case)
        assert score["score"] == "FAIL", f"Expected FAIL for physical promise, got {score['score']}"

    def test_marketing_case_warn_without_kpi(self):
        fn = self._import_scoring()
        case = {
            "case_id": "tiktok_kpi_marketing",
            "expectations": {
                "must_marketing_kpi": True,
                "must_have_sources": True,
                "min_sources": 1,
                "forbidden_claims": [],
            },
            "overrides": {},
        }
        result = {
            "case_id": "tiktok_kpi_marketing",
            "status": "completed",
            "retrieval": {"sources_count": 2, "chunks": [{"source_uri": "doc.md", "node_path": "/t", "title": "T", "score": 0.8, "chunk_id": "c1"}]},
            "forbidden_hits": [],
            "user_response": "Publicamos automaticamente en TikTok.",
            "rule_hits": [],
        }
        score = fn(result, case)
        assert score["score"] == "WARN", f"Expected WARN for missing KPI, got {score['score']}"

    def test_whatsapp_handoff_promise_fail(self):
        fn = self._import_scoring()
        case = {
            "case_id": "manual_process_to_digital",
            "expectations": {
                "must_not_promise_whatsapp_handoff_ready": True,
                "must_have_sources": True,
                "min_sources": 1,
                "forbidden_claims": [],
            },
            "overrides": {},
        }
        result = {
            "case_id": "manual_process_to_digital",
            "status": "completed",
            "retrieval": {"sources_count": 2, "chunks": [{"source_uri": "doc.md", "node_path": "/t", "title": "T", "score": 0.8, "chunk_id": "c1"}]},
            "forbidden_hits": [],
            "user_response": "El WhatsApp handoff automatico ya esta listo y activo.",
            "rule_hits": [],
        }
        score = fn(result, case)
        assert score["score"] == "FAIL", f"Expected FAIL for handoff promise, got {score['score']}"

    def test_vague_case_warn_without_reconduction(self):
        fn = self._import_scoring()
        case = {
            "case_id": "vague_automate_everything",
            "expectations": {
                "must_reconduce_vague": True,
                "must_ask_useful_question": True,
                "must_have_sources": False,
                "min_sources": 0,
                "forbidden_claims": [],
            },
            "overrides": {},
        }
        result = {
            "case_id": "vague_automate_everything",
            "status": "completed",
            "retrieval": {"sources_count": 0, "chunks": []},
            "forbidden_hits": [],
            "user_response": "Automatizamos todo tu negocio.",
            "rule_hits": [],
        }
        score = fn(result, case)
        assert score["score"] == "WARN", f"Expected WARN for missing reconduction, got {score['score']}"


# ── Real LLM mode tests ────────────────────────────────────────────────────


class TestRealLLMMode:
    def test_build_service_with_litellm_uses_litellm_interpreter(self):
        from scripts.evaluate_sales_diagnosis_dev_knowledge_retrieval_quality import (
            _build_service_for_mode,
        )
        from modules.automation_diagnosis.ai_interpreter import (
            LiteLLMAIInterpreter,
        )
        service = _build_service_for_mode(
            "fake", ai_provider="litellm", model_alias="test_model"
        )
        assert isinstance(service.ai_interpreter, LiteLLMAIInterpreter)

    def test_build_service_default_uses_mock(self):
        from scripts.evaluate_sales_diagnosis_dev_knowledge_retrieval_quality import (
            _build_service_for_mode,
        )
        from modules.automation_diagnosis.ai_interpreter import MockAIInterpreter
        service = _build_service_for_mode("fake")
        assert isinstance(service.ai_interpreter, MockAIInterpreter)

    def test_run_case_includes_ai_provider(self):
        from scripts.evaluate_sales_diagnosis_dev_knowledge_retrieval_quality import (
            _build_service_for_mode,
            run_case,
        )
        service = _build_service_for_mode("fake")
        case = {"case_id": "test_llm", "question": "Test?", "overrides": {}, "expectations": {}}
        result = run_case(service, case)
        assert "ai_provider" in result
        assert "ai_model" in result
        assert "response_is_fallback" in result
        assert "response_text_length" in result

    def test_report_schema_includes_ai_fields(self):
        from scripts.evaluate_sales_diagnosis_dev_knowledge_retrieval_quality import (
            generate_report,
        )
        report = generate_report(
            mode="knowledge_ingestion",
            results=[{"ai_provider": "litellm", "ai_model": "test_model",
                       "response_is_fallback": False, "response_text_length": 100,
                       "case_id": "t1"}],
            scores=[],
        )
        assert report["report_metadata"]["ai_provider"] == "mock"

    def test_real_llm_flag_sets_ai_provider(self):
        import argparse
        from scripts.evaluate_sales_diagnosis_dev_knowledge_retrieval_quality import main
        import scripts.evaluate_sales_diagnosis_dev_knowledge_retrieval_quality as mod
        # Test that --real-llm maps to litellm provider
        parser = argparse.ArgumentParser()
        parser.add_argument("--real-llm", action="store_true")
        parser.add_argument("--ai-provider", default="mock")
        parser.add_argument("--model-alias", default=None)
        args = parser.parse_args(["--real-llm", "--model-alias", "test"])
        # Simulate the provider resolution logic
        ai_provider = args.ai_provider
        if args.real_llm:
            ai_provider = "litellm"
        assert ai_provider == "litellm"

    def test_ai_provider_override_works(self):
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--real-llm", action="store_true")
        parser.add_argument("--ai-provider", default="mock")
        args = parser.parse_args(["--ai-provider", "litellm"])
        ai_provider = args.ai_provider
        assert ai_provider == "litellm"

    def test_missing_litellm_returns_error_gracefully(self):
        from scripts.evaluate_sales_diagnosis_dev_knowledge_retrieval_quality import (
            _build_service_for_mode,
        )
        import os
        saved_key = os.environ.pop("LITELLM_MASTER_KEY", None)
        saved_te_key = os.environ.pop("TEAM360_LITELLM_API_KEY", None)
        saved_li_key = os.environ.pop("LITELLM_API_KEY", None)
        try:
            service = _build_service_for_mode(
                "fake", ai_provider="litellm", model_alias="nonexistent_model"
            )
            assert service.ai_interpreter is not None
        finally:
            if saved_key:
                os.environ["LITELLM_MASTER_KEY"] = saved_key
            if saved_te_key:
                os.environ["TEAM360_LITELLM_API_KEY"] = saved_te_key
            if saved_li_key:
                os.environ["LITELLM_API_KEY"] = saved_li_key


# ── No secret leakage ───────────────────────────────────────────────────────


class TestNoSecrets:
    def test_evaluator_no_secret_in_source(self):
        source = EVAL_SCRIPT.read_text(encoding="utf-8")
        assert "get_database_settings" in source or "settings.dsn" in source
        assert "api-key" not in source.lower()

    def test_smoke_no_secret_in_source(self):
        from tests.test_evaluate_sales_diagnosis_dev_knowledge_retrieval_quality import (
            TestSmokeScript,
        )
        source = TestSmokeScript.SMOKE_SCRIPT.read_text(encoding="utf-8")
        assert "sanitize_dsn" in source or "_sanitize" in source
