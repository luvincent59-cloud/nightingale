from common import AppTest, app


class RiskTest(AppTest):
    def test_emergency_phrases(self):
        _, _, patient, user = self.converted()
        for phrase in ("I have crushing chest pain", "difficulty breathing", "heavy bleeding", "I want to hurt myself"):
            with self.subTest(phrase=phrase):
                r = app.patient_message(user, patient["patient_id"], phrase)
                self.assertEqual(r["risk_level"], "high")
                self.assertTrue(r["escalation_required"])
                self.assertNotIn("you have", r["answer"].lower())
                self.assertIn("999", r["answer"])

    def test_ambiguous_escalates(self):
        _, _, patient, user = self.converted()
        r = app.patient_message(user, patient["patient_id"], "My chest feels funny")
        self.assertEqual(r["risk_level"], "medium")
        self.assertTrue(r["escalation_required"])
