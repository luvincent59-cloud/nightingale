from common import AppTest, app


class FunnelPriorityTest(AppTest):
    def test_channel_funnel_counts_unique_leads_and_dropoff(self):
        app.new_lead("instagram_ad_click", campaign_id="ivf_over40")
        active = app.new_lead("instagram_ad_click", campaign_id="ivf_over40")
        app.guest_message(active["guest_token"], "What is the cost?")
        app.guest_message(active["guest_token"], "How does egg freezing work?")
        code = app.request_code(active["guest_token"], "funnel@example.invalid")["demo_code"]
        app.convert(active["guest_token"], "funnel@example.invalid", code, "+6591234567", True)
        row = next(r for r in app.stats("demo-clinic") if r["channel"] == "instagram_ad_click")
        f = row["funnel"]
        self.assertEqual([f[x] for x in ("visitor", "conversation_started", "value_event", "auth_started", "consented", "patient_created", "escalation_sent")], [2, 1, 1, 1, 1, 1, 0])
        self.assertEqual(row["drop_offs"]["visitor_to_conversation"], {"left": 1, "rate_percent": 50})
        self.assertEqual(row["qualified"], 1)

    def test_anonymous_lead_has_score_but_no_contact_or_concern(self):
        lead = app.new_lead("social_comment", platform="Instagram_comment", handle="demo_prospect")
        app.guest_message(lead["guest_token"], "What is the cost?")
        nurse = app.one("SELECT * FROM users WHERE id='demo-nurse'")
        row = app.warm_leads(nurse)[0]
        self.assertEqual(row["priority"], "anonymous_interest")
        self.assertEqual(row["top_concern"], "Hidden until consent")
        self.assertFalse(row["contact_allowed"])
        self.assertEqual(row["score"], sum(row["score_breakdown"].values()))

    def test_clinical_concern_is_compassion_priority_never_sales(self):
        lead = app.new_lead("instagram_ad_click")
        app.guest_message(lead["guest_token"], "I have crushing chest pain")
        nurse = app.one("SELECT * FROM users WHERE id='demo-nurse'")
        row = app.warm_leads(nurse)[0]
        self.assertEqual(row["priority"], "clinical_review")
        self.assertFalse(row["contact_allowed"])
        self.assertIn("never sales", row["suggested_action"])
        self.assertEqual(row["top_concern"], "Hidden until consent")
        f = app.stats("demo-clinic")[0]
        self.assertEqual(f["funnel"]["value_event"], 0)
        self.assertEqual(f["funnel"]["clinical_intent"], 1)
        self.assertEqual(f["qualified"], 1)

    def test_guest_clinical_intent_enters_queue_after_explicit_consent(self):
        lead = app.new_lead("instagram_ad_click", campaign_id="urgent_demo")
        concern = app.guest_message(lead["guest_token"], "I have crushing chest pain")
        nurse = app.one("SELECT * FROM users WHERE id='demo-nurse'")
        self.assertEqual(app.escalation_view(nurse), [])
        code = app.request_code(lead["guest_token"], "urgent2@example.invalid")["demo_code"]
        patient = app.convert(lead["guest_token"], "urgent2@example.invalid", code, "+6591234567", True)
        queue = app.escalation_view(nurse)
        self.assertEqual(queue[0]["patient_id"], patient["patient_id"])
        self.assertEqual(queue[0]["trigger_message_id"], concern["message_id"])
        self.assertEqual(queue[0]["attribution"]["campaign_id"], "urgent_demo")
        self.assertEqual(app.warm_leads(nurse)[0]["priority"], "clinical_review")
        self.assertFalse(app.warm_leads(nurse)[0]["contact_allowed"])

    def test_consented_nonclinical_lead_can_receive_care_followup(self):
        _, _, patient, _ = self.converted()
        nurse = app.one("SELECT * FROM users WHERE id='demo-nurse'")
        row = app.warm_leads(nurse)[0]
        self.assertEqual(row["patient_id"], patient["patient_id"])
        self.assertTrue(row["contact_allowed"])
        self.assertIn("egg freezing", row["top_concern"])
        self.assertEqual(row["score_breakdown"]["identity"], 3)

    def test_patient_escalation_overrides_followup_priority(self):
        _, _, patient, user = self.converted()
        app.patient_message(user, patient["patient_id"], "I want to hurt myself")
        nurse = app.one("SELECT * FROM users WHERE id='demo-nurse'")
        row = app.warm_leads(nurse)[0]
        self.assertEqual(row["priority"], "clinical_review")
        self.assertFalse(row["contact_allowed"])
        self.assertIn("never sales", row["suggested_action"])
        self.assertEqual(row["stage"], "escalation_sent")
