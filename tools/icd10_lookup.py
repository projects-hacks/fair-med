"""
ICD-10 validation tool for BillShield.

This wraps the public ICD10API.com endpoint in a LangChain tool so that
agents (primarily the Parser agent) can validate diagnosis codes and
retrieve human-readable descriptions.
"""

from __future__ import annotations

from typing import Any, Dict

import requests
from langchain_core.tools import tool


ICD10_API_URL = "http://icd10api.com/"


@tool
def validate_icd10_code(code: str) -> Dict[str, Any]:
    """
    Validate an ICD-10 code and return structured information.

    Args:
        code: ICD-10 diagnosis code, e.g. "J06.9".

    Returns:
        A JSON-serializable dict with fields:
        - code: the code that was checked
        - name: short ICD-10 label (if available)
        - description: full description (if available)
        - valid: bool | "unknown" when API unavailable
        - raw: raw response payload for advanced agents
    """
    normalized = (code or "").strip().upper()
    if not normalized:
        return {
            "code": code,
            "name": "",
            "description": "",
            "valid": False,
            "raw": {"error": "empty code"},
        }

    try:
        resp = requests.get(
            ICD10_API_URL,
            params={"code": normalized, "r": "json"},
            timeout=10,
        )
        if resp.status_code != 200:
            return {
                "code": normalized,
                "name": "",
                "description": "",
                "valid": "unknown",
                "raw": {
                    "error": "http_error",
                    "status_code": resp.status_code,
                },
            }

        data = resp.json()
        is_true = str(data.get("Response", "")).lower() == "true"
        desc = data.get("Description") or ""
        name = data.get("Name") or ""

        return {
            "code": normalized,
            "name": name,
            "description": desc,
            "valid": bool(is_true and data.get("Valid", True)),
            "raw": data,
        }
    except Exception as exc:  # noqa: BLE001
        # Network issues should not break the entire pipeline; mark as unknown.
        return {
            "code": normalized,
            "name": "",
            "description": "",
            "valid": "unknown",
            "raw": {"error": "exception", "message": str(exc)},
        }

