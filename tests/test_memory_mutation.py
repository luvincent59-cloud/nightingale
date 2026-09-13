from common import AppTest, app


class MemoryTest(AppTest):
    def test_medication_correction_keeps_both_sources(self):
        _, _, patient, user = self.converted()
        first = app.patient_message(user, patient["patient_id"], "I take Advil.")
        second = app.patient_message(user, patient["patient_id"], "Actually I stopped last week.")
        meds = [x for x in app.profile(patient["patient_id"]) if x["kind"] == "medication"]
        self.assertEqual([(x["value"], x["status"]) for x in meds], [("Advil", "active"), ("Advil", "stopped")])
        self.assertEqual(meds[0]["provenance_pointer"], first["message_id"])
        self.assertEqual(meds[1]["provenance_pointer"], second["message_id"])
        self.assertEqual(meds[1]["previous_id"], meds[0]["id"])
