#!/usr/bin/env python3
"""Validate intent classifier and TurnDecision via real /api/diagnosis/turn calls."""

import json, urllib.request, uuid, sys, time

BASE = "http://127.0.0.1:7050/api/diagnosis/turn"
PASS = 0
FAIL = 0
TOTAL = 0

def turn(sid, msg, locale="es", expect=None):
    global PASS, FAIL, TOTAL
    TOTAL += 1
    payload = json.dumps({"session_id": sid, "message": msg, "locale": locale}).encode()
    req = urllib.request.Request(BASE, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            r = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:200]
        print(f"  HTTP {e.code}: {body}")
        FAIL += 1
        return {}

    td = r.get("turn_decision", {}) or {}
    lang = r.get("language", {}) or {}
    intent = td.get("intent", "?")
    scope = td.get("intent_scope", "?")
    src = td.get("intent_source", "?")
    action = td.get("action", "?")
    reason = td.get("readiness_reason", "?")
    text = r.get("response_text", "")[:100]
    diag_status = td.get("diagnosis_status", "?")

    ok = True
    issues = []
    if expect:
        for key, val in expect.items():
            actual = td.get(key, lang.get(key, "?"))
            if actual != val:
                ok = False
                issues.append(f"{key}={actual}(expected {val})")

    status = "OK" if ok else "ISSUE"
    if not ok: FAIL += 1
    else: PASS += 1

    print(f"  [{status}] intent={intent:25s} scope={scope:15s} src={src:20s} action={action:10s} reason={reason:30s} diag={diag_status}")
    if issues:
        for i in issues:
            print(f"         {i}")
    print(f"         {text}...")
    print()
    return {"response": r, "turn_decision": td, "language": lang}

def session(name):
    sid = f"val_{name}_{uuid.uuid4().hex[:6]}"
    print(f"\n{'='*60}")
    print(f"DIALOGUE: {name}")
    print(f"Session: {sid}")
    print(f"{'='*60}")
    return sid

def pg_check(sid):
    import subprocess
    r = subprocess.run(
        ["docker", "exec", "imotorsoft-postgres", "psql", "-U", "administrator", "-d", "team360", "-t", "-A",
         f"SELECT state_jsonb->'semantic_memory' FROM sales_diagnosis_conversation_states WHERE session_id='{sid}'"],
        capture_output=True, text=True, timeout=5
    )
    return r.stdout.strip()[:500]

print(f"Base URL: {BASE}")
print()

# ---- DIALOGUE 1: Full normal flow ----
sid = session("01_full_flow")
turn(sid, "Quiero responder automaticamente las consultas de venta.")
turn(sid, "Entran por WhatsApp y Gmail.")
turn(sid, "Son unas 80 por dia.")
turn(sid, "El stock esta en el sistema y los precios en una planilla.")
turn(sid, "Las respuestas comunes pueden salir solas, pero los descuentos especiales los revisa una persona.")
turn(sid, "Con esto dame una orientacion inicial.", expect={"action": "diagnose"})

# ---- DIALOGUE 2: Data + diagnosis same turn ----
sid = session("02_data_and_diag")
turn(sid, "Queremos automatizar consultas por WhatsApp.")
turn(sid, "El stock esta en nuestro sistema.")
turn(sid, "Son unas 80 consultas por dia y ya podés decirme qué harías.", expect={"intent": "request_diagnosis"})

# ---- DIALOGUE 3: Point question ----
sid = session("03_point_question")
turn(sid, "Queremos automatizar consultas de clientes.")
r = turn(sid, "¿Se puede conectar Gmail?")
td = r.get("turn_decision", {})
assert td.get("action") != "diagnose", "Point question should not diagnose"
assert td.get("diagnosis_status") != "completed", "Point question should not complete diagnosis"
print("  >> Point question guard OK: diagnosis not completed")

# ---- DIALOGUE 4: False positive stop_interview ----
sid = session("04_false_stop")
turn(sid, "No quiero responder ese mensaje automaticamente.", expect={"intent": "provide_information"})

# ---- DIALOGUE 5: Real stop interview ----
sid = session("05_real_stop")
turn(sid, "Quiero automatizar consultas por WhatsApp.")
turn(sid, "El stock esta en nuestro sistema.")
turn(sid, "No quiero seguir respondiendo preguntas. Orientame con lo que ya tenés.", expect={"intent": "stop_interview"})

# ---- DIALOGUE 6: Correction ----
sid = session("06_correction")
turn(sid, "Las respuestas comunes pueden salir automaticamente.")
r2 = turn(sid, "En realidad, tambien quiero que las respuestas comunes sean aprobadas por una persona.", expect={"intent": "provide_information"})

# ---- DIALOGUE 7: English ambiguous ----
sid = session("07_english")
turn(sid, "I want to automate customer inquiries.", locale="en")
turn(sid, "They come through WhatsApp and Gmail.", locale="en")
turn(sid, "Tell me what you would do first.", locale="en", expect={"intent": "request_diagnosis"})

# ---- DIALOGUE 8: Hebrew ----
sid = session("08_hebrew")
turn(sid, "אני רוצה להפוך את פניות הלקוחות לאוטומטיות", locale="he")
turn(sid, "הפניות מגיעות דרך WhatsApp ו-Gmail", locale="he")
turn(sid, "לפי מה שסיפרתי, מה אתה ממליץ לעשות?", locale="he", expect={"intent": "request_diagnosis"})

# ---- DIALOGUE 9: Mixed message ----
sid = session("09_mixed")
turn(sid, "Tenemos consultas por WhatsApp y Gmail.")
r9 = turn(sid, "Con esto ya está, give me an initial assessment.")
lang9 = r9.get("language", {})
resp_lang = lang9.get("response_language", "?")
print(f"  response_language={resp_lang}")
# Should remain Spanish

# ---- DIALOGUE 10: Factual simple responses ----
sid = session("10_factual")
turn(sid, "Quiero automatizar consultas.")
turn(sid, "WhatsApp y Gmail.")
turn(sid, "80 por dia.")
turn(sid, "Sí.")
turn(sid, "Los descuentos los aprueba una persona.")

# ---- DIALOGUE 11: "Diagnóstico" mentioned but not requested ----
sid = session("11_diag_mentioned")
turn(sid, "El diagnostico que me mandaron antes estaba incompleto.", expect={"intent_source": "ai_classifier"})

# ---- DIALOGUE 12: Point vs global recommendation ----
sid = session("12a_point_rec")
turn(sid, "¿Qué conviene usar para leer los correos?", expect={"intent": "ask_point_question"})

sid = session("12b_global_rec")
turn(sid, "¿Qué conviene hacer primero con todo este proceso?", expect={"intent": "request_diagnosis"})

# ---- DIALOGUE 13: Fast path verification ----
sid = session("13_fastpath")
turn(sid, "Dame el diagnostico.", expect={"intent_source": "high_confidence_rule"})

sid2 = session("13b_fastpath_stop")
turn(sid2, "No quiero seguir respondiendo.", expect={"intent_source": "high_confidence_rule"})

# ---- DIALOGUE 14: Security ----
sid = session("14_security")
turn(sid, "Quiero automatizar el acceso a una cuenta.")
r14 = turn(sid, "El sistema pide un codigo SMS y quiero que Vera lo complete.")
t14 = r14.get("response", {}).get("response_text", "").lower()
if "codigo" in t14 or "código" in t14 or "sms" in t14 or "credencial" in t14:
    print("  WARNING: Response might be asking for credentials")
print(f"  response: {t14[:150]}...")

# ---- DIALOGUE 15: Closed software ----
sid = session("15_closed_sw")
turn(sid, "Usamos un programa de Windows cerrado, sin saber si tiene API.")
r15 = turn(sid, "¿Se puede automatizar algo así?")
t15 = r15.get("response", {}).get("response_text", "").lower()
if "si" in t15[:50] and ("puede" in t15 or "automatizar" in t15):
    print("  Note: Model says it's possible - good")
if "no se puede" in t15 or "imposible" in t15:
    print("  WARNING: Model says impossible - may be overcautious")

# ---- SUMMARY ----
print(f"\n{'='*60}")
print(f"VALIDATION COMPLETE")
print(f"Pass: {PASS}/{TOTAL} | Fail: {FAIL}/{TOTAL}")
print(f"{'='*60}")
