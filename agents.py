from __future__ import annotations
import os
from typing import Dict, Any, List, Tuple

from crewai import Agent, Task, Crew, Process

# LangChain + Gemini (Google Generative AI) LLM
import numpy as np

if not hasattr(np, "float_"):  # NumPy 2.0 removed np.float_; some deps still expect it
    np.float_ = np.float64

os.environ["GOOGLE_API_KEY"] = "AIzaSyCiPIpTscpSrssE5cNksi3qfsGv1C6SDis"

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.prompts import ChatPromptTemplate

from tools import crm_get_customer_by_phone, credit_bureau_get_score, offer_mart_get_preapproved_limit
from underwriting import evaluate_application, compute_emi
from sanction import generate_sanction_letter
from pathlib import Path

# ---------- LLM Factory ----------
def make_llm(model: str = "gemini-1.5-flash") -> ChatGoogleGenerativeAI:
    api_key = "AIzaSyCiPIpTscpSrssE5cNksi3qfsGv1C6SDis"
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY is not set.")
    os.environ["GOOGLE_API_KEY"] = api_key
    return ChatGoogleGenerativeAI(model=model, temperature=0.2, google_api_key=api_key)

# ---------- Agents ----------
def build_agents() -> Dict[str, Agent]:
    llm = make_llm()

    system_sales = (
        "You are a persuasive Sales Agent for an NBFC. "
        "Gather missing info politely (loan amount, tenure, salary if needed). "
        "Be concise and helpful."
    )
    sales_agent = Agent(
        role="Sales Agent",
        goal="Collect user needs and loan parameters, persuade to proceed",
        backstory="Top-performing digital RM with empathy and clarity.",
        llm=llm,
        verbose=False,
        allow_delegation=False,
    )

    system_verify = (
        "You are a Verification Agent using a CRM. You only return JSON with fields: "
        "{'verified': bool, 'name': str, 'address': str}. No extra text."
    )
    verify_agent = Agent(
        role="Verification Agent",
        goal="Verify KYC using CRM by phone",
        backstory="Diligent KYC specialist.",
        llm=llm,
        verbose=False,
        allow_delegation=False,
    )

    system_uw = (
        "You are an Underwriting Agent. You evaluate credit score and rules to return decisions. "
        "Return strict JSON with fields: {'decision': str, 'reason': str | null, 'emi': float | null}."
    )
    uw_agent = Agent(
        role="Underwriting Agent",
        goal="Underwrite loan per rules with credit score & pre-approved limit",
        backstory="Risk analyst focused on objective rules.",
        llm=llm,
        verbose=False,
        allow_delegation=False,
    )

    system_sanction = "You are a Sanction Letter Agent. When called, you return a short confirmation."
    sanction_agent = Agent(
        role="Sanction Agent",
        goal="Generate a sanction letter PDF",
        backstory="Back-office document generator.",
        llm=llm,
        verbose=False,
        allow_delegation=False,
    )

    return {
        "sales": sales_agent,
        "verify": verify_agent,
        "uw": uw_agent,
        "sanction": sanction_agent,
    }

# ---------- Tasks (lightweight wrappers) ----------
def task_verify(phone: str) -> Dict[str, Any]:
    cust = crm_get_customer_by_phone(phone)
    if not cust:
        return {"verified": False, "name": "", "address": ""}
    return {"verified": True, "name": cust["name"], "address": cust["address"]}

def task_underwrite(context: Dict[str, Any]) -> Dict[str, Any]:
    decision, details = evaluate_application(context)
    payload = {"decision": decision, "reason": details.get("reason"), "emi": details.get("emi")}
    return payload

def task_sanction_pdf(output_dir: Path, context: Dict[str, Any]) -> Path:
    fname = f"sanction_{context['customer_phone']}.pdf"
    out = output_dir / fname
    return generate_sanction_letter(
        out,
        customer_name=context["customer_name"],
        phone=context["customer_phone"],
        loan_amount=float(context["loan_amount"]),
        tenure_months=int(context["tenure_months"]),
        annual_rate_pct=float(context.get("annual_rate_pct", 12.0)),
        emi=float(context.get("emi", 0.0))
    )

def master_orchestrate(context: Dict[str, Any], output_dir: Path) -> Tuple[str, Dict[str, Any]]:
    """A simple master controller to route steps based on context."""
    # 1) Verify
    verify = task_verify(context["customer_phone"])
    if not verify["verified"]:
        return "KYC_FAILED", {"message": "KYC verification failed. Please check phone."}
    context["customer_name"] = verify["name"]

    # 2) Credit score & pre-approved
    score = credit_bureau_get_score(context["customer_phone"])
    pre = offer_mart_get_preapproved_limit(context["customer_phone"])
    context["credit_score"] = score
    context["pre_approved_limit"] = pre

    # 3) Underwrite
    uw = task_underwrite(context)
    decision = uw["decision"]
    context["emi"] = uw.get("emi")

    if decision == "REJECT":
        return "REJECT", {"reason": uw.get("reason")}
    if decision == "REQUIRE_SALARY":
        return "REQUIRE_SALARY", {"message": "Please upload/provide salary to proceed", "emi": uw.get("emi")}

    # 4) Sanction PDF
    pdf_path = task_sanction_pdf(output_dir, context)
    return "APPROVED", {"emi": context["emi"], "pdf_path": str(pdf_path)}
