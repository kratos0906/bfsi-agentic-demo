from __future__ import annotations
from typing import Dict, Any, Tuple

def compute_emi(principal: float, annual_rate_pct: float, tenure_months: int) -> float:
    r = annual_rate_pct / 12 / 100.0
    n = tenure_months
    if r == 0:
        return principal / n
    return principal * r * (1 + r)**n / ((1 + r)**n - 1)

def evaluate_application(context: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """
    Returns (decision, details)
    decision ∈ {"APPROVE_INSTANT", "REQUIRE_SALARY", "REJECT"}
    """
    phone = context["customer_phone"]
    loan_amount = float(context["loan_amount"])
    tenure = int(context["tenure_months"])
    annual_rate = float(context.get("annual_rate_pct", 12.0))
    salary = float(context.get("monthly_salary", 0))

    credit_score = int(context["credit_score"])
    pre_limit = int(context["pre_approved_limit"])

    # Problem-statement rules
    if credit_score < 700:
        return "REJECT", {"reason": "Credit score below 700"}

    if loan_amount <= pre_limit:
        return "APPROVE_INSTANT", {"emi": compute_emi(loan_amount, annual_rate, tenure)}

    if loan_amount <= 2 * pre_limit:
        # Need salary slip; approve if EMI <= 50% salary
        emi = compute_emi(loan_amount, annual_rate, tenure)
        if salary <= 0:
            return "REQUIRE_SALARY", {"reason": "Need salary slip to evaluate EMI threshold", "emi": emi}
        return ("APPROVE_INSTANT", {"emi": emi}) if emi <= 0.5 * salary else ("REJECT", {"reason": "EMI exceeds 50% of salary", "emi": emi})

    return "REJECT", {"reason": "Loan amount exceeds 2x pre-approved limit"}
