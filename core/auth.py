"""
OAuth Token Management for YokeFlow
====================================

This module handles automatic OAuth token refresh by reading from Claude's
credentials file (~/.claude/.credentials.json) instead of relying on static
environment variables.

The token in .env can become stale because Claude Code automatically refreshes
tokens, but YokeFlow's .env file doesn't get updated. This module solves that
by reading the fresh token directly from Claude's credentials file.
"""

import json
import os
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def get_claude_credentials_path() -> Path:
    """
    Get the path to Claude's credentials file.

    Returns:
        Path to ~/.claude/.credentials.json
    """
    # On Windows, ~ expands to C:/Users/<username>
    # On Linux/Mac, ~ expands to /home/<username> or /Users/<username>
    return Path.home() / ".claude" / ".credentials.json"


def get_oauth_token_from_credentials() -> Optional[str]:
    """
    Read OAuth token from Claude's credentials file.

    This is the preferred source as Claude Code automatically refreshes
    this token, keeping it always valid.

    Returns:
        OAuth access token if found and valid, None otherwise
    """
    credentials_path = get_claude_credentials_path()

    if not credentials_path.exists():
        logger.debug(f"Claude credentials file not found at {credentials_path}")
        return None

    try:
        with open(credentials_path, 'r') as f:
            credentials = json.load(f)

        # Extract token from the nested structure
        oauth_data = credentials.get("claudeAiOauth", {})
        access_token = oauth_data.get("accessToken")

        if access_token:
            # Log token prefix for debugging (first 30 chars only for security)
            token_prefix = access_token[:30] if len(access_token) > 30 else access_token
            logger.info(f"[AUTH] Loaded fresh OAuth token from credentials file: {token_prefix}...")
            return access_token
        else:
            logger.warning("Claude credentials file exists but contains no accessToken")
            return None

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Claude credentials file: {e}")
        return None
    except Exception as e:
        logger.error(f"Error reading Claude credentials file: {e}")
        return None


def get_oauth_token() -> Optional[str]:
    """
    Get OAuth token with automatic refresh from Claude's credentials.

    Priority order:
    1. Fresh token from ~/.claude/.credentials.json (preferred - auto-refreshed by Claude Code)
    2. Fallback to CLAUDE_CODE_OAUTH_TOKEN environment variable

    Returns:
        OAuth access token if available, None otherwise
    """
    # First, try to get fresh token from Claude's credentials file
    token = get_oauth_token_from_credentials()

    if token:
        return token

    # Fallback to environment variable (may be stale)
    env_token = os.getenv("CLAUDE_CODE_OAUTH_TOKEN")

    if env_token:
        logger.info("[AUTH] Using OAuth token from environment variable (credentials file not available)")
        return env_token

    logger.warning("[AUTH] No OAuth token found in credentials file or environment")
    return None


def update_env_token_if_needed() -> bool:
    """
    Update the environment variable with fresh token from credentials file.

    This ensures that any subprocess or library that reads from os.environ
    will get the fresh token.

    Returns:
        True if token was updated, False otherwise
    """
    fresh_token = get_oauth_token_from_credentials()

    if fresh_token:
        current_token = os.getenv("CLAUDE_CODE_OAUTH_TOKEN")

        if current_token != fresh_token:
            os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = fresh_token
            logger.info("[AUTH] Updated environment with fresh OAuth token from credentials file")
            return True
        else:
            logger.debug("[AUTH] Environment token already matches credentials file")

    return False
