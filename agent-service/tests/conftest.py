"""Test setup. The settings need some values, so we set safe test values here.

With this file, the tests also run on a fresh clone, without a .env file.
An environment variable has priority over the .env file, so the tests never use real keys.
"""

import os

os.environ.setdefault("DB_SERVICE_API_KEY", "test-key")
os.environ.setdefault("KNOWLEDGE_SERVICE_API_KEY", "test-key")
os.environ["LANGFUSE_ENABLED"] = "false"  # a test must never send data to Langfuse
