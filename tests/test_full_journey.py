import json
from unittest.mock import patch

from common import AppTest, app


class FullJourneyTest(AppTest):
    def test_instagram_to_nurse_without_repeating_the_story(self):
        lead = app.new_lead("instagram_ad_click", campaign_id="ivf_over40", creative="story_a")
        guest = app.guest_message(lead["guest_token"], "What is the cost?")
        self.assertEqual(guest["value_event"], "service_answer")
        concern = app.guest_message(lead["guest_token"], "My chest feels funny")
        self.assertEqual(app.guest_view(lead["guest_token"])["messages"][0]["id"], guest["message_id"])

        code = app.request_code(lead["guest_token"], "journey@example.invalid")["demo_code"]
        with self.assertRaises(PermissionError):
            app.convert(lead["guest_token"], "journey@example.invalid", "000000" if code != "000000" else "111111", "+6591234567", True)
        with self.assertRaises(ValueError):
            app.convert(lead["guest_token"], "journey@example.invalid", code, "+6591234567", False)
        patient = app.convert(lead["guest_token"], "journey@example.invalid", code, "+6591234567", True)
        user = app.auth(patient["session_token"])
        view = app.patient_view(user, patient["patient_id"])
        self.assertIn(concern["message_id"], [m["id"] for m in view["messages"]])
        self.assertEqual(view["attribution"]["source_channel"], "instagram_ad_click")
        self.assertEqual(view["attribution"]["creative"], "story_a")

        first = app.patient_message(user, patient["patient_id"], "I take Advil.")
        second = app.patient_message(user, patient["patient_id"], "Actually I stopped last week.")
        medication = [x for x in app.profile(patient["patient_id"]) if x["kind"] == "medication"]
        self.assertEqual([x["status"] for x in medication], ["active", "stopped"])
        self.assertEqual([x["provenance_pointer"] for x in medication], [first["message_id"], second["message_id"]])

        nurse = app.one("SELECT * FROM users WHERE id='demo-nurse'")
        self.assertEqual(app.escalation_view(nurse), [])
        pending = app.patient_view(user, patient["patient_id"])["pending_escalations"]
        self.assertEqual(pending[0]["trigger_message_id"], concern["message_id"])
        app.send_escalation(user, patient["patient_id"], pending[0]["id"])
        packet = app.escalation_view(nurse)[0]
        self.assertEqual(packet["trigger_message_id"], concern["message_id"])
        self.assertEqual(packet["attribution"]["campaign_id"], "ivf_over40")
        self.assertIn(concern["message_id"], packet["provenance"])
        self.assertTrue(packet["profile_snapshot"])
        self.assertEqual(packet["status"], "new")

    def test_failed_redaction_stops_before_persistence(self):
        lead = app.new_lead("website_widget")
        with patch.object(app, "redact", side_effect=RuntimeError("redaction unavailable")):
            with self.assertRaises(RuntimeError):
                app.guest_message(lead["guest_token"], "My name is John Doe")
        self.assertEqual(app.one("SELECT COUNT(*) n FROM messages")["n"], 0)

    def test_storage_and_audit_separate_patient_text(self):
        _, _, patient, user = self.converted()
        marker = "I take SyntheticDrugXYZ"
        reply = app.patient_message(user, patient["patient_id"], marker)
        stored = app.one("SELECT body_enc,transcript_id,audio_id FROM messages WHERE id=?", (reply["message_id"],))
        self.assertNotIn(marker, stored["body_enc"])
        self.assertEqual(app.dec(stored["body_enc"]), marker)
        self.assertIsNone(stored["transcript_id"])
        self.assertIsNone(stored["audio_id"])
        self.assertNotIn(marker, json.dumps(app.rows("SELECT * FROM audit")))

    def test_no_marketing_consent_is_recorded_as_absent(self):
        _, _, patient, user = self.converted()
        record = app.one("SELECT marketing_consent_at FROM users WHERE id=?", (user["id"],))
        self.assertIsNone(record["marketing_consent_at"])
