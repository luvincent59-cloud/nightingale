from common import AppTest, app


class AnswerTest(AppTest):
    def test_exact_cost_question_gets_useful_truthful_answer(self):
        l = app.new_lead("instagram_ad_click", campaign_id="ivf_over40", topic="egg freezing")
        r = app.guest_message(l["guest_token"], "what is the cost?")
        self.assertIn("don't have Demo Clinic's verified price list", r["answer"])
        self.assertIn("itemized quote", r["answer"])
        self.assertIn("storage", r["answer"])
        self.assertEqual(r["citation"]["url"], app.HFEA_EGG)

    def test_general_egg_freezing_question_receives_process_answer(self):
        answer, citation = app.faq_answer("How does egg freezing work?")
        self.assertIn("egg collection", answer)
        self.assertEqual(citation["url"], app.HFEA_EGG)
        self.assertEqual(app.classify("How does egg freezing work?")[0], "low")

    def test_personal_symptom_still_escalates(self):
        self.assertEqual(app.classify("I have crushing chest pain")[0], "high")
        self.assertEqual(app.classify("I feel pain after egg freezing")[0], "medium")
