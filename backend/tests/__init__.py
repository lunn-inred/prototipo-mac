"""Isolate tests from the operator's Google OAuth configuration."""

import os

os.environ["MAC_GOOGLE_CLIENT_ID"] = ""
