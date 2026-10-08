import io
import json
import unittest
from unittest.mock import patch

import run


class LauncherTest(unittest.TestCase):
    def response(self, installation=None, payload=None):
        response = io.BytesIO(json.dumps(payload or {"app": "money-manager", "status": "ok"}).encode())
        response.status = 200
        response.headers = {}
        if installation is not None:
            response.headers["X-Money-Manager-Installation"] = installation
        return response

    def test_reuses_this_installation(self):
        with patch("run.urllib.request.urlopen", return_value=self.response(run.installation_id())):
            self.assertTrue(run.money_manager_is_running())

    def test_does_not_reuse_an_old_money_manager(self):
        with patch("run.urllib.request.urlopen", return_value=self.response()):
            self.assertFalse(run.money_manager_is_running())

    def test_does_not_reuse_another_installation(self):
        with patch("run.urllib.request.urlopen", return_value=self.response("another-folder")):
            self.assertFalse(run.money_manager_is_running())

    def test_unavailable_server_is_not_running(self):
        with patch("run.urllib.request.urlopen", side_effect=OSError("Connection refused")):
            self.assertFalse(run.money_manager_is_running())
