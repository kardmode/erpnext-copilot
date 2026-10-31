"""Tests for Universal AI Provider Adapters (OpenAI direct, Custom endpoints, Google Gemini)."""
import unittest
import sys
import os
import json
from unittest.mock import MagicMock, patch

app_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if app_root not in sys.path:
    sys.path.insert(0, app_root)

from erpnext_ai_bots.agent.providers import OpenAICompatibleClient, GeminiClient


class TestProviders(unittest.TestCase):

    def test_openai_client_endpoint_formatting(self):
        """Endpoints should format properly with chat/completions appended."""
        client_default = OpenAICompatibleClient(api_key="sk-test")
        self.assertEqual(client_default.endpoint, "https://api.openai.com/v1/chat/completions")

        client_custom = OpenAICompatibleClient(api_key="sk-test", api_endpoint="http://localhost:11434/v1/")
        self.assertEqual(client_custom.endpoint, "http://localhost:11434/v1/chat/completions")

    @patch("requests.post")
    def test_openai_streaming_parser(self, mock_post):
        """Verify OpenAI SSE chunk consumption, token streaming, and function call assembly."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_lines.return_value = [
            b'data: {"choices": [{"delta": {"content": "Hello "}}]}',
            b'data: {"choices": [{"delta": {"content": "world!"}}]}',
            b'data: {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call_123", "function": {"name": "accounting_get_bank_balances", "arguments": "{\\"company\\": \\"Acme\\"}"}}]}}]}',
            b'data: {"usage": {"prompt_tokens": 100, "completion_tokens": 20}}',
            b'data: [DONE]',
        ]
        mock_post.return_value = mock_response

        deltas = []
        client = OpenAICompatibleClient(api_key="sk-test")
        result = client.send_streaming(
            messages=[{"role": "user", "content": "Hello"}],
            on_delta=lambda d: deltas.append(d),
        )

        self.assertEqual("".join(deltas), "Hello world!")
        self.assertEqual(result["text"], "Hello world!")
        self.assertEqual(len(result["function_calls"]), 1)
        self.assertEqual(result["function_calls"][0]["name"], "accounting_get_bank_balances")
        self.assertEqual(result["usage"]["input_tokens"], 100)
        self.assertEqual(result["usage"]["output_tokens"], 20)

    @patch("requests.post")
    def test_gemini_streaming_parser(self, mock_post):
        """Verify Google Gemini SSE stream parsing and functionCall extraction."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_lines.return_value = [
            b'data: {"candidates": [{"content": {"parts": [{"text": "Checking "}]}}]}',
            b'data: {"candidates": [{"content": {"parts": [{"text": "balances..."}]}}]}',
            b'data: {"candidates": [{"content": {"parts": [{"functionCall": {"name": "accounting_get_bank_balances", "args": {"company": "Acme"}}}]}}], "usageMetadata": {"promptTokenCount": 85, "candidatesTokenCount": 15}}',
        ]
        mock_post.return_value = mock_response

        deltas = []
        client = GeminiClient(api_key="AIzaSyTestKey")
        result = client.send_streaming(
            messages=[{"role": "user", "content": "What is our balance?"}],
            system_prompt="You are an ERPNext assistant.",
            tools=[{"name": "accounting.get_bank_balances", "input_schema": {"type": "object"}}],
            on_delta=lambda d: deltas.append(d),
        )

        self.assertEqual("".join(deltas), "Checking balances...")
        self.assertEqual(result["text"], "Checking balances...")
        self.assertEqual(len(result["function_calls"]), 1)
        self.assertEqual(result["function_calls"][0]["name"], "accounting_get_bank_balances")
        self.assertIn('"company": "Acme"', result["function_calls"][0]["arguments"])
        self.assertEqual(result["usage"]["input_tokens"], 85)
        self.assertEqual(result["usage"]["output_tokens"], 15)


if __name__ == "__main__":
    unittest.main()
