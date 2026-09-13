from common import AppTest, app


class ValueTest(AppTest):
    def test_live_count_and_tracked_value(self):
        l = app.new_lead("website_widget")
        answer = app.guest_message(l["guest_token"], "What are your hours?")
        self.assertEqual(answer["value_event"], "service_answer")
        self.assertEqual(app.weekly_question_count("demo-clinic"), 1)
        app.guest_message(l["guest_token"], "What about consultation?")
        self.assertEqual(app.weekly_question_count("demo-clinic"), 1)
        self.assertEqual(app.one("SELECT COUNT(*) n FROM events WHERE lead_id=? AND event='value_event'", (l["lead_id"],))["n"], 2)
        self.assertEqual(answer["citation"]["span"], app.FAQ[0]["source_span"])

    def test_channel_openings_and_anonymous_lead_form(self):
        self.assertNotEqual(app.opening("website_widget", "anonymous", "egg freezing", 10), app.opening("instagram_ad_click", "anonymous", "egg freezing", 10))
        self.assertIn("anonymously", app.opening("lead_form", "anonymous", "care", 10))

    def test_shareable_draft_is_optional_short_and_tracked(self):
        l = app.new_lead("website_widget", topic="egg freezing")
        d = app.guest_draft(l["guest_token"])
        self.assertLessEqual(d["characters"], 240)
        self.assertIn("egg freezing", d["draft"])
        self.assertIn("never posted automatically", d["share_choice"])
        self.assertEqual(app.one("SELECT COUNT(*) n FROM events WHERE lead_id=? AND event='value_event'", (l["lead_id"],))["n"], 1)
