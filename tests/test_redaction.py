import contextlib
import io
from common import AppTest, app


class RedactionTest(AppTest):
    def test_identifiers_removed_from_model_input_and_logs(self):
        raw = "My name is John Doe and my IC is S1234567A. Call +6591234567."
        clean = app.redact(raw)
        self.assertNotIn("John Doe", clean)
        self.assertNotIn("S1234567A", clean)
        self.assertNotIn("+6591234567", clean)
        self.assertGreaterEqual(clean.count("[REDACTED]"), 2)
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            l = app.new_lead("website_widget")
            app.guest_message(l["guest_token"], raw)
        self.assertNotIn("John Doe", stream.getvalue())
        self.assertNotIn("S1234567A", stream.getvalue())
        self.assertNotIn("John Doe", str(app.rows("SELECT * FROM audit")))
