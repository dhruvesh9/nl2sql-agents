"""Test setup. The settings need some values, so we set safe test values here.

With this file, the tests also run on a fresh clone, without a .env file.
An environment variable has priority over the .env file, so the tests never use real keys.
"""

import os

import pytest

os.environ["LANGFUSE_ENABLED"] = "false"  # a test must never send data to Langfuse


@pytest.fixture(autouse=True)
def no_time_budget() -> None:
    """Every test starts without a request time budget. A test that sets one must not leak it."""
    from app import deadline

    deadline._deadline.set(None)
