from common import AppTest, app


class AnonymousNurseFlowTest(AppTest):
    def test_pre_disclosure_identifiers_are_never_persisted(self):
        lead = app.new_lead("instagram_ad_click", campaign_id="ivf_over40")
        response = app.guest_message(lead["guest_token"], "My name is John Doe and my IC is S1234567A. Call +6591234567.")
        self.assertIsNotNone(response["privacy_notice"])
        self.assertNotIn("John Doe", response["stored_message"])
        self.assertNotIn("S1234567A", response["stored_message"])
        saved = app.one("SELECT body_enc FROM messages WHERE id=?", (response["message_id"],))
        stored = app.dec(saved["body_enc"])
        self.assertNotIn("John Doe", stored)
        self.assertNotIn("S1234567A", stored)
        self.assertNotIn("+6591234567", stored)
        self.assertEqual(app.scrub_legacy_guest_messages(), 0)

    def test_legacy_guest_identifier_is_scrubbed_on_migration(self):
        lead = app.new_lead("website_widget")
        with app.connection() as db:
            db.execute("INSERT INTO messages VALUES(?,?,?,?,?,?,?,?,?)", ("old-message", lead["lead_id"], None, "guest", app.enc("My name is John Doe."), app.now(), "guest", None, None))
        self.assertEqual(app.scrub_legacy_guest_messages(), 1)
        saved = app.one("SELECT body_enc FROM messages WHERE id='old-message'")
        self.assertNotIn("John Doe", app.dec(saved["body_enc"]))

    def test_nurse_sees_channel_but_no_identity_or_guest_content(self):
        social = app.simulate_comment("Instagram_comment", "demo_prospect", "Tell me more", "event_99999999")
        app.guest_message(social["guest_token"], "What is the cost?")
        nurse = app.one("SELECT * FROM users WHERE id='demo-nurse'")
        inquiries = app.staff_inquiries(nurse)
        self.assertEqual(inquiries[0]["source_channel"], "social_comment")
        self.assertEqual(inquiries[0]["platform"], "Instagram_comment")
        self.assertEqual(inquiries[0]["identity_status"], "anonymous")
        self.assertIsNone(inquiries[0]["patient_id"])
        self.assertNotIn("handle", inquiries[0])
        self.assertNotIn("email", inquiries[0])
        self.assertNotIn("body", inquiries[0])

    def test_nurse_view_marks_identity_shared_only_after_consent(self):
        lead = app.new_lead("instagram_ad_click", campaign_id="ivf_over40")
        app.guest_message(lead["guest_token"], "What is the cost?")
        nurse = app.one("SELECT * FROM users WHERE id='demo-nurse'")
        self.assertEqual(app.staff_inquiries(nurse)[0]["identity_status"], "anonymous")
        code = app.request_code(lead["guest_token"], "optin@example.invalid")["demo_code"]
        patient = app.convert(lead["guest_token"], "optin@example.invalid", code, "+6591234567", True)
        row = app.staff_inquiries(nurse)[0]
        self.assertEqual(row["identity_status"], "shared_with_clinic")
        self.assertEqual(row["patient_id"], patient["patient_id"])

    def test_specific_answer_has_value_event_generic_reply_does_not(self):
        lead = app.new_lead("website_widget")
        generic = app.guest_message(lead["guest_token"], "hello")
        self.assertIsNone(generic["value_event"])
        useful = app.guest_message(lead["guest_token"], "What is the cost?")
        self.assertEqual(useful["value_event"], "service_answer")
        resumed = app.guest_view(lead["guest_token"])
        answer = next(m for m in resumed["messages"] if m["id"] == useful["answer_message_id"])
        self.assertEqual(answer["value_event"], "service_answer")
        self.assertTrue(resumed["has_value"])

    def test_clinical_concern_allows_disclosure_without_false_value_badge(self):
        lead = app.new_lead("website_widget")
        response = app.guest_message(lead["guest_token"], "I have crushing chest pain")
        self.assertIsNone(response["value_event"])
        self.assertTrue(response["can_disclose"])
        self.assertFalse(app.guest_view(lead["guest_token"])["has_value"])
        code = app.request_code(lead["guest_token"], "urgent@example.invalid")["demo_code"]
        self.assertEqual(len(code), 6)

    def test_lead_form_stays_anonymous_until_conversion(self):
        lead = app.new_lead("lead_form", email="notyet@example.invalid")
        saved = app.lead_for(lead["guest_token"])
        self.assertEqual(saved["identity_level"], "anonymous")
        self.assertIsNone(saved["email_enc"])
