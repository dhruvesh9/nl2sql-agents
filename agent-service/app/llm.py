"""LLM calls with the Together SDK.

Pipeline step: all LLM agents (steps 1, 2, 4, 5, 6) use this module.
call_llm sends one request. call_llm_json asks for JSON and parses the answer.
"""

import logging
import time
from json import loads
from typing import Any

from together import APITimeoutError, RateLimitError, Together, TogetherError

from app.config import LlmParams, settings
from app.errors import LlmError
from app.tracing import observe

logger = logging.getLogger(__name__)


def options_for(agent: str) -> dict[str, Any]:
    """Return the LLM options of one agent: its own values, and the defaults for the rest.

    agent is the agent name, for example "table_classifier". An unknown name uses only the defaults.
    The result has the keys model, temperature, reasoning_enabled, top_p, and top_k.
    Example: options_for("query_analyzer")["reasoning_enabled"] -> False
    """
    own = getattr(settings, agent, None)
    if not isinstance(own, LlmParams):
        own = LlmParams()

    def pick(own_value: Any, default_value: Any) -> Any:
        return default_value if own_value is None else own_value

    return {
        "model": pick(own.model, settings.llm_model),
        "temperature": pick(own.temperature, settings.llm_temperature),
        "reasoning_enabled": pick(own.reasoning_enabled, settings.llm_reasoning_enabled),
        "top_p": own.top_p,
        "top_k": own.top_k,
    }


def call_llm(system_prompt: str, user_message: str, agent: str = "default") -> str:
    """Send one chat request to the LLM. Return the text of the answer.

    agent is the agent name. It selects the LLM options of that agent (see options_for).
    Logs the agent, the model, the elapsed time, and the token usage. Langfuse records the same data.
    """
    options = options_for(agent)
    # The client is created here so that a missing key does not stop the app from starting.
    client = Together(
        api_key=settings.together_api_key,
        timeout=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    # We send an option only when it is set. A model can reject an option that it does not know.
    # Reasoning models "think" before they answer. That costs seconds and tokens.
    request: dict[str, Any] = {"temperature": options["temperature"]}
    if options["top_p"] is not None:
        request["top_p"] = options["top_p"]
    if options["top_k"] is not None:
        request["top_k"] = options["top_k"]
    if options["reasoning_enabled"] is not None:
        request["reasoning"] = {"enabled": options["reasoning_enabled"]}

    with observe(
        f"llm_call:{agent}",
        as_type="generation",
        model=options["model"],
        input=messages,
        metadata={"agent": agent},
        model_parameters={**request, "reasoning": options["reasoning_enabled"]},
    ) as generation:
        start = time.perf_counter()
        # Some models (for example Qwen3.8-Flash) accept only streaming requests.
        # Streaming works for all models, so we always stream and join the parts.
        parts: list[str] = []
        usage: dict[str, int] = {}
        try:
            stream = client.chat.completions.create(
                model=options["model"],
                messages=messages,
                stream=True,
                **request,
            )
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    parts.append(chunk.choices[0].delta.content)
                if getattr(chunk, "usage", None):  # the last chunk can hold the token counts
                    usage = _usage_as_dict(chunk)
        except RateLimitError as error:
            _log_failure(agent, options["model"], "rate_limited", start, error)
            raise LlmError("rate_limited", str(error)) from error
        except APITimeoutError as error:
            # A slow answer is not the same as "not available": the user can try a simpler question.
            _log_failure(agent, options["model"], "timeout", start, error)
            raise LlmError("timeout", str(error)) from error
        except TogetherError as error:
            # No connection, 5xx, bad key: for the user these are all "not available".
            _log_failure(agent, options["model"], "unavailable", start, error)
            raise LlmError("unavailable", f"{type(error).__name__}: {error}") from error
        text = "".join(parts)
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        generation.update(output=text, usage_details=usage)

    # The message stays the same for every call. The changing values are fields, so a log tool
    # can answer "how many tokens did table_classifier use today?".
    logger.info(
        "llm_call",
        extra={
            "agent": agent,
            "model": options["model"],
            "reasoning": options["reasoning_enabled"],
            "elapsed_ms": elapsed_ms,
            "input_tokens": usage.get("input", 0),
            "output_tokens": usage.get("output", 0),
            "total_tokens": usage.get("total", 0),
        },
    )
    return text


def _log_failure(agent: str, model: str, kind: str, start: float, error: Exception) -> None:
    """Log a failed LLM call with the reason. The caller then raises LlmError."""
    logger.warning(
        "llm_call failed",
        extra={
            "agent": agent,
            "model": model,
            "kind": kind,
            "elapsed_ms": int((time.perf_counter() - start) * 1000),
            "error": f"{type(error).__name__}: {error}",
        },
    )


def _usage_as_dict(response: Any) -> dict[str, int]:
    """Read the token counts from a Together response."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return {}
    return {
        "input": usage.prompt_tokens or 0,
        "output": usage.completion_tokens or 0,
        "total": usage.total_tokens or 0,
    }


def parse_json_text(text: str) -> dict[str, Any]:
    """Remove Markdown fences from the text, parse it, and return a dict.

    Raises ValueError if the text is not a JSON object. (JSONDecodeError is a kind of ValueError.)
    """
    text = text.replace("```json", "").replace("```", "").strip()

    # The LLM can write words around the JSON. Keep only the part from the first { to the last }.
    # We skip this when the text starts like JSON, so a list is not cut into an object by mistake.
    if not text.startswith(("{", "[")):
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            text = text[start : end + 1]

    data = loads(text)
    if not isinstance(data, dict):
        # ValueError (not TypeError) on purpose: callers catch one error type for every parse problem.
        raise ValueError("The answer is JSON, but it is not a JSON object")  # noqa: TRY004
    return data


def call_llm_json(system_prompt: str, user_message: str, agent: str = "default") -> dict[str, Any]:
    """Call the LLM and return the answer as a Python dict. agent selects the LLM options.

    If the answer is not valid JSON, we ask one more time. The retry message holds the bad
    answer and the parse error, so the LLM can fix its mistake. More retries cost money
    and rarely help.

    Example:
        call_llm_json("Return JSON.", 'Give {"a": 1}') -> {"a": 1}
    """
    system_prompt = system_prompt + "\n\nIMPORTANT: answer with JSON only, no other text."
    answer = call_llm(system_prompt, user_message, agent)

    try:
        return parse_json_text(answer)
    except ValueError as error:
        logger.warning("The LLM answer is not valid JSON. Retrying one time. Error: %s", error)
        retry_message = (
            f"{user_message}\n\n"
            f"Your earlier answer was not valid JSON.\n"
            f"Earlier answer:\n{answer}\n"
            f"Parse error: {error}\n"
            f"Return only the corrected JSON object."
        )

    retry_answer = call_llm(system_prompt, retry_message, agent)
    try:
        return parse_json_text(retry_answer)
    except ValueError as error:
        # Put the bad text in the message. It is the first thing you need to debug this.
        raise LlmError(
            "bad_output",
            f"The LLM did not return valid JSON after one retry. Last answer: {retry_answer!r}",
        ) from error
