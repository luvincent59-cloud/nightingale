# Requirements 10–11: repeatable acceptance check

Run from this repository with the bundled Python environment or an environment with `cryptography` installed:

```sh
python -m unittest discover -s tests -q
```

Last local run (2026-09-13): **42 tests passed**. The tests use temporary SQLite databases, generated encryption keys, and synthetic `.invalid` contact addresses. No external model, social network, or clinic service is contacted.

| Check | Reproducible evidence | Result and boundary |
| --- | --- | --- |
| Instagram → anonymous answer → consent → patient → nurse | `test_full_journey.py` | Pass: original message ID, campaign/creative, and profile provenance survive. A medium-risk handoff stays out of the nurse queue until the patient sends it. |
| Patient A changes URL to patient B, or requests nurse queue | `test_http_authorization.py`, `test_access_control.py` | Pass: the server route rejects the altered URL and queue request. The patient cannot bypass this by changing UI controls. |
| Staff/nurse/clinician scope | `test_access_control.py` | Pass for the implemented roles: reception `staff` cannot open patient chat or clinical queue; nurse/clinician access is limited to their clinic. Demo nurse login is insecure and is not production authorization. |
| Specific answers, live counts, channel attribution, resumed guest session, referral, scoring | `test_answers.py`, `test_value_events.py`, `test_anonymous_nurse_flow.py`, `test_social_journey.py`, `test_funnel_and_priorities.py` | Pass within the local simulator. Statistics count recorded LeadSessions, not unique people. |
| Dangerous/ambiguous symptoms, clinician packet, medication correction, honest AI identity | `test_risk_escalation.py`, `test_patient_safety_record.py`, `test_escalation_payload.py`, `test_memory_mutation.py`, `test_trust.py` | Pass for tested phrases; rule-based risk detection has not had clinical validation. |
| Identifiers, storage, audit, redaction failure | `test_redaction.py`, `test_full_journey.py` | Recognized names/IDs/phones are removed from guest messages; patient message bodies and phone numbers are encrypted; audit entries do not contain tested patient text. If redaction raises, the guest message is not stored and the HTTP layer returns a generic service error. This does **not** prove that all identifiers are recognized. |
| Marketing without separate consent | `test_full_journey.py` | The absence of marketing consent is stored. No marketing-send feature exists, so actual outbound suppression cannot be tested yet. |
| Voice-ready fields | `test_full_journey.py` | `messages.transcript_id` and `messages.audio_id` exist and remain empty for text chat. |
| Mobile | `static/index.html`, `static/style.css` | Viewport meta tag and a narrow-screen layout are present. Physical-device interaction and accessibility testing remain open. |

**Not passed as a deployment requirement:** The demo is served over local HTTP, so transport encryption is not demonstrated. SQLite does not use whole-database encryption; message bodies, phone numbers and handoff summaries are encrypted at the application layer, but user email and some acquisition metadata remain plaintext. There is no external AI call, so timeout behavior is a documented fallback policy rather than a tested live integration. Verification codes are displayed in demo mode; login-provider outage and delivery cannot be tested as a real service. There is no real clinic queue alert, acknowledgement SLA, or actual 12–18 hour staffing guarantee. These gaps prevent a real-patient rollout.
