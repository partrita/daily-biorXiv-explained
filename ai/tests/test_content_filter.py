import sys
import unittest
from pathlib import Path
from unittest.mock import patch

AI_DIR = Path(__file__).resolve().parents[1]
if str(AI_DIR) not in sys.path:
    sys.path.insert(0, str(AI_DIR))

from content_filter import is_sensitive


class FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self.payload = payload or {}

    def json(self):
        return self.payload


class SensitiveFilterTests(unittest.TestCase):
    @patch("content_filter.requests.post", return_value=FakeResponse(429))
    def test_service_rate_limit_does_not_block_a_paper(self, _post):
        """Catches the fail-closed branch that silently removed every paper on a 429."""
        self.assertFalse(is_sensitive("A paper abstract"))

    @patch(
        "content_filter.requests.post",
        return_value=FakeResponse(200, {"sensitive": True}),
    )
    def test_confirmed_sensitive_content_is_blocked(self, _post):
        self.assertTrue(is_sensitive("A paper abstract"))


if __name__ == "__main__":
    unittest.main()
