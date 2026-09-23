"""Offline focused tests for the direct single-shot C adapter (no network)."""
import hashlib
import json
import unittest

from notes.y4.c_arm_direct_adapter import (
    DirectAdapterError, build_request, invoke, resolve_slug,
)

SLUG = "opencode-go/deepseek-v4.1-flash"
PACKAGE = b'{"schema_version":"y4-public.v3","payload":"test"}'


def ok_transport(content="{}"):
    calls = []

    def transport(request_bytes, api_key, session_id, timeout_s):
        calls.append((request_bytes, api_key, session_id, timeout_s))
        body = json.dumps({
            "id": "resp_1",
            "choices": [{"message": {"role": "assistant", "content": content},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 2,
                      "completion_tokens_details": {"reasoning_tokens": 1}},
        }).encode("utf-8")
        return 200, body
    return transport, calls


class DirectAdapterTests(unittest.TestCase):
    def test_slug_identity_fail_closed(self):
        self.assertEqual(resolve_slug(SLUG), "DeepSeek V4.1 Flash")
        for bad in ("opencode-go/deepseek-v4-flash", "opencode-go/deepseek-v4-pro",
                    "opencode/deepseek-v4.1-flash"):
            with self.subTest(slug=bad), self.assertRaises(DirectAdapterError):
                resolve_slug(bad)

    def test_request_is_package_only_with_caller_budget(self):
        request = json.loads(build_request(SLUG, PACKAGE, 65536))
        self.assertEqual(request["model"], "deepseek-v4.1-flash")
        self.assertEqual(len(request["messages"]), 1)
        self.assertEqual(request["messages"][0]["content"], PACKAGE.decode("utf-8"))
        self.assertEqual(request["max_tokens"], 65536)
        self.assertFalse(request["stream"])
        self.assertNotIn("tools", request)

    def test_exactly_one_call_and_exact_hashes(self):
        transport, calls = ok_transport(content='{"proposal": true}')
        response = invoke(PACKAGE, SLUG, "key", 65536, "sess-1", transport=transport)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][2], "sess-1")
        self.assertEqual(calls[0][3], 120.0)
        receipt = response.to_receipt()
        self.assertEqual(receipt["tool_calls"], [])
        self.assertEqual(receipt["agent_steps"], 0)
        self.assertEqual(receipt["finish_reason"], "stop")
        self.assertEqual(receipt["usage"]["completion_tokens_details"]["reasoning_tokens"], 1)
        self.assertEqual(receipt["content_sha256"],
                         hashlib.sha256(response.content_bytes).hexdigest())
        self.assertEqual(receipt["request_body_sha256"],
                         hashlib.sha256(response.request_bytes).hexdigest())

    def test_failure_is_one_call_no_retry(self):
        calls = []

        def failing(request_bytes, api_key, session_id, timeout_s):
            calls.append(1)
            raise OSError("network down")

        with self.assertRaises(DirectAdapterError):
            invoke(PACKAGE, SLUG, "key", 65536, "sess-1", transport=failing)
        self.assertEqual(len(calls), 1)

    def test_missing_credential_fails_before_call(self):
        calls = []

        def never(request_bytes, api_key, session_id, timeout_s):
            calls.append(1)
            return 200, b"{}"

        with self.assertRaises(DirectAdapterError):
            invoke(PACKAGE, SLUG, "", 16384, "sess-1", transport=never)
        self.assertEqual(calls, [])

    def test_http_error_and_bad_budget_fail_closed(self):
        def http_500(request_bytes, api_key, session_id, timeout_s):
            return 500, b"boom"

        with self.assertRaises(DirectAdapterError):
            invoke(PACKAGE, SLUG, "key", 65536, "sess-1", transport=http_500)
        with self.assertRaises(DirectAdapterError):
            build_request(SLUG, PACKAGE, 0)


if __name__ == "__main__":
    unittest.main()
