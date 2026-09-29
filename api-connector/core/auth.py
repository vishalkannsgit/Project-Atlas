"""
core/auth.py

Handles loading API keys and secrets SAFELY -- never hardcoded in the code.

Why this matters:
If an API key is typed directly into a .py file, anyone who sees the code
(or if it's accidentally pushed to GitHub) can steal it. Instead, secrets
live in environment variables (or a secrets vault in production), and this
file is the ONLY place that knows how to read them.

For local development: secrets come from a `.env` file (never committed to
git -- see .gitignore).
For production: the same code works if real environment variables are set
by the deployment system (Docker/Kubernetes secrets) -- no code changes
needed, which satisfies Atlas's NFR "Secure role-based administration."
"""

import os
import logging
from dotenv import load_dotenv

logger = logging.getLogger("atlas_connectors.auth")

# Loads variables from a local .env file into the environment (development
# convenience only -- in production, real env vars are already set by
# Docker/Kubernetes, so this line simply does nothing there).
load_dotenv()


class MissingSecretError(Exception):
    """Raised when a required secret/API key is not found."""
    pass


def get_secret(key: str, required: bool = True, default: str | None = None) -> str | None:
    """
    Safely read a secret/config value by name.

    Args:
        key: the environment variable name, e.g. "PUBMED_API_KEY"
        required: if True, raises an error when missing (fail loud, not silent)
        default: fallback value if not required and not found

    Returns:
        The secret value as a string, or the default if not required.
    """
    value = os.environ.get(key, default)

    if required and not value:
        logger.error(f"Missing required secret: {key}")
        raise MissingSecretError(
            f"Required secret '{key}' not found. "
            f"Set it in your .env file (local) or as an environment "
            f"variable (production)."
        )

    return value


# Convenience wrappers for the specific secrets this project needs.
# Adding a new connector's secret later just means adding one more line here.

def get_pubmed_api_key() -> str | None:
    # PubMed API technically works without a key, but a key raises your
    # rate limit significantly -- so we treat it as optional, not required.
    return get_secret("PUBMED_API_KEY", required=False)


def get_nih_api_key() -> str | None:
    return get_secret("NIH_API_KEY", required=False)


def get_atlas_api_url() -> str:
    return get_secret("ATLAS_API_URL", required=True)


def get_atlas_api_key() -> str:
    return get_secret("ATLAS_API_KEY", required=True)
