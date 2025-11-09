from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, Any, Optional

DATA_PATH = Path(__file__).parent / "sample_data.json"

def _load_data() -> Dict[str, Any]:
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

# ---- Mock CRM ----
def crm_get_customer_by_phone(phone: str) -> Optional[Dict[str, Any]]:
    db = _load_data()["customers"]
    for c in db:
        if c["phone"] == phone:
            return c
    return None

# ---- Mock Credit Bureau ----
def credit_bureau_get_score(phone: str) -> int:
    cust = crm_get_customer_by_phone(phone)
    if not cust:
        return 0
    return int(cust.get("credit_score", 0))

# ---- Mock Offer Mart ----
def offer_mart_get_preapproved_limit(phone: str) -> int:
    cust = crm_get_customer_by_phone(phone)
    if not cust:
        return 0
    return int(cust.get("pre_approved_limit", 0))

def save_session_context(context: Dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(context, indent=2), encoding="utf-8")
