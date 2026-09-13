# Nightingale — first-touch-to-care prototype

This repository is a **synthetic-data evaluation prototype**, not a deployed medical service. It demonstrates an anonymous first contact, useful pre-signup answer, verified-email *demo flow*, explicit clinic-sharing consent, preserved guest-to-patient provenance, live patient profile, conservative escalation, a clinic queue, and server-side access checks. The accompanying [failure-first evaluation](EVALUATION.md) distinguishes working behavior from deployment blockers.

## Run locally

Python 3.9+ and `cryptography` are required.

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:8000`. The server binds to loopback by default. Do not expose this demo to a network or enter real patient information.

The first run generates `.local-key` with restrictive file permissions. This key and the SQLite database are ignored by Git. For a persistent deployment, supply `NIGHTINGALE_KEY` from a proper secrets manager and store the database in an encrypted managed service. Losing the key makes existing content unreadable.

## Demo walkthrough

1. Open **`http://127.0.0.1:8000/simulate`**. Choose Instagram, TikTok or Facebook, submit a synthetic comment, inspect the simulated private reply, then select its portal link. For an ad route, choose Instagram or Google ad and click the sample ad. This shows the acquisition step before the care portal.
2. Ask a general question. The answer is sourced from the small local FAQ and emits `value_event`. Try **“What is the cost?”**, **“How does egg freezing work?”**, or **“What should I ask at a consultation?”**. The cost answer states that Demo Clinic has no verified price list and gives the cost categories to request; it does not invent a clinic price.
3. Select **Share my contact details**. Enter a synthetic mobile number and email in the form that opens, use the displayed **demo** verification code, and consent to share with Demo Clinic.
   The visitor remains anonymous until choosing **Share my contact details**. That button opens a mobile-phone and email form. If a guest types a recognized name, ID, phone or email into chat before choosing it, the page warns them and the server saves only a redacted version. The original identifying text is not persisted by the application; this is stronger than deleting it after ten minutes. The pattern detector is still insufficient for real patients.
4. The patient profile and original guest message remain available. Send `I take Advil.` followed by `Actually I stopped last week.` to see provenance-preserving mutation.
5. Send `My chest feels funny`. The assistant stops general advice and offers **Send to Nurse/Clinic**. Click it to send the handoff and see the 12–18 hour response expectation; you can keep chatting. For `I have crushing chest pain`, the high-risk concern goes straight to the nurse queue with emergency guidance.
6. Open **staff demo**, sign in as demo nurse, and select **Channel & anonymous inquiries**. It shows the arrival channel and campaign after a conversation, but no pre-consent contact details or message content. **Funnel by channel** shows distinct-lead counts for arrival, chat, value, clinical intent, authentication, consent, patient creation and escalation, plus the largest adjacent-stage drop-off. **Prioritized leads** shows a transparent score and places clinical concerns first for nurse review, never sales. Staff referral creates a link whose token resumes the original LeadSession with the topic preloaded.

The social-comment simulator uses `POST /api/simulate/comment` with a synthetic event ID. Replaying the same ID returns the same LeadSession and reply link, avoiding duplicate invitations. This **does not** connect to Instagram, TikTok, or Facebook and sends no real DM. The ad routes open the portal with campaign and creative context.

## Tests

```bash
python -m unittest discover -s tests -v
```

The tests cover guest conversion, live value counts, channel openings, session expiry, simulated social-comment deduplication and attribution, escalation persistence, risk phrases, memory correction, redaction, role isolation, honest AI identity, and an Instagram-to-nurse acceptance journey. They run with temporary SQLite databases and randomly generated encryption keys. No real patient data or external API credentials are used. See [TEST_RESULTS.md](TEST_RESULTS.md) for the requirement-by-requirement results and remaining deployment gaps.

The public submission repository is [luvincent59-cloud/nightingale](https://github.com/luvincent59-cloud/nightingale). It includes a GitHub Actions workflow that installs `requirements.txt` and runs the same tests on every push and pull request. The local `origin` URL is already set. The first upload used the connected GitHub account because local Git credentials are not configured; future command-line pushes require GitHub authentication and a one-time history reconciliation. The submitted code and tests are already available at the link.

The runtime database, local encryption key, virtual environment, and Python caches are excluded from Git. A fresh checkout recreates its own demo database and key on first launch.

## What is implemented

| Area | Behavior |
| --- | --- |
| Channels | Declarative opening rules in [`channels.json`](channels.json); `staff_referral`, `social_comment`, ad clicks, lead form, reviews, and website widget are simulated. Source, campaign, creative, identity level and landing time survive conversion and escalation. |
| Nurse funnel | Per-channel distinct LeadSession counts and adjacent-stage drop-offs. Qualification is either a substantive `value_event` or `clinical_intent`, so urgent guests are not misreported as having received value. |
| Lead priority | Score = arrival recency (0–5) + channel (0–3) + consented identity (0 or 3) + stage (0–10). Anonymous concerns and contact details are hidden. Any clinical-intent or escalation record moves the lead to compassionate nurse review, ahead of ordinary follow-up; no sales contact is suggested. A guest clinical concern enters the nurse queue only after explicit identity-sharing consent. |
| Guest value | FAQ-based service answers and question-preparation prompts with stored citations; optional, user-controlled 240-character draft. A small `VALUE EVENT` badge appears on a specific, useful answer or draft and persists on resume. A generic greeting does not count. Weekly guest-conversation count is a live SQL query and displayed only at 5+. |
| Consent | Demo verification-code check for an email login identifier, phone contact point, separate timestamped marketing consent, immutable user ID, and permissioned conversion. Redacted guest messages retain their original IDs. |
| Memory | Encrypted values, active/stopped medication history, complaint/symptom extraction, source message pointers, timestamps and previous-version links. |
| Safety | Every patient turn gets a persisted `risk_assessments` record before reply: level, short reason, response confidence, assessment timestamp and action. The patient can see the safety check beside the message; the nurse's escalation record includes it. Medium/high messages stop general advice. High-risk messages are sent immediately; medium-risk and ambiguous messages show an explicit Send to Nurse/Clinic action. Emergency phrases, ambiguous symptoms, medication-change requests and requests for diagnosis are asserted in tests. |
| Handoff | Trigger message, 1–5 bullet summary, snapshot, provenance, attribution, status, and a reserved clinician-response field are persisted. The nurse queue only shows sent records; sending confirms a 12–18 hour ordinary response expectation. Patient chat remains available after send. |
| Access | Session-token checks and clinic/patient ownership checks happen in server functions. Staff queue and analytics reject patient role. |
| Privacy | Before voluntary disclosure, recognized names, ICs, phones and emails are removed **before guest-message persistence**; the visitor receives a warning. Encrypted saved messages, phone and memory values use Fernet; audit/event logs contain only IDs and allowed metadata. The nurse's anonymous-inquiry list shows channel attribution but no contact details or guest content. This demo does not send data to an external model. |

## Explicit limitations

The verification code appears in the API response, staff login is a demo shortcut, TLS is not included in the local server, the phrase-based risk gate is not clinically validated, and the regex redactor is **not sufficient to guarantee removal of all PHI**. The app removes detected identifiers before storage, so there is no stored raw copy to delete ten minutes later in new guest sessions; this cannot guarantee removal from network infrastructure, backups, or a detector miss. On startup, the app makes a best-effort pass to scrub legacy guest records. No external LLM, real scheduling feed, email sender, real social webhook/DM, marketing outreach, clinician reply workflow, production key management, or deployment pipeline is configured. The service must remain synthetic-only until those gaps are resolved and reviewed by the clinic's security, privacy, and clinical teams.

`purge_expired_guests()` deletes unconverted guest messages and LeadSessions after three days when the server starts. A production worker must run it on a schedule, and the clinic must set an approved retention schedule. Only aggregate channel metrics should be kept after deletion; this demo deletes the related event rows rather than claiming a fully designed analytics retention policy.
