"""Errors that the agents raise. The Response Agent turns them into a client response.

Pipeline step: infrastructure (error handling). An agent does not write a message for the user.
It raises an error that says what went wrong. One place (app/agents/response_agent.py) maps
the error to a code and a friendly text, so the texts are in one file and never leak details.
"""


class LlmError(Exception):
    """An LLM call failed. kind tells the reason, and detail is for the logs only.

    kind is one of:
        "unavailable": timeout, no connection, a 5xx answer, or a bad API key.
        "rate_limited": the provider said "too many requests" (429).
        "bad_output": the answer is not usable (not JSON, or a key is missing), even after a retry.
    """

    def __init__(self, kind: str, detail: str) -> None:
        super().__init__(f"LLM error ({kind}): {detail}")
        self.kind = kind
        self.detail = detail
