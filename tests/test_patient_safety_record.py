from common import AppTest, app


class PatientSafetyRecordTest(AppTest):
    def test_high_risk_is_persisted_before_safe_reply_and_visible_to_nurse(self):
        _, _, patient, user = self.converted()
        result = app.patient_message(user, patient["patient_id"], "我有剧烈的胸口压榨性疼痛")
        self.assertEqual(result["risk_level"], "high")
        self.assertTrue(result["escalation_required"])
        self.assertNotIn("you have", result["answer"].lower())
        self.assertIn("999", result["answer"])
        record = app.one("SELECT * FROM risk_assessments WHERE message_id=?", (result["message_id"],))
        self.assertEqual(record["risk_level"], "high")
        self.assertEqual(record["action"], "escalate")
        self.assertEqual(record["assessed_at"], result["risk_provenance"])
        nurse = app.one("SELECT * FROM users WHERE id='demo-nurse'")
        self.assertEqual(app.escalation_view(nurse)[0]["risk_assessment"]["risk_level"], "high")

    def test_ambiguous_and_personal_medical_requests_stop_advice(self):
        _, _, patient, user = self.converted()
        for question in ("My chest feels funny", "Should I stop taking Advil?", "Do I have a disease?"):
            with self.subTest(question=question):
                result = app.patient_message(user, patient["patient_id"], question)
                self.assertEqual(result["risk_level"], "medium")
                self.assertTrue(result["escalation_required"])
                self.assertIn("human review", result["answer"])

    def test_low_risk_grounded_answer_and_honest_identity(self):
        _, _, patient, user = self.converted()
        answer = app.patient_message(user, patient["patient_id"], "What is the cost?")
        self.assertEqual(answer["risk_level"], "low")
        self.assertEqual(answer["citation"]["url"], app.HFEA_EGG)
        self.assertEqual(answer["value_event"], "service_answer")
        self.assertEqual(app.one("SELECT action FROM risk_assessments WHERE message_id=?", (answer["message_id"],))["action"], "education")
        trust = app.patient_message(user, patient["patient_id"], "Are you a real doctor?")
        self.assertIn("AI, not a doctor", trust["answer"])
        self.assertIn("nurse or clinician", trust["answer"])
