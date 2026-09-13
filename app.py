"""Nightingale synthetic-data vertical slice. Run with `python app.py`."""
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import threading
import time
from datetime import datetime, timezone
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("NIGHTINGALE_DB", ROOT / "nightingale.db"))
CHANNELS = json.loads((ROOT / "channels.json").read_text())
GUEST_TTL_DAYS = 3
LOCK = threading.RLock()
RATE = {}
EMERGENCY = ("crushing chest pain", "difficulty breathing", "heavy bleeding", "want to hurt myself", "剧烈的胸口压榨性疼痛", "呼吸困难", "大量出血", "想伤害自己")
AMBIGUOUS = ("chest feels funny", "chest feels strange", "胸口感觉怪怪的", "not sure", "unsure", "diagnosis", "诊断", "不确定")
PERSONAL_MEDICAL = ("should i take", "should i stop", "can i stop", "what dose", "change my medication", "diagnose me", "do i have", "treatment plan for me", "该停药", "应该吃", "我是不是", "诊断我", "剂量", "用药怎么")
CLINICAL = ("pain", "bleeding", "breath", "hurt", "symptom", "疼", "痛", "出血", "呼吸", "伤害")
HFEA_EGG = "https://www.hfea.gov.uk/treatments/fertility-preservation/egg-freezing"
FAQ = [
    {"id": "faq-hours", "text": "Demo Clinic has not supplied verified opening hours. I don't want to guess. You can send the clinic your question securely; a team member can confirm hours and the best time to call.", "zh": "演示诊所尚未提供经过核实的营业时间，我不能猜测。你可以通过安全通道把问题发给诊所，请工作人员确认营业时间和适合联系的时段。", "tags": ("hour", "open", "营业", "几点", "开门", "时间"), "source_url": None, "source_span": "Demo clinic hours are not configured."},
    {"id": "faq-availability", "text": "I can't see Demo Clinic's live appointment calendar, so I can't promise a slot. The useful next step is to ask for the earliest consultation, whether virtual visits are offered, and what information is needed to book.", "zh": "我无法查看演示诊所的实时预约日历，因此不能保证有空位。你可以询问最早可预约的咨询时间、是否提供线上咨询，以及预约需要准备哪些资料。", "tags": ("availability", "available", "slot", "book", "排期", "空位", "有号", "最早"), "source_url": None, "source_span": "No live appointment feed is connected."},
    {"id": "faq-cost", "text": "I don't have Demo Clinic's verified price list. For egg freezing, ask for an itemized quote covering consultation and tests, medicines, egg collection and freezing, storage, and any later thawing or treatment. Published figures from other countries should not be treated as this clinic's price.", "zh": "我没有演示诊所经过核实的价目表。询问冻卵费用时，可以要求逐项列出咨询与检查、药物、取卵与冷冻、储存，以及未来解冻和治疗的费用。其他国家公开的价格不能当作这家诊所的报价。", "tags": ("cost", "price", "fee", "多少钱", "费用", "价格", "收费"), "source_url": HFEA_EGG, "source_span": "Make sure you get a full costed treatment plan from your clinic so you're not caught out by unexpected 'extras'."},
    {"id": "faq-success", "text": "Egg freezing may preserve an option for future fertility treatment, but it does not guarantee a baby. Outcomes depend on factors such as age when eggs are frozen and the clinic's results. Ask the clinician for recent, age-relevant outcomes and how they apply to you; I can't estimate your personal chance here.", "zh": "冻卵可以为未来的生育治疗保留一种选择，但不能保证将来一定生育。结果受冷冻时年龄等因素影响。可以请医生提供近期、与你年龄段相关的数据并解释其意义；我不能在这里估算你的个人成功率。", "tags": ("success", "chance", "rate", "guarantee", "成功率", "机会", "几率", "保证"), "source_url": HFEA_EGG, "source_span": "It’s becoming more successful but by no means a guarantee of having a baby."},
    {"id": "faq-risk", "text": "Egg freezing involves medicines and an egg-collection procedure, and there can be side effects or complications. A clinician should explain risks in the context of your health. If you are experiencing symptoms now, describe them clearly and seek human care rather than relying on this general answer.", "zh": "冻卵过程涉及用药和取卵操作，可能出现副作用或并发症。医生应结合你的健康情况解释风险。如果你现在有症状，请明确描述并寻求真人医护帮助，不要仅依赖这段一般信息。", "tags": ("risk", "safe", "painful", "hurt", "风险", "安全吗", "疼吗", "痛吗", "副作用"), "source_url": HFEA_EGG, "source_span": "some women do experience side effects from their fertility drugs"},
    {"id": "faq-process", "text": "In general, egg freezing involves an initial assessment, medicines to stimulate egg development, monitoring, egg collection, and freezing for storage. The exact schedule and suitability require a clinician's assessment. At a first visit, ask what tests are needed, how many visits to expect, and how storage works.", "zh": "一般来说，冻卵包括初步评估、促进卵子发育的药物、监测、取卵，以及冷冻储存。具体时间安排及是否适合你，需要医生评估。首次咨询可询问需要哪些检查、预计到诊次数，以及储存如何安排。", "tags": ("process", "steps", "work", "how long", "duration", "involve", "流程", "步骤", "怎么做", "多久", "过程"), "source_url": HFEA_EGG, "source_span": "What does egg freezing involve?"},
    {"id": "faq-preparation", "text": "For a first consultation, it helps to bring your main goal and questions. You could ask: What options fit my situation? What tests are needed? What are the risks and realistic outcomes? What is the full cost, including storage? A clinician can then address your personal circumstances.", "zh": "首次咨询前，可以先整理目标和问题。例如：有哪些选择？需要做什么检查？风险和实际结果如何？包括储存在内的全部费用是多少？医生才能结合你的个人情况回答。", "tags": ("prepare", "question", "consult", "visit", "appointment", "what should i ask", "准备", "问什么", "咨询", "预约"), "source_url": "https://www.hfea.gov.uk/choose-a-fertility-clinic/preparing-for-your-clinic-appointment/", "source_span": "Questions about medication, tests and wellbeing to ask your fertility clinic"},
    {"id": "faq-general", "text": "I can answer general questions about egg freezing, such as the process, risks, costs to ask about, and preparing for a consultation. What would you like to know first? For personal medical advice, I can help you send a question to the clinic.", "zh": "我可以回答关于冻卵流程、风险、费用构成和首次咨询准备的一般问题。你想先了解哪一项？如果需要针对个人情况的医疗建议，我可以帮你把问题发给诊所。", "tags": (), "source_url": HFEA_EGG, "source_span": "This page explains how the process works, its success rates and risks."},
]


def now():
    return datetime.now(timezone.utc).isoformat()


def connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=15, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA secure_delete=ON")
    return db


def init_db():
    with connection() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,email TEXT UNIQUE NOT NULL,phone_enc TEXT NOT NULL,role TEXT NOT NULL,clinic_id TEXT NOT NULL,verified_at TEXT NOT NULL,marketing_consent_at TEXT);
        CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,user_id TEXT NOT NULL,expires_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS leads(id TEXT PRIMARY KEY,clinic_id TEXT NOT NULL,source_channel TEXT NOT NULL,platform TEXT,campaign_id TEXT,creative TEXT,identity_level TEXT NOT NULL,landing_timestamp TEXT NOT NULL,topic TEXT,handle TEXT,email_enc TEXT,guest_token_hash TEXT NOT NULL,created_at REAL NOT NULL,converted_patient_id TEXT,consented_at TEXT);
        CREATE TABLE IF NOT EXISTS patients(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,lead_id TEXT NOT NULL,clinic_id TEXT NOT NULL,created_at TEXT NOT NULL,consented_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY,lead_id TEXT,patient_id TEXT,role TEXT NOT NULL,body_enc TEXT NOT NULL,created_at TEXT NOT NULL,origin TEXT NOT NULL,transcript_id TEXT,audio_id TEXT);
        CREATE TABLE IF NOT EXISTS memory(id TEXT PRIMARY KEY,patient_id TEXT NOT NULL,kind TEXT NOT NULL,value_enc TEXT NOT NULL,status TEXT NOT NULL,provenance_pointer TEXT NOT NULL,updated_at TEXT NOT NULL,previous_id TEXT);
        CREATE TABLE IF NOT EXISTS escalations(id TEXT PRIMARY KEY,patient_id TEXT NOT NULL,trigger_message_id TEXT NOT NULL,summary_enc TEXT NOT NULL,profile_snapshot_enc TEXT NOT NULL,provenance_json TEXT NOT NULL,attribution_json TEXT NOT NULL,status TEXT NOT NULL,clinician_response_enc TEXT,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,lead_id TEXT NOT NULL,event TEXT NOT NULL,metadata_json TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS auth_codes(email_hash TEXT PRIMARY KEY,code_hash TEXT NOT NULL,expires_at REAL NOT NULL,lead_id TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS audit(id TEXT PRIMARY KEY,actor_id TEXT,action TEXT NOT NULL,target_id TEXT,metadata_json TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS simulated_social_events(event_id TEXT PRIMARY KEY,platform TEXT NOT NULL,lead_id TEXT NOT NULL,guest_token_enc TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS risk_assessments(message_id TEXT PRIMARY KEY,patient_id TEXT NOT NULL,risk_level TEXT NOT NULL,risk_reason TEXT NOT NULL,confidence TEXT NOT NULL,assessed_at TEXT NOT NULL,action TEXT NOT NULL);
        """)


def _fernet():
    key = os.environ.get("NIGHTINGALE_KEY")
    if not key:
        key_path = ROOT / ".local-key"
        if not key_path.exists():
            key_path.write_bytes(Fernet.generate_key())
            key_path.chmod(0o600)
        key = key_path.read_text().strip()
    return Fernet(key.encode())


def enc(value):
    return _fernet().encrypt(str(value).encode()).decode()


def dec(value):
    return _fernet().decrypt(value.encode()).decode()


def uid():
    return secrets.token_urlsafe(16)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def redact(text):
    """Fail closed for recognized identifiers; callers never send raw text to an LLM."""
    if not isinstance(text, str):
        raise ValueError("text required")
    text = re.sub(r"\b[A-Z]\d{7}[A-Z]\b", "[REDACTED]", text, flags=re.I)
    text = re.sub(r"\b(?:\+?\d[\d\s().-]{7,}\d)\b", "[REDACTED]", text)
    text = re.sub(r"\b(?:my name is|i am|i'm|我叫|我是)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3}|[\u4e00-\u9fff]{2,4})", "[REDACTED]", text, flags=re.I)
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[REDACTED]", text)
    return text


def scrub_legacy_guest_messages():
    """Best-effort migration for older demo DBs that stored raw guest text."""
    changed = 0
    with connection() as db:
        for m in db.execute("SELECT id,body_enc FROM messages WHERE role='guest'").fetchall():
            original = dec(m["body_enc"])
            clean = redact(original)
            if clean != original:
                db.execute("UPDATE messages SET body_enc=? WHERE id=?", (enc(clean), m["id"]))
                changed += 1
    if changed:
        with connection() as db:
            db.execute("VACUUM")
    return changed


def log(action, actor_id=None, target_id=None, **metadata):
    # PHI-free allowlist. Never pass user content here.
    safe = {k: v for k, v in metadata.items() if k in {"channel", "risk", "stage", "result", "kind"}}
    with connection() as db:
        db.execute("INSERT INTO audit VALUES(?,?,?,?,?,?)", (uid(), actor_id, action, target_id, json.dumps(safe), now()))
    print(json.dumps({"event": action, "actor_id": actor_id, "target_id": target_id, **safe, "at": now()}), flush=True)


def event(lead_id, name, **metadata):
    with connection() as db:
        db.execute("INSERT INTO events VALUES(?,?,?,?,?)", (uid(), lead_id, name, json.dumps(metadata), now()))
    log("funnel_event", target_id=lead_id, stage=name)


def one(sql, args=()):
    with connection() as db:
        row = db.execute(sql, args).fetchone()
        return dict(row) if row else None


def rows(sql, args=()):
    with connection() as db:
        return [dict(r) for r in db.execute(sql, args).fetchall()]


def opening(channel, identity_level, topic, hour=None):
    period = "day" if 8 <= (datetime.now().hour if hour is None else hour) < 18 else "night"
    return CHANNELS[channel][identity_level][period].format(topic=topic or "care")


def new_lead(channel, clinic_id="demo-clinic", campaign_id=None, creative=None, topic=None, platform=None, handle=None, email=None):
    if channel not in CHANNELS:
        raise ValueError("unsupported channel")
    if clinic_id != "demo-clinic":
        raise ValueError("unknown clinic")
    if channel == "social_comment" and platform not in ("Instagram_comment", "Tiktok_comment", "Facebook_comment"):
        raise ValueError("invalid social platform")
    identity = "handle" if channel == "social_comment" else "anonymous"
    lead_id, token = uid(), uid()
    with connection() as db:
        db.execute("INSERT INTO leads VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (lead_id, clinic_id, channel, platform, campaign_id, creative, identity, now(), topic, digest(handle) if handle else None, None, digest(token), time.time(), None, None))
    event(lead_id, "visitor", channel=channel)
    return {"lead_id": lead_id, "guest_token": token, "opening": opening(channel, identity, topic), "expires_in_days": GUEST_TTL_DAYS}


def simulate_comment(platform, handle, comment, event_id):
    """Synthetic platform event; never calls a real social API or sends a real DM."""
    if platform not in ("Instagram_comment", "Tiktok_comment", "Facebook_comment"):
        raise ValueError("unsupported platform")
    if not re.fullmatch(r"[A-Za-z0-9_.]{2,40}", handle or ""):
        raise ValueError("synthetic handle required")
    if not comment or len(comment) > 240:
        raise ValueError("comment must be 1-240 characters")
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,80}", event_id or ""):
        raise ValueError("event ID required")
    with LOCK:
        prior = one("SELECT * FROM simulated_social_events WHERE event_id=?", (event_id,))
        if prior:
            if prior["platform"] != platform:
                raise ValueError("event ID collision")
            return {"lead_id": prior["lead_id"], "guest_token": dec(prior["guest_token_enc"]), "dm_text": "Thanks for your comment. Ask general questions privately in the Nightingale demo portal.", "delivery": "simulated_private_reply", "duplicate": True}
        lead = new_lead("social_comment", platform=platform, handle=handle, topic="egg freezing", campaign_id="social_post_demo", creative="egg_freezing_questions_post")
        with connection() as db:
            db.execute("INSERT INTO simulated_social_events VALUES(?,?,?,?,?)", (event_id, platform, lead["lead_id"], enc(lead["guest_token"]), now()))
    log("social_comment_simulated", target_id=lead["lead_id"], channel=platform)
    return {"lead_id": lead["lead_id"], "guest_token": lead["guest_token"], "dm_text": "Thanks for your comment. Ask general questions privately in the Nightingale demo portal.", "delivery": "simulated_private_reply", "duplicate": False}


def lead_for(token):
    row = one("SELECT * FROM leads WHERE guest_token_hash=?", (digest(token or ""),))
    if not row or time.time() - row["created_at"] > GUEST_TTL_DAYS * 86400:
        raise PermissionError("guest session missing or expired")
    return row


def faq_answer(clean):
    lower = clean.lower()
    item = next((f for f in FAQ[:-1] if any(t in lower for t in f["tags"])), FAQ[-1])
    if item["id"] == "faq-general" and ("egg freezing" in lower or "冻卵" in lower):
        item = next(f for f in FAQ if f["id"] == "faq-process")
    is_chinese = bool(re.search(r"[\u4e00-\u9fff]", clean))
    return item["zh"] if is_chinese else item["text"], {"source_id": item["id"], "span": item["source_span"], "url": item["source_url"]}


def classify(text):
    lower = text.lower()
    if any(x in lower for x in EMERGENCY):
        return "high", "emergency phrase", "high"
    if any(x in lower for x in PERSONAL_MEDICAL):
        return "medium", "personal diagnosis or treatment request", "low"
    general_education = ("egg freezing" in lower or "冻卵" in lower) and any(x in lower for x in ("how", "what", "does", "is it", "can you explain", "怎么", "什么", "会", "吗", "多久")) and not any(x in lower for x in ("i have", "i feel", "my chest", "my pain", "我有", "我现在", "我感觉"))
    if general_education:
        return "low", "general education question", "high"
    if any(x in lower for x in AMBIGUOUS) or any(x in lower for x in CLINICAL):
        return "medium", "clinical or uncertain concern", "low"
    return "low", "general information", "high"


def guest_message(token, body):
    lead = lead_for(token)
    if lead["converted_patient_id"]:
        raise PermissionError("use patient session")
    if not body or len(body) > 2000:
        raise ValueError("message must be 1-2000 characters")
    clean = redact(body)
    privacy_notice = ("You entered identifying information before choosing to share it. I removed those details from this guest message immediately; the clinic cannot see them. Use ‘Share my contact details’ only when you are ready." if clean != body else None)
    mid = uid()
    with connection() as db:
        # Never persist raw identifying text in an anonymous guest message.
        db.execute("INSERT INTO messages VALUES(?,?,?,?,?,?,?,?,?)", (mid, lead["id"], None, "guest", enc(clean), now(), "guest", None, None))
    if one("SELECT COUNT(*) AS n FROM messages WHERE lead_id=? AND role='guest'", (lead["id"],))["n"] == 1:
        event(lead["id"], "conversation_started")
    risk, _, _ = classify(clean)
    if "real doctor" in clean.lower() or "真人医生" in clean:
        answer = "I am Nightingale AI, not a doctor. Demo Clinic is the care provider. A human nurse or clinician reviews concerns you choose to send securely, and urgent concerns are routed for human review. For emergencies, call 999."
        value_kind = "trust_explanation"
        citation = None
    elif risk != "low":
        answer = "I am Nightingale AI, not a doctor. I can help you organize your concern, but I cannot assess it here. Continue securely to send it to the clinic. If this is an emergency, call 999 now."
        value_kind = None
        citation = None
    else:
        answer, citation = faq_answer(clean)
        value_kind = "service_answer" if citation["source_id"] != "faq-general" else None
    answer_id = uid()
    with connection() as db:
        db.execute("INSERT INTO messages VALUES(?,?,?,?,?,?,?,?,?)", (answer_id, lead["id"], None, "assistant", enc(answer), now(), "guest", None, None))
    if value_kind:
        event(lead["id"], "value_event", kind=value_kind, message_id=answer_id)
    elif risk != "low":
        event(lead["id"], "clinical_intent", message_id=mid, risk=risk)
    return {"message_id": mid, "answer_message_id": answer_id, "stored_message": clean, "privacy_notice": privacy_notice, "answer": answer, "value_event": value_kind, "can_disclose": bool(value_kind or risk != "low"), "citation": citation, "continue_label": "Share my contact details"}


def guest_view(token):
    lead = lead_for(token)
    if lead["converted_patient_id"]:
        raise PermissionError("use patient session")
    ms = rows("SELECT id,role,body_enc,created_at FROM messages WHERE lead_id=? AND patient_id IS NULL ORDER BY created_at", (lead["id"],))
    values = {json.loads(e["metadata_json"]).get("message_id"): json.loads(e["metadata_json"]).get("kind") for e in rows("SELECT metadata_json FROM events WHERE lead_id=? AND event='value_event'", (lead["id"],))}
    can_disclose = bool(one("SELECT 1 FROM events WHERE lead_id=? AND event IN ('value_event','clinical_intent')", (lead["id"],)))
    return {"lead_id": lead["id"], "opening": opening(lead["source_channel"], lead["identity_level"], lead["topic"]), "messages": [{"id": m["id"], "role": m["role"], "body": dec(m["body_enc"]), "created_at": m["created_at"], "value_event": values.get(m["id"])} for m in ms], "has_value": bool(values), "can_disclose": can_disclose}


def guest_draft(token):
    lead = lead_for(token)
    if lead["converted_patient_id"]:
        raise PermissionError("use patient session")
    topic = (redact(lead["topic"] or "care") or "care")[:40]
    draft = f"I'm exploring {topic}. A clinician can explain options and risks. I'd like to ask what to expect, which questions matter, and when to seek care. Thank you for helping me take this step."
    if len(draft) > 240:
        raise ValueError("draft too long")
    if not one("SELECT 1 FROM events WHERE lead_id=? AND event='conversation_started'", (lead["id"],)):
        event(lead["id"], "conversation_started")
    answer_id = uid()
    with connection() as db:
        db.execute("INSERT INTO messages VALUES(?,?,?,?,?,?,?,?,?)", (answer_id, lead["id"], None, "assistant", enc(draft), now(), "guest", None, None))
    event(lead["id"], "value_event", kind="shareable_draft", message_id=answer_id)
    return {"draft": draft, "characters": len(draft), "share_choice": "Copy only if you choose; never posted automatically."}


def request_code(token, email):
    lead = lead_for(token)
    if lead["converted_patient_id"]:
        raise ValueError("already converted")
    if not one("SELECT 1 FROM events WHERE lead_id=? AND event IN ('value_event','clinical_intent')", (lead["id"],)):
        raise ValueError("receive value or express a clinical concern before signup")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email or ""):
        raise ValueError("valid email required")
    if lead["email_enc"] and dec(lead["email_enc"]).lower() != email.lower():
        raise ValueError("use the email already provided")
    code = f"{secrets.randbelow(1000000):06d}"
    with connection() as db:
        db.execute("INSERT OR REPLACE INTO auth_codes VALUES(?,?,?,?)", (digest(email.lower()), digest(code), time.time() + 600, lead["id"]))
    event(lead["id"], "auth_started")
    # Demo mode only. Production must deliver code through an approved email provider.
    return {"demo_code": code, "expires_in_seconds": 600}


def convert(token, email, code, phone, consent, marketing_consent=False):
    lead = lead_for(token)
    if lead["converted_patient_id"]:
        raise ValueError("already converted")
    if not consent:
        raise ValueError("clinic sharing consent required")
    if not re.fullmatch(r"\+?[0-9][0-9 -]{7,17}", phone or ""):
        raise ValueError("phone required")
    check = one("SELECT * FROM auth_codes WHERE email_hash=?", (digest(email.lower()),))
    if not check or check["lead_id"] != lead["id"] or check["expires_at"] < time.time() or not hmac.compare_digest(check["code_hash"], digest(code)):
        raise PermissionError("verification failed")
    prior = one("SELECT * FROM users WHERE email=?", (email.lower(),))
    if prior and prior["role"] != "patient":
        raise PermissionError("role mismatch")
    user_id = prior["id"] if prior else uid()
    patient_id, session_token = uid(), uid()
    ts = now()
    with LOCK, connection() as db:
        if not prior:
            db.execute("INSERT INTO users VALUES(?,?,?,?,?,?,?)", (user_id, email.lower(), enc(phone), "patient", lead["clinic_id"], ts, ts if marketing_consent else None))
        db.execute("INSERT INTO patients VALUES(?,?,?,?,?,?)", (patient_id, user_id, lead["id"], lead["clinic_id"], ts, ts))
        db.execute("UPDATE leads SET converted_patient_id=?,consented_at=? WHERE id=? AND converted_patient_id IS NULL", (patient_id, ts, lead["id"]))
        db.execute("INSERT INTO sessions VALUES(?,?,?)", (digest(session_token), user_id, time.time() + 86400))
        db.execute("DELETE FROM auth_codes WHERE email_hash=?", (digest(email.lower()),))
    event(lead["id"], "consented")
    event(lead["id"], "patient_created")
    for m in rows("SELECT * FROM messages WHERE lead_id=? AND role='guest' ORDER BY created_at", (lead["id"],)):
        update_memory(patient_id, dec(m["body_enc"]), m["id"])
    clinical = rows("SELECT metadata_json FROM events WHERE lead_id=? AND event='clinical_intent' ORDER BY created_at DESC", (lead["id"],))
    escalation_id = None
    if clinical:
        details = json.loads(clinical[0]["metadata_json"])
        escalation_id = create_escalation(patient_id, details["message_id"], details.get("risk", "medium"), send_now=details.get("risk") == "high")
    log("guest_to_patient", actor_id=user_id, target_id=patient_id, result="success")
    return {"patient_id": patient_id, "session_token": session_token, "clinic_id": lead["clinic_id"], "escalation_id": escalation_id}


def auth(session_token):
    s = one("SELECT * FROM sessions WHERE token_hash=?", (digest(session_token or ""),))
    if not s or s["expires_at"] < time.time():
        raise PermissionError("login required")
    return one("SELECT * FROM users WHERE id=?", (s["user_id"],))


def patient_access(user, patient_id):
    p = one("SELECT * FROM patients WHERE id=?", (patient_id,))
    if not p or user["role"] not in ("patient", "nurse", "clinician") or (user["role"] == "patient" and p["user_id"] != user["id"]) or (user["role"] in ("nurse", "clinician") and p["clinic_id"] != user["clinic_id"]):
        log("access_denied", actor_id=user["id"], target_id=patient_id, result="denied")
        raise PermissionError("access denied")
    return p


def update_memory(patient_id, text, message_id):
    lower = text.lower()
    candidates = []
    m = re.search(r"\b(?:i take|i am taking|我在吃|我服用)\s+([A-Za-z][A-Za-z0-9-]{1,40})", text, re.I)
    if m:
        candidates.append(("medication", m.group(1), "active"))
    if "stopped last week" in lower or "上周就停" in text:
        old = one("SELECT * FROM memory WHERE patient_id=? AND kind='medication' ORDER BY updated_at DESC LIMIT 1", (patient_id,))
        if old:
            candidates.append(("medication", dec(old["value_enc"]), "stopped"))
    m = re.search(r"\b(?:allergic to|过敏于|对.+?过敏)\s+([A-Za-z][A-Za-z0-9-]{1,40})", text, re.I)
    if m:
        candidates.append(("allergy", m.group(1), "reported"))
    if any(x in lower for x in CLINICAL) or any(x in lower for x in ("egg freezing", "ivf")):
        candidates.append(("chief_complaint", redact(text)[:180], "reported"))
    symptom_words = ("pain", "bleeding", "difficulty breathing", "chest feels", "疼", "痛", "出血", "呼吸困难")
    if any(x in lower for x in symptom_words):
        timeline_match = re.search(r"(?:for|since)\s+\d+\s+(?:days?|weeks?|months?)|(?:last week|yesterday|today)|(?:持续|从).{0,12}", lower)
        value = redact(text)[:140]
        if timeline_match:
            value += " | timeline: " + timeline_match.group(0)
        candidates.append(("symptom", value, "reported"))
    for kind, value, status in candidates:
        old = one("SELECT * FROM memory WHERE patient_id=? AND kind=? ORDER BY updated_at DESC LIMIT 1", (patient_id, kind))
        with connection() as db:
            db.execute("INSERT INTO memory VALUES(?,?,?,?,?,?,?,?)", (uid(), patient_id, kind, enc(value), status, message_id, now(), old["id"] if old else None))


def profile(patient_id):
    items = rows("SELECT * FROM memory WHERE patient_id=? ORDER BY updated_at", (patient_id,))
    return [{"id": r["id"], "kind": r["kind"], "value": dec(r["value_enc"]), "status": r["status"], "provenance_pointer": r["provenance_pointer"], "updated_at": r["updated_at"], "previous_id": r["previous_id"]} for r in items]


def attribution(lead_id):
    l = one("SELECT * FROM leads WHERE id=?", (lead_id,))
    return {k: l[k] for k in ("clinic_id", "source_channel", "platform", "campaign_id", "creative", "identity_level", "landing_timestamp")}


def create_escalation(patient_id, trigger_id, risk, send_now=True):
    p = one("SELECT * FROM patients WHERE id=?", (patient_id,))
    msg = one("SELECT * FROM messages WHERE id=? AND (patient_id=? OR (lead_id=? AND origin='guest' AND role='guest'))", (trigger_id, patient_id, p["lead_id"]))
    if not msg:
        raise ValueError("trigger message missing")
    snapshot = profile(patient_id)
    summary = ["Patient requested clinical review.", "Risk: " + risk + ".", "Concern: " + redact(dec(msg["body_enc"]))[:180]]
    pointers = [trigger_id] + [x["provenance_pointer"] for x in snapshot]
    eid = uid()
    with connection() as db:
        db.execute("INSERT INTO escalations VALUES(?,?,?,?,?,?,?,?,?,?)", (eid, patient_id, trigger_id, enc(json.dumps(summary)), enc(json.dumps(snapshot)), json.dumps(pointers), json.dumps(attribution(p["lead_id"])), "new" if send_now else "pending_patient_send", None, now()))
    if send_now:
        event(p["lead_id"], "escalation_sent")
    return eid


def send_escalation(user, patient_id, escalation_id):
    p = patient_access(user, patient_id)
    if user["role"] != "patient":
        raise PermissionError("patient role required")
    escalation = one("SELECT * FROM escalations WHERE id=? AND patient_id=?", (escalation_id, patient_id))
    if not escalation:
        raise ValueError("handoff not found")
    if escalation["status"] == "pending_patient_send":
        with connection() as db:
            db.execute("UPDATE escalations SET status='new' WHERE id=? AND status='pending_patient_send'", (escalation_id,))
        event(p["lead_id"], "escalation_sent")
    return {"escalation_id": escalation_id, "status": "new" if escalation["status"] == "pending_patient_send" else escalation["status"], "expected_response": "12–18 hours"}


def patient_message(user, patient_id, body):
    p = patient_access(user, patient_id)
    if user["role"] != "patient":
        raise PermissionError("patient role required")
    if not body or len(body) > 2000:
        raise ValueError("message must be 1-2000 characters")
    clean = redact(body)
    risk, reason, confidence = classify(clean)
    mid = uid()
    assessed_at = now()
    with connection() as db:
        db.execute("INSERT INTO messages VALUES(?,?,?,?,?,?,?,?,?)", (mid, p["lead_id"], patient_id, "patient", enc(body), now(), "patient", None, None))
        db.execute("INSERT INTO risk_assessments VALUES(?,?,?,?,?,?,?)", (mid, patient_id, risk, reason, confidence, assessed_at, "education" if risk == "low" else "escalate"))
    update_memory(patient_id, body, mid)
    if risk == "low":
        if "real doctor" in clean.lower() or "真人医生" in clean:
            answer = "I am Nightingale AI, not a doctor. Demo Clinic provides the care. A nurse or clinician reviews concerns sent to the clinic; urgent or uncertain concerns are routed for human review. If this is an emergency, call 999."
            citation = None
            value_kind = "trust_explanation"
        else:
            answer, citation = faq_answer(clean)
            value_kind = "service_answer" if citation["source_id"] != "faq-general" else None
        escalation_id = None
    else:
        answer = "I cannot assess this safely in chat. " + ("I have sent this to the nurse/clinic for human review. " if risk == "high" else "Use Send to Nurse/Clinic below to request human review. ") + "If this may be an emergency, exit Nightingale and call 999 now."
        citation = None
        event(p["lead_id"], "clinical_intent", risk=risk, message_id=mid)
        escalation_id = create_escalation(patient_id, mid, risk, send_now=risk == "high")
        value_kind = None
    answer_id = uid()
    with connection() as db:
        db.execute("INSERT INTO messages VALUES(?,?,?,?,?,?,?,?,?)", (answer_id, p["lead_id"], patient_id, "assistant", enc(answer), now(), "patient", None, None))
    if value_kind:
        event(p["lead_id"], "value_event", kind=value_kind, message_id=answer_id)
    log("risk_assessed", actor_id=user["id"], target_id=mid, risk=risk)
    return {"message_id": mid, "answer_message_id": answer_id, "answer": answer, "value_event": value_kind, "risk_level": risk, "risk_reason": reason, "confidence": confidence, "risk_provenance": assessed_at, "escalation_required": risk != "low", "escalation_id": escalation_id, "escalation_status": "new" if risk == "high" else "pending_patient_send" if risk == "medium" else None, "citation": citation, "profile": profile(patient_id)}


def patient_view(user, patient_id):
    p = patient_access(user, patient_id)
    ms = rows("SELECT id,role,body_enc,created_at,origin,transcript_id,audio_id FROM messages WHERE lead_id=? ORDER BY created_at", (p["lead_id"],))
    visible = []
    for m in ms:
        body = dec(m.pop("body_enc"))
        visible.append({**m, "body": body})
    values = {json.loads(e["metadata_json"]).get("message_id"): json.loads(e["metadata_json"]).get("kind") for e in rows("SELECT metadata_json FROM events WHERE lead_id=? AND event='value_event'", (p["lead_id"],))}
    for m in visible:
        m["value_event"] = values.get(m["id"])
        if m["role"] == "patient":
            assessment = one("SELECT risk_level,risk_reason,confidence,assessed_at,action FROM risk_assessments WHERE message_id=? AND patient_id=?", (m["id"], patient_id))
            m["risk_assessment"] = assessment
    pending = rows("SELECT id,trigger_message_id,status,created_at FROM escalations WHERE patient_id=? AND status='pending_patient_send' ORDER BY created_at DESC", (patient_id,))
    return {"patient_id": patient_id, "messages": visible, "profile": profile(patient_id), "attribution": attribution(p["lead_id"]), "pending_escalations": pending}


def escalation_view(user):
    if user["role"] not in ("nurse", "clinician"):
        raise PermissionError("clinician queue only")
    es = rows("SELECT e.*,p.clinic_id FROM escalations e JOIN patients p ON e.patient_id=p.id WHERE p.clinic_id=? AND e.status!='pending_patient_send' ORDER BY e.created_at DESC", (user["clinic_id"],))
    return [{"id": e["id"], "patient_id": e["patient_id"], "trigger_message_id": e["trigger_message_id"], "triggering_message": dec(one("SELECT body_enc FROM messages WHERE id=?", (e["trigger_message_id"],))["body_enc"]), "risk_assessment": one("SELECT risk_level,risk_reason,confidence,assessed_at,action FROM risk_assessments WHERE message_id=?", (e["trigger_message_id"],)), "triage_summary": json.loads(dec(e["summary_enc"])), "profile_snapshot": json.loads(dec(e["profile_snapshot_enc"])), "provenance": json.loads(e["provenance_json"]), "attribution": json.loads(e["attribution_json"]), "status": e["status"], "clinician_response": dec(e["clinician_response_enc"]) if e["clinician_response_enc"] else None} for e in es]


def staff_referral(user, topic):
    if user["role"] not in ("staff", "nurse", "clinician"):
        raise PermissionError("staff only")
    if not topic or len(topic) > 180:
        raise ValueError("topic required")
    return new_lead("staff_referral", clinic_id=user["clinic_id"], topic=redact(topic))


def weekly_question_count(clinic_id):
    return one("SELECT COUNT(DISTINCT e.lead_id) AS n FROM events e JOIN leads l ON e.lead_id=l.id WHERE l.clinic_id=? AND e.event='conversation_started' AND e.created_at>=?", (clinic_id, datetime.fromtimestamp(time.time() - 7*86400, timezone.utc).isoformat()))["n"]


def stats(clinic_id):
    stages = ("visitor", "conversation_started", "value_event", "clinical_intent", "auth_started", "consented", "patient_created", "escalation_sent")
    grouped = {}
    for lead in rows("SELECT id,source_channel,platform FROM leads WHERE clinic_id=?", (clinic_id,)):
        channel = lead["platform"] or lead["source_channel"]
        bucket = grouped.setdefault(channel, {"channel": channel, "source_channel": lead["source_channel"], "funnel": {stage: 0 for stage in stages}, "qualified": 0})
        seen = {e["event"] for e in rows("SELECT event FROM events WHERE lead_id=?", (lead["id"],))}
        for stage in stages:
            bucket["funnel"][stage] += int(stage in seen)
        bucket["qualified"] += int("value_event" in seen or "clinical_intent" in seen)
    result = []
    for bucket in grouped.values():
        f, q = bucket["funnel"], bucket["qualified"]
        transitions = (("visitor_to_conversation", f["visitor"], f["conversation_started"]), ("conversation_to_qualified", f["conversation_started"], q), ("qualified_to_auth", q, f["auth_started"]), ("auth_to_consent", f["auth_started"], f["consented"]), ("consent_to_patient", f["consented"], f["patient_created"]))
        bucket["drop_offs"] = {name: {"left": max(0, start - finish), "rate_percent": round(100 * max(0, start - finish) / start) if start else None} for name, start, finish in transitions}
        result.append(bucket)
    return sorted(result, key=lambda x: (-x["funnel"]["visitor"], x["channel"]))


def warm_leads(user):
    if user["role"] not in ("staff", "nurse", "clinician"):
        raise PermissionError("staff only")
    out = []
    stage_points = {"visitor": 0, "conversation_started": 3, "value_event": 5, "clinical_intent": 5, "auth_started": 7, "consented": 9, "patient_created": 10, "escalation_sent": 10}
    channel_points = {"staff_referral": 3, "lead_form": 2, "social_comment": 1}
    for l in rows("SELECT * FROM leads WHERE clinic_id=?", (user["clinic_id"],)):
        events = rows("SELECT event,metadata_json FROM events WHERE lead_id=? ORDER BY created_at", (l["id"],))
        seen = {e["event"] for e in events}
        if not ("conversation_started" in seen or "clinical_intent" in seen):
            continue
        stage = next((s for s in reversed(tuple(stage_points)) if s in seen), "visitor")
        clinical = "clinical_intent" in seen or "escalation_sent" in seen
        last = one("SELECT MAX(created_at) AS at FROM messages WHERE lead_id=?", (l["id"],))["at"] or l["landing_timestamp"]
        age_days = max(0, int((time.time() - l["created_at"]) / 86400))
        points = {"recency": max(0, 5 - age_days), "channel": channel_points.get(l["source_channel"], 0), "identity": 3 if l["consented_at"] else 0, "stage": stage_points[stage]}
        score = sum(points.values())
        concern = "Hidden until consent"
        if l["consented_at"] and l["converted_patient_id"]:
            concern = next((x["value"] for x in reversed(profile(l["converted_patient_id"])) if x["kind"] == "chief_complaint"), "Not captured")
        priority = "clinical_review" if clinical else "follow_up" if l["consented_at"] else "anonymous_interest"
        contact_allowed = bool(l["consented_at"] and l["converted_patient_id"] and not clinical)
        out.append({"lead_id": l["id"], "patient_id": l["converted_patient_id"] if l["consented_at"] else None, "channel": l["platform"] or l["source_channel"], "stage": stage, "score": score, "score_breakdown": points, "priority": priority, "top_concern": concern, "contact_allowed": contact_allowed, "suggested_action": "Nurse review; never sales outreach" if clinical else "Care follow-up allowed; marketing requires separate consent" if contact_allowed else "No contact: anonymous visitor", "last_activity": last})
    return sorted(out, key=lambda x: (x["priority"] == "clinical_review", x["score"], x["last_activity"]), reverse=True)


def staff_inquiries(user):
    """Nurse-facing attribution without pre-consent identity or guest content."""
    if user["role"] not in ("staff", "nurse", "clinician"):
        raise PermissionError("staff only")
    leads = rows("SELECT id,source_channel,platform,campaign_id,creative,landing_timestamp,converted_patient_id,consented_at FROM leads WHERE clinic_id=? ORDER BY landing_timestamp DESC", (user["clinic_id"],))
    out = []
    for lead in leads:
        n = one("SELECT COUNT(*) n FROM messages WHERE lead_id=? AND role='guest'", (lead["id"],))["n"]
        if n == 0:
            continue
        out.append({"lead_id": lead["id"], "source_channel": lead["source_channel"], "platform": lead["platform"], "campaign_id": lead["campaign_id"], "creative": lead["creative"], "landing_timestamp": lead["landing_timestamp"], "guest_message_count": n, "identity_status": "shared_with_clinic" if lead["consented_at"] else "anonymous", "patient_id": lead["converted_patient_id"] if lead["consented_at"] else None})
    return out


def purge_expired_guests():
    cutoff = time.time() - GUEST_TTL_DAYS * 86400
    expired = rows("SELECT id FROM leads WHERE converted_patient_id IS NULL AND created_at<?", (cutoff,))
    with connection() as db:
        for l in expired:
            db.execute("DELETE FROM messages WHERE lead_id=?", (l["id"],))
            db.execute("DELETE FROM events WHERE lead_id=?", (l["id"],))
            db.execute("DELETE FROM leads WHERE id=?", (l["id"],))
    return len(expired)


def seed_demo_staff():
    if one("SELECT id FROM users WHERE email='nurse@demo.invalid'"):
        return
    with connection() as db:
        db.execute("INSERT INTO users VALUES(?,?,?,?,?,?,?)", ("demo-nurse", "nurse@demo.invalid", enc("00000000"), "nurse", "demo-clinic", now(), None))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Default HTTP access logs may include raw URLs and query strings.
        return

    def _json(self, code, payload):
        data = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def _body(self):
        n = int(self.headers.get("Content-Length", "0"))
        if n > 20000:
            raise ValueError("body too large")
        return json.loads(self.rfile.read(n) or b"{}")

    def _token(self):
        return self.headers.get("Authorization", "").removeprefix("Bearer ")

    def _route(self):
        path = urlparse(self.path).path
        if path == "/api/lead" and self.command == "POST":
            b = self._body()
            return self._json(200, new_lead(**{k: b.get(k) for k in ("channel", "clinic_id", "campaign_id", "creative", "topic", "platform", "handle", "email") if b.get(k) is not None}))
        if path == "/api/simulate/comment" and self.command == "POST" and os.environ.get("NIGHTINGALE_DEMO", "1") == "1":
            b = self._body(); return self._json(200, simulate_comment(b.get("platform"), b.get("handle"), b.get("comment"), b.get("event_id")))
        if path == "/api/guest/message" and self.command == "POST":
            b = self._body(); return self._json(200, guest_message(b.get("guest_token"), b.get("body")))
        if path == "/api/guest/resume" and self.command == "POST":
            b = self._body(); return self._json(200, guest_view(b.get("guest_token")))
        if path == "/api/guest/draft" and self.command == "POST":
            b = self._body(); return self._json(200, guest_draft(b.get("guest_token")))
        if path == "/api/auth/start" and self.command == "POST":
            b = self._body(); return self._json(200, request_code(b.get("guest_token"), b.get("email")))
        if path == "/api/auth/convert" and self.command == "POST":
            b = self._body(); return self._json(200, convert(b.get("guest_token"), b.get("email"), b.get("code"), b.get("phone"), b.get("consent"), b.get("marketing_consent", False)))
        if path == "/api/patient/message" and self.command == "POST":
            b = self._body(); return self._json(200, patient_message(auth(self._token()), b.get("patient_id"), b.get("body")))
        if path == "/api/patient/escalation/send" and self.command == "POST":
            b = self._body(); return self._json(200, send_escalation(auth(self._token()), b.get("patient_id"), b.get("escalation_id")))
        if path.startswith("/api/patient/") and self.command == "GET":
            return self._json(200, patient_view(auth(self._token()), path.rsplit("/", 1)[-1]))
        if path == "/api/staff/queue" and self.command == "GET":
            return self._json(200, escalation_view(auth(self._token())))
        if path == "/api/staff/leads" and self.command == "GET":
            return self._json(200, warm_leads(auth(self._token())))
        if path == "/api/staff/inquiries" and self.command == "GET":
            return self._json(200, staff_inquiries(auth(self._token())))
        if path == "/api/staff/stats" and self.command == "GET":
            u = auth(self._token());
            if u["role"] not in ("staff", "nurse", "clinician"): raise PermissionError("staff only")
            return self._json(200, stats(u["clinic_id"]))
        if path == "/api/staff/referral" and self.command == "POST":
            b = self._body(); return self._json(200, staff_referral(auth(self._token()), b.get("topic")))
        if path == "/api/value/count" and self.command == "GET":
            n = weekly_question_count("demo-clinic")
            return self._json(200, {"count": n, "message": f"{n} guest conversations started this week." if n >= 5 else None, "query": "live"})
        if path == "/api/demo/staff-login" and self.command == "POST" and os.environ.get("NIGHTINGALE_DEMO", "1") == "1":
            token = uid()
            with connection() as db: db.execute("INSERT INTO sessions VALUES(?,?,?)", (digest(token), "demo-nurse", time.time() + 3600))
            return self._json(200, {"session_token": token})
        if path in ("/", "/index.html", "/app.js", "/style.css", "/manifest.json", "/sw.js", "/simulate", "/simulator.html", "/simulator.js", "/simulator.css") and self.command == "GET":
            file = ROOT / "static" / ("index.html" if path == "/" else "simulator.html" if path == "/simulate" else path[1:])
            if not file.exists(): return self._json(404, {"error": "not found"})
            data = file.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", {".html":"text/html; charset=utf-8", ".js":"text/javascript", ".css":"text/css", ".json":"application/json"}[file.suffix])
            self.send_header("Content-Length", str(len(data)))
            self.end_headers(); self.wfile.write(data); return
        return self._json(404, {"error": "not found"})

    def do_GET(self):
        try: self._route()
        except PermissionError as e: self._json(403, {"error": str(e)})
        except (ValueError, TypeError, KeyError) as e: self._json(400, {"error": str(e)})
        except Exception: self._json(503, {"error": "Service temporarily unavailable. Please check your conversation before retrying, or contact the clinic directly."})

    def do_POST(self):
        ip = self.client_address[0]
        stamp = time.time()
        with LOCK:
            RATE[ip] = [t for t in RATE.get(ip, []) if stamp - t < 60]
            if len(RATE[ip]) >= 60: return self._json(429, {"error": "rate limited"})
            RATE[ip].append(stamp)
        try: self._route()
        except PermissionError as e: self._json(403, {"error": str(e)})
        except (ValueError, TypeError, KeyError) as e: self._json(400, {"error": str(e)})
        except Exception: self._json(503, {"error": "Service temporarily unavailable. Please check your conversation before retrying, or contact the clinic directly."})


if __name__ == "__main__":
    init_db(); scrub_legacy_guest_messages(); seed_demo_staff(); purge_expired_guests()
    host = os.environ.get("NIGHTINGALE_HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    print(f"Nightingale at http://{host}:{port}")
    ThreadingHTTPServer((host, port), Handler).serve_forever()
