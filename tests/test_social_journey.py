from common import AppTest, app


class SocialJourneyTest(AppTest):
    def test_comment_creates_one_handle_only_lead_and_portal_token(self):
        first = app.simulate_comment("Instagram_comment", "demo_prospect", "I'd like to learn more", "event_12345678")
        again = app.simulate_comment("Instagram_comment", "demo_prospect", "I'd like to learn more", "event_12345678")
        self.assertFalse(first["duplicate"])
        self.assertTrue(again["duplicate"])
        self.assertEqual(first["lead_id"], again["lead_id"])
        self.assertEqual(first["guest_token"], again["guest_token"])
        lead = app.lead_for(first["guest_token"])
        self.assertEqual(lead["source_channel"], "social_comment")
        self.assertEqual(lead["platform"], "Instagram_comment")
        self.assertEqual(lead["identity_level"], "handle")
        self.assertNotEqual(lead["handle"], "demo_prospect")
        self.assertEqual(lead["campaign_id"], "social_post_demo")
        self.assertIsNone(lead["email_enc"])
        self.assertEqual(app.one("SELECT COUNT(*) n FROM leads")["n"], 1)

    def test_comment_attribution_survives_conversion_and_handoff(self):
        social = app.simulate_comment("Tiktok_comment", "demo_prospect", "What should I ask?", "event_87654321")
        token = social["guest_token"]
        app.guest_message(token, "What happens at an egg freezing consultation?")
        code = app.request_code(token, "social@example.invalid")["demo_code"]
        patient = app.convert(token, "social@example.invalid", code, "+6591234567", True)
        user = app.auth(patient["session_token"])
        reply = app.patient_message(user, patient["patient_id"], "My chest feels funny")
        app.send_escalation(user, patient["patient_id"], reply["escalation_id"])
        nurse = app.one("SELECT * FROM users WHERE id='demo-nurse'")
        queue = app.escalation_view(nurse)
        self.assertEqual(queue[0]["id"], reply["escalation_id"])
        self.assertEqual(queue[0]["attribution"]["platform"], "Tiktok_comment")
        self.assertEqual(queue[0]["attribution"]["source_channel"], "social_comment")
