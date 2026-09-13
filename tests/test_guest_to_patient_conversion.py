from common import AppTest, app


class ConversionTest(AppTest):
    def test_provenance_attribution_and_context(self):
        lead, guest, patient, user = self.converted(concern="I want to ask about egg freezing")
        view = app.patient_view(user, patient["patient_id"])
        self.assertEqual(view["attribution"]["source_channel"], "instagram_ad_click")
        self.assertEqual(view["attribution"]["campaign_id"], "ivf_over40")
        self.assertEqual(view["messages"][0]["id"], guest["message_id"])
        self.assertTrue(any(x["provenance_pointer"] == guest["message_id"] for x in view["profile"]))
        self.assertIn("egg freezing", view["messages"][0]["body"])

    def test_value_before_signup_and_consent(self):
        l = app.new_lead("website_widget")
        with self.assertRaises(ValueError):
            app.request_code(l["guest_token"], "a@example.invalid")
        app.guest_message(l["guest_token"], "What are your hours?")
        c = app.request_code(l["guest_token"], "a@example.invalid")["demo_code"]
        with self.assertRaises(ValueError):
            app.convert(l["guest_token"], "a@example.invalid", c, "+6591234567", False)

    def test_guest_session_recovery_window(self):
        l = app.new_lead("website_widget")
        self.assertEqual(app.lead_for(l["guest_token"])["id"], l["lead_id"])
        with app.connection() as db:
            db.execute("UPDATE leads SET created_at=? WHERE id=?", (0, l["lead_id"]))
        with self.assertRaises(PermissionError):
            app.lead_for(l["guest_token"])
