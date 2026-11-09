"""
SHEM Backend — Command ID Generator
Produces unique, human-readable relay command identifiers.
Format: SHEM-CMD-<8 uppercase hex chars>
Example: SHEM-CMD-3A7F2C1B
"""

from __future__ import annotations

import secrets


def generate_command_id() -> str:
    """
    Generate a unique relay command ID.
    Uses 4 cryptographically random bytes → 8 uppercase hex characters.
    Collision probability is negligible for the expected command volume.
    """
    return f"SHEM-CMD-{secrets.token_hex(4).upper()}"

