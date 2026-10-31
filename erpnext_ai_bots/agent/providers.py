"""Universal AI Provider Adapters for OpenAI and Google Gemini.

Supports:
  - OpenAI direct API Key (GPT-4o, GPT-4o-mini, etc.)
  - Custom OpenAI-compatible endpoints (Ollama, Groq, DeepSeek, vLLM)
  - Google Gemini REST streaming API (Gemini 2.0 Flash, Gemini 1.5 Pro)
"""
import json
import logging
from typing import Any, Callable, Dict, List, Optional
import requests

logger = logging.getLogger(__name__)


class OpenAICompatibleClient:
    """Client for OpenAI-compatible Chat Completions endpoints."""

    def __init__(self, api_key: str, api_endpoint: Optional[str] = None):
        self.api_key = api_key or ""
        self.endpoint = (api_endpoint or "https://api.openai.com/v1").rstrip("/") + "/chat/completions"

    def send_streaming(
        self,
        messages: List[Dict[str, Any]],
        model: str = "gpt-4o",
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        on_delta: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        """Send chat messages and stream tokens via Server-Sent Events."""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        # Convert tool schemas to standard Chat Completions format
        formatted_tools = []
        if tools:
            for t in tools:
                if t.get("type") == "function" and "parameters" in t:
                    formatted_tools.append({
                        "type": "function",
                        "function": {
                            "name": t.get("name"),
                            "description": t.get("description", ""),
                            "parameters": t.get("parameters", {}),
                        },
                    })
                elif "name" in t and "input_schema" in t:
                    # Anthropic format converter
                    formatted_tools.append({
                        "type": "function",
                        "function": {
                            "name": t["name"].replace(".", "_"),
                            "description": t.get("description", ""),
                            "parameters": t.get("input_schema", {}),
                        },
                    })
                else:
                    formatted_tools.append(t)

        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if formatted_tools:
            payload["tools"] = formatted_tools

        response = requests.post(
            self.endpoint,
            headers=headers,
            json=payload,
            stream=True,
            timeout=(10, 120),
        )

        if response.status_code != 200:
            error_msg = f"OpenAI API Error ({response.status_code}): {response.text[:300]}"
            raise RuntimeError(error_msg)

        full_text = []
        function_calls_dict: Dict[int, Dict[str, Any]] = {}
        usage = {"input_tokens": 0, "output_tokens": 0}

        for raw_line in response.iter_lines(decode_unicode=True):
            if not raw_line:
                continue
            line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else str(raw_line)
            line = line.strip()
            if not line:
                continue

            if line.startswith("data: "):
                raw_data = line[6:].strip()
                if raw_data == "[DONE]":
                    break
                try:
                    chunk = json.loads(raw_data)
                except json.JSONDecodeError:
                    continue

                if "usage" in chunk and chunk["usage"]:
                    usage["input_tokens"] = chunk["usage"].get("prompt_tokens", 0)
                    usage["output_tokens"] = chunk["usage"].get("completion_tokens", 0)

                choices = chunk.get("choices", [])
                if not choices:
                    continue

                delta = choices[0].get("delta", {})

                # Text chunk
                if "content" in delta and delta["content"]:
                    text_delta = delta["content"]
                    full_text.append(text_delta)
                    if on_delta:
                        on_delta(text_delta)

                # Tool call chunks
                if "tool_calls" in delta and delta["tool_calls"]:
                    for tc in delta["tool_calls"]:
                        idx = tc.get("index", 0)
                        if idx not in function_calls_dict:
                            function_calls_dict[idx] = {
                                "id": tc.get("id", f"call_{idx}"),
                                "call_id": tc.get("id", f"call_{idx}"),
                                "name": "",
                                "arguments": "",
                            }
                        if "id" in tc and tc["id"]:
                            function_calls_dict[idx]["id"] = tc["id"]
                            function_calls_dict[idx]["call_id"] = tc["id"]
                        fn = tc.get("function", {})
                        if "name" in fn and fn["name"]:
                            function_calls_dict[idx]["name"] += fn["name"]
                        if "arguments" in fn and fn["arguments"]:
                            function_calls_dict[idx]["arguments"] += fn["arguments"]

        return {
            "text": "".join(full_text),
            "function_calls": list(function_calls_dict.values()),
            "usage": usage,
        }


class GeminiClient:
    """Client for Google Gemini REST API with SSE streaming."""

    def __init__(self, api_key: str):
        self.api_key = api_key or ""
        self.base_url = "https://generativelanguage.googleapis.com/v1beta/models"

    def send_streaming(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: str = "",
        model: str = "gemini-2.0-flash",
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        on_delta: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        """Stream response and function calls from Google Gemini."""
        endpoint = f"{self.base_url}/{model}:streamGenerateContent?alt=sse&key={self.api_key}"

        # Convert tools to Gemini function declarations
        gemini_tools = []
        if tools:
            func_decls = []
            for t in tools:
                name = t.get("name", "")
                if "parameters" in t:
                    params = t.get("parameters", {})
                elif "input_schema" in t:
                    params = t.get("input_schema", {})
                else:
                    params = {"type": "object", "properties": {}}

                safe_name = name.replace(".", "_")
                func_decls.append({
                    "name": safe_name,
                    "description": t.get("description", ""),
                    "parameters": params,
                })
            gemini_tools.append({"functionDeclarations": func_decls})

        # Convert messages to Gemini contents format
        contents = []
        for m in messages:
            role = "user" if m.get("role") == "user" else "model"
            content = m.get("content")
            if isinstance(content, str):
                contents.append({"role": role, "parts": [{"text": content}]})
            elif isinstance(content, list):
                parts = []
                for b in content:
                    if isinstance(b, dict):
                        if b.get("type") == "text":
                            parts.append({"text": b.get("text", "")})
                        elif b.get("type") == "function_call_output":
                            parts.append({
                                "functionResponse": {
                                    "name": b.get("name", "tool_result"),
                                    "response": {"output": b.get("output", "")},
                                }
                            })
                if parts:
                    contents.append({"role": role, "parts": parts})

        payload: Dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }

        if system_prompt:
            payload["systemInstruction"] = {
                "parts": [{"text": system_prompt}]
            }

        if gemini_tools:
            payload["tools"] = gemini_tools

        response = requests.post(
            endpoint,
            headers={"Content-Type": "application/json"},
            json=payload,
            stream=True,
            timeout=(10, 120),
        )

        if response.status_code != 200:
            error_msg = f"Gemini API Error ({response.status_code}): {response.text[:300]}"
            raise RuntimeError(error_msg)

        full_text = []
        function_calls = []
        usage = {"input_tokens": 0, "output_tokens": 0}

        for raw_line in response.iter_lines(decode_unicode=True):
            if not raw_line:
                continue
            line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else str(raw_line)
            line = line.strip()
            if not line:
                continue

            if line.startswith("data: "):
                raw_data = line[6:].strip()
                try:
                    chunk = json.loads(raw_data)
                except json.JSONDecodeError:
                    continue

                if "usageMetadata" in chunk:
                    meta = chunk["usageMetadata"]
                    usage["input_tokens"] = meta.get("promptTokenCount", 0)
                    usage["output_tokens"] = meta.get("candidatesTokenCount", 0)

                candidates = chunk.get("candidates", [])
                if not candidates:
                    continue

                content_obj = candidates[0].get("content", {})
                parts = content_obj.get("parts", [])

                for part in parts:
                    if "text" in part:
                        t = part["text"]
                        full_text.append(t)
                        if on_delta:
                            on_delta(t)
                    elif "functionCall" in part:
                        fc = part["functionCall"]
                        function_calls.append({
                            "id": f"call_{len(function_calls)}",
                            "call_id": f"call_{len(function_calls)}",
                            "name": fc.get("name", ""),
                            "arguments": json.dumps(fc.get("args", {})),
                        })

        return {
            "text": "".join(full_text),
            "function_calls": function_calls,
            "usage": usage,
        }
