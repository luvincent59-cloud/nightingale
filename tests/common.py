import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app


class AppTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        app.DB_PATH = Path(self.tmp.name) / "test.db"
        os.environ["NIGHTINGALE_KEY"] = app.Fernet.generate_key().decode()
        app.init_db()
        app.seed_demo_staff()

    def tearDown(self):
        self.tmp.cleanup()

    def converted(self, channel="instagram_ad_click", campaign="ivf_over40", concern="I want to ask about egg freezing"):
        lead = app.new_lead(channel, campaign_id=campaign, topic="egg freezing")
        guest = app.guest_message(lead["guest_token"], concern)
        code = app.request_code(lead["guest_token"], "patient@example.invalid")["demo_code"]
        patient = app.convert(lead["guest_token"], "patient@example.invalid", code, "+6591234567", True)
        user = app.auth(patient["session_token"])
        return lead, guest, patient, user
