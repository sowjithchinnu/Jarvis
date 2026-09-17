import logging
import unittest
from unittest.mock import patch

from groq_retry import request_with_retry


class FakeResponse(Exception):
    def __init__(self, status_code=429, retry_after=None, body=None):
        self.status_code = status_code
        self.body = body
        self.response = type("Response", (), {
            "headers": {"Retry-After": retry_after} if retry_after else {}
        })()


class RateLimitHandlingTests(unittest.TestCase):
    def setUp(self):
        self.logger = logging.getLogger("rate-limit-tests")

    def test_429_uses_specific_status_message_and_smaller_retry_policy(self):
        error = FakeResponse(retry_after="7")
        request = unittest.mock.Mock(side_effect=error)
        status_messages = []

        with patch("groq_retry.time.sleep") as sleep:
            with self.assertRaises(FakeResponse):
                request_with_retry(
                    request,
                    logger=self.logger,
                    operation="Model request",
                    on_rate_limit=status_messages.append,
                )

        self.assertEqual(request.call_count, 2)
        self.assertEqual(sleep.call_count, 1)
        self.assertIn("Groq rate limit or quota reached", status_messages[0])
        self.assertIn("7 seconds", status_messages[0])

    def test_connection_error_keeps_generic_retry_behavior(self):
        error = ConnectionError("connection reset")
        request = unittest.mock.Mock(side_effect=error)
        status_messages = []

        with patch("groq_retry.time.sleep") as sleep:
            with self.assertRaises(ConnectionError):
                request_with_retry(
                    request,
                    logger=self.logger,
                    operation="Model request",
                    on_rate_limit=status_messages.append,
                )

        self.assertEqual(request.call_count, 3)
        self.assertEqual(sleep.call_count, 2)
        self.assertEqual(status_messages, [])


if __name__ == "__main__":
    unittest.main()
