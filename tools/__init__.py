"""
BillShield tool wrappers.

These functions are exposed as LangChain tools and are intended to be
bound to Nemotron models inside the agent implementations.

Data sources:
- Medicare rates: CMS RVU26B April 2026 via Supabase cms_pfs_rvu table
- Billing rules: Real CMS NCCI quarterly PTP + MUE data via Supabase billing_rules table
- ICD-10 validation: ICD10API.com REST endpoint
- Patient rights: DuckDuckGo web search
"""

from .icd10_lookup import validate_icd10_code
from .medicare_pricing import lookup_medicare_rate
from .web_search import search_patient_rights
from .billing_rules import check_billing_rules, get_ncci_unbundling_pairs, get_mue_limits

__all__ = [
    "validate_icd10_code",
    "lookup_medicare_rate",
    "search_patient_rights",
    "check_billing_rules",
    "get_ncci_unbundling_pairs",
    "get_mue_limits",
]
