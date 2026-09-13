from common import AppTest, app


class AccessTest(AppTest):
    def test_patient_isolation_and_staff_queue(self):
        _, _, pa, ua = self.converted()
        lb = app.new_lead("website_widget")
        app.guest_message(lb["guest_token"], "What are your hours?")
        cb = app.request_code(lb["guest_token"], "patientb@example.invalid")["demo_code"]
        pb = app.convert(lb["guest_token"], "patientb@example.invalid", cb, "+6591234568", True)
        with self.assertRaises(PermissionError):
            app.patient_view(ua, pb["patient_id"])
        with self.assertRaises(PermissionError):
            app.escalation_view(ua)
        nurse = app.one("SELECT * FROM users WHERE id='demo-nurse'")
        self.assertEqual(app.patient_view(nurse, pa["patient_id"])["patient_id"], pa["patient_id"])
        self.assertEqual(app.patient_view(nurse, pb["patient_id"])["patient_id"], pb["patient_id"])
        self.assertIsInstance(app.escalation_view(nurse), list)

    def test_staff_role_cannot_read_patient_chat_or_clinical_queue(self):
        _, _, patient, _ = self.converted()
        staff = {"id": "front-desk", "role": "staff", "clinic_id": "demo-clinic"}
        with self.assertRaises(PermissionError):
            app.patient_view(staff, patient["patient_id"])
        with self.assertRaises(PermissionError):
            app.escalation_view(staff)

    def test_other_clinic_cannot_read_patient_or_queue(self):
        _, _, patient, _ = self.converted()
        other_nurse = {"id": "other-nurse", "role": "nurse", "clinic_id": "other-clinic"}
        with self.assertRaises(PermissionError):
            app.patient_view(other_nurse, patient["patient_id"])
        self.assertEqual(app.escalation_view(other_nurse), [])
