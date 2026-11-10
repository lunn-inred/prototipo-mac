"""Do not use the operator's Google OAuth session in frontend tests."""

import os

os.environ["MAC_GOOGLE_CLIENT_ID"] = ""
