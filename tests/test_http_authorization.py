from common import AppTest, app
from unittest.mock import patch


class RouteHarness:
    command = "GET"

    def __init__(self, path, token):
        self.path = path
        self.token = token

    def _token(self):
        return self.token

    def _json(self, code, payload):
        self.last_response = (code, payload)
        return code, payload


class HttpAuthorizationTest(AppTest):
    def test_altering_patient_url_or_requesting_queue_is_rejected(self):
        _, _, first, _ = self.converted()
        lead = app.new_lead("website_widget")
        app.guest_message(lead["guest_token"], "What is the cost?")
        code = app.request_code(lead["guest_token"], "second@example.invalid")["demo_code"]
        second = app.convert(lead["guest_token"], "second@example.invalid", code, "+6591234568", True)

        own = RouteHarness("/api/patient/" + first["patient_id"], first["session_token"])
        self.assertEqual(app.Handler._route(own)[0], 200)
        altered = RouteHarness("/api/patient/" + second["patient_id"], first["session_token"])
        with self.assertRaises(PermissionError):
            app.Handler._route(altered)
        queue = RouteHarness("/api/staff/queue", first["session_token"])
        with self.assertRaises(PermissionError):
            app.Handler._route(queue)
        unauthenticated = RouteHarness("/api/patient/" + first["patient_id"], "")
        with self.assertRaises(PermissionError):
            app.Handler._route(unauthenticated)

    def test_unexpected_service_failure_returns_generic_error(self):
        request = RouteHarness("/api/guest/message", "")
        with patch.object(app.Handler, "_route", side_effect=RuntimeError("secret patient phrase")):
            app.Handler.do_GET(request)
        self.assertEqual(request.last_response[0], 503)
        self.assertNotIn("secret patient phrase", str(request.last_response[1]))
