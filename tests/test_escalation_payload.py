from common import AppTest, app


class EscalationTest(AppTest):
    def test_complete_persisted_payload(self):
        lead, guest, patient, user = self.converted()
        result = app.patient_message(user, patient["patient_id"], "My chest feels funny")
        self.assertTrue(result["escalation_required"])
        self.assertEqual(result["escalation_status"], "pending_patient_send")
        nurse = app.one("SELECT * FROM users WHERE id='demo-nurse'")
        self.assertEqual(app.escalation_view(nurse), [])
        self.assertEqual(app.patient_view(user, patient["patient_id"])["pending_escalations"][0]["id"], result["escalation_id"])
        sent = app.send_escalation(user, patient["patient_id"], result["escalation_id"])
        self.assertEqual(sent["expected_response"], "12–18 hours")
        app.send_escalation(user, patient["patient_id"], result["escalation_id"])
        self.assertEqual(app.one("SELECT COUNT(*) n FROM events WHERE lead_id=? AND event='escalation_sent'", (lead["lead_id"],))["n"], 1)
        queue = app.escalation_view(nurse)
        self.assertEqual(queue[0]["trigger_message_id"], result["message_id"])
        self.assertIn("chest feels funny", queue[0]["triggering_message"].lower())
        self.assertGreaterEqual(len(queue[0]["triage_summary"]), 1)
        self.assertLessEqual(len(queue[0]["triage_summary"]), 5)
        self.assertTrue(queue[0]["profile_snapshot"])
        self.assertIn(guest["message_id"], queue[0]["provenance"])
        self.assertEqual(queue[0]["attribution"]["campaign_id"], "ivf_over40")
        self.assertEqual(queue[0]["status"], "new")
        self.assertIsNone(queue[0]["clinician_response"])
        app.patient_message(user, patient["patient_id"], "What is the cost?")
        self.assertGreater(len(app.patient_view(user, patient["patient_id"])["messages"]), 0)
