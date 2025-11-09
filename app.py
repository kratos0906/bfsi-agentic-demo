from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Dict, Any

import streamlit as st

from agents import master_orchestrate, task_verify
from tools import crm_get_customer_by_phone

# ---- Constants & Paths ----
DEFAULT_RATE = 12.0
MIN_LOAN = 10_000
MIN_TENURE = 6
MAX_TENURE = 84
OUTPUT_DIR = Path("outputs")
PHONE_PROMPTS = [
    "🤖 **Master Agent:** I'll need the mobile number linked to your account so I can pull up the right details.",
    "🤖 **Master Agent:** As soon as I have your registered 10-digit number, I can bring up your loan options.",
    "🤖 **Master Agent:** Whenever you're ready, pop in the mobile number you use with us and I'll take it from there.",
]

# ---- Streamlit Page Config ----
st.set_page_config(
    page_title="NBFC Agentic AI (CrewAI + Gemini)",
    page_icon="💬",
    layout="centered",
)

st.title("💬 NBFC Agentic AI Demo")
st.caption("Agentic Master Controller orchestrating Sales, Verification, Underwriting & Sanction workers.")

with st.expander("🔧 How this demo works", expanded=False):
    st.markdown(
        """
        1. **Master Agent** drives the conversation and decides which specialist agent to engage.
        2. **Verification Agent** confirms customer identity from a mock CRM.
        3. **Underwriting Agent** gathers credit score, applies policy rules, and may ask for salary.
        4. **Sanction Agent** prepares a sanction letter PDF when the loan is approved.

        Provide answers just as you would in a chat. Type `restart` any time to launch a fresh application.
        """
    )


# ---- Helpers ----
def reset_conversation() -> None:
    """Start or restart the chat flow."""
    st.session_state.chat_history = [
        {
            "role": "assistant",
            "content": (
                "🤖 **Master Agent:** Hi there! I'm your personal loan concierge. "
                "I'll keep things friendly while looping in my specialist teammates when needed. "
                "To pull up your profile, could you share the mobile number you use with us?"
            ),
        }
    ]
    st.session_state.conversation_state = "COLLECT_PHONE"
    st.session_state.collected_data: Dict[str, Any] = {
        "annual_rate_pct": DEFAULT_RATE,
        "customer_profile": None,
    }
    st.session_state.latest_status = None
    st.session_state.latest_payload = None
    st.session_state.phone_retry_count = 0


def add_assistant_message(message: str) -> None:
    st.session_state.chat_history.append({"role": "assistant", "content": message})


def trigger_rerun() -> None:
    """Handle Streamlit rerun across API versions."""
    if hasattr(st, "experimental_rerun"):
        st.experimental_rerun()
    else:
        st.rerun()


def format_currency(amount: float | int | None) -> str:
    if amount is None:
        return "₹0"
    return f"₹{amount:,.0f}"


def next_phone_prompt() -> str:
    idx = st.session_state.get("phone_retry_count", 0)
    message = PHONE_PROMPTS[idx % len(PHONE_PROMPTS)]
    st.session_state.phone_retry_count = idx + 1
    return message


def extract_number(text: str) -> float | None:
    matches = re.findall(r"\d[\d,\.]*", text)
    if not matches:
        return None
    raw = matches[0].replace(",", "")
    try:
        return float(raw)
    except ValueError:
        return None


def parse_tenure(text: str) -> int | None:
    number = extract_number(text)
    if number is None:
        return None
    text_lower = text.lower()
    if "year" in text_lower:
        months = int(round(number * 12))
    else:
        months = int(round(number))
    return months if months > 0 else None


def is_positive_response(text: str) -> bool:
    words = set(re.sub(r"[^a-z\s]", " ", text.lower()).split())
    return bool(words & {"yes", "y", "sure", "okay", "ok", "yeah", "yup", "proceed", "go", "affirmative"})


def is_negative_response(text: str) -> bool:
    words = set(re.sub(r"[^a-z\s]", " ", text.lower()).split())
    return bool(words & {"no", "n", "not", "later", "skip", "nah"})


def is_greeting(text: str) -> bool:
    words = set(re.sub(r"[^a-z\s]", " ", text.lower()).split())
    return bool(words & {"hi", "hello", "hey", "heya", "hiya", "greetings"})


def wants_lower_rate(text: str) -> bool:
    lowered = text.lower()
    return (
        any(token in lowered for token in {"rate", "interest", "roi", "percentage"})
        and any(token in lowered for token in {"lower", "less", "reduce", "drop", "discount", "better"})
    )


def wants_amount_adjustment(text: str) -> bool:
    lowered = text.lower()
    if extract_number(text) is None:
        return False
    amount_terms = {"loan", "amount", "principal", "ticket", "disburse", "sanction", "lakh", "lac", "crore", "limit"}
    adjust_terms = {"less", "lower", "reduce", "drop", "smaller", "instead", "maybe", "around", "about", "approve", "can you", "could you", "let's", "do"}
    if "instead" in lowered:
        return True
    return any(term in lowered for term in amount_terms) and any(term in lowered for term in adjust_terms)


def compute_best_rate(profile: Dict[str, Any]) -> float:
    score = profile.get("credit_score", 0)
    if score >= 800:
        return 9.75
    if score >= 760:
        return 10.25
    if score >= 720:
        return 10.75
    if score >= 680:
        return 11.25
    return 11.75


def try_handle_negotiation(message: str, state: str) -> bool:
    """Handle ad-hoc negotiation requests for rate or loan amount."""
    data = st.session_state.collected_data
    if not data.get("customer_phone"):
        return False

    profile = data.get("customer_profile") or {}

    if wants_lower_rate(message):
        current_rate = data.get("annual_rate_pct", DEFAULT_RATE)
        best_rate = compute_best_rate(profile)
        requested_rate = extract_number(message)

        if state == "DONE":
            add_assistant_message(
                "🤖 **Master Agent:** We've already wrapped this ticket. Type `restart` and I'll open a fresh application so we can revisit the rate together."
            )
            return True

        if requested_rate and requested_rate < 5:
            requested_rate = None  # likely not a rate, ignore

        proposed_rate = (
            max(best_rate, requested_rate) if requested_rate else max(best_rate, current_rate - 0.5)
        )

        if proposed_rate < current_rate:
            data["annual_rate_pct"] = proposed_rate
            credit_hint = ""
            credit_score = profile.get("credit_score")
            if credit_score:
                credit_hint = f" Given your credit score of {credit_score}, I've got room to request this concession."
            add_assistant_message(
                f"🤝 **Sales Agent:** I can pitch a rate of about {proposed_rate:.2f}% to underwriting for you.{credit_hint} "
                "Final numbers will still reflect their call, but I'll go in with this ask."
            )
        else:
            add_assistant_message(
                f"🤝 **Sales Agent:** We're already sitting at {current_rate:.2f}%. I'll flag your request and "
                "see if underwriting can sweeten the offer further when we submit."
            )
        return True

    if data.get("loan_amount") and wants_amount_adjustment(message):
        current_amount = data["loan_amount"]
        new_amount = extract_number(message)

        if state == "DONE":
            add_assistant_message(
                "🤖 **Master Agent:** Happy to explore a different ticket size—type `restart` and we'll tailor a fresh request."
            )
            return True

        if not new_amount or new_amount <= 0:
            add_assistant_message(
                "🤝 **Sales Agent:** I didn't quite catch the amount you had in mind. Could you share the figure in rupees?"
            )
            return True

        new_amount = float(new_amount)

        if new_amount >= current_amount:
            add_assistant_message(
                "🤝 **Sales Agent:** I'm already championing a higher ticket with underwriting. "
                "If you'd like to go even bigger, we may need fresh documents—shall we keep the current ask for now?"
            )
            return True

        data["loan_amount"] = new_amount
        limit = (profile or {}).get("pre_approved_limit")
        limit_note = ""
        if limit and new_amount > limit:
            limit_note = (
                f" (still a bit above your pre-approved {format_currency(limit)}, but I'll push for it)."
            )
        elif limit:
            limit_note = f" (comfortably within your pre-approved {format_currency(limit)})."

        add_assistant_message(
            f"🤝 **Sales Agent:** Got it—we'll reshape the request to {format_currency(new_amount)}{limit_note}"
            " and see if underwriting signs off."
        )

        if state in {"READY_TO_RUN"}:
            add_assistant_message(
                "🤖 **Master Agent:** Let me refresh the checks with this revised amount."
            )
            run_master_pipeline()
        return True

    return False


def run_master_pipeline() -> None:
    """Trigger the end-to-end orchestration once we have the required data."""
    data = st.session_state.collected_data
    profile = data.get("customer_profile") or {}
    display_name = profile.get("name") or profile.get("first_name") or "there"
    required = ["customer_phone", "loan_amount", "tenure_months"]
    missing = [field for field in required if field not in data]
    if missing:
        add_assistant_message(
            "🤖 **Master Agent:** I still need a couple of things before I brief the team: "
            + ", ".join(missing)
        )
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    context = {
        "customer_phone": data["customer_phone"],
        "loan_amount": data["loan_amount"],
        "tenure_months": data["tenure_months"],
        "annual_rate_pct": data.get("annual_rate_pct", DEFAULT_RATE),
    }
    if data.get("monthly_salary") is not None:
        context["monthly_salary"] = data["monthly_salary"]

    add_assistant_message(
        "🤖 **Master Agent:** "
        f"Thanks, {display_name}! I'm taking forward "
        f"{format_currency(context['loan_amount'])} over {context['tenure_months']} months "
        f"at around {context['annual_rate_pct']:.2f}% while I sync with underwriting and the docs team."
    )

    status, payload = master_orchestrate(context, output_dir=OUTPUT_DIR)
    st.session_state.latest_status = status
    st.session_state.latest_payload = payload

    if status == "KYC_FAILED":
        add_assistant_message(
            "🛂 **Verification Agent:** I couldn't match that number to any of our customers. Mind double-checking the digits?"
        )
        st.session_state.conversation_state = "COLLECT_PHONE"
        st.session_state.collected_data.pop("customer_phone", None)
        st.session_state.collected_data.pop("customer_name", None)
        st.session_state.collected_data["customer_profile"] = None
        return

    if status == "REQUIRE_SALARY":
        emi = payload.get("emi")
        message = (
            "📊 **Underwriting Agent:** I'm almost there, but I do need a monthly take-home figure to close this out."
            + (f" Right now the EMI is tracking around {format_currency(emi)}." if emi else "")
        )
        add_assistant_message(message)
        add_assistant_message(
            "🤖 **Master Agent:** A quick salary number will help me champion this for you. What does your monthly income look like?"
        )
        st.session_state.conversation_state = "COLLECT_SALARY"
        return

    if status == "REJECT":
        reason = payload.get("reason") or "Policy rules prevent us from approving this request."
        add_assistant_message(f"📊 **Underwriting Agent:** I'm sorry — we have to decline this one because {reason}.")
        add_assistant_message(
            "🤖 **Master Agent:** If you'd like, I can explore a different amount or tenure. Just type `restart` and we'll try again together."
        )
        st.session_state.conversation_state = "DONE"
        return

    if status == "APPROVED":
        emi = payload.get("emi", 0.0)
        name = st.session_state.collected_data.get("customer_name")
        greeting = f"{name}, " if name else ""
        city = profile.get("city")
        city_line = f" in {city}" if city else ""
        add_assistant_message(
            f"📊 **Underwriting Agent:** All checks passed! Your estimated EMI comes to {format_currency(emi)}."
        )
        add_assistant_message(
            f"📄 **Sanction Agent:** {greeting}I've drafted your sanction letter{city_line}. Grab it below when you're ready!"
        )
        add_assistant_message("🤖 **Master Agent:** Congratulations! Type `restart` to run another application.")
        st.session_state.conversation_state = "DONE"
        return

    add_assistant_message(
        f"🤖 **Master Agent:** I encountered an unexpected status `{status}`. Let's restart if you'd like to try again."
    )
    st.session_state.conversation_state = "DONE"


def handle_user_message(message: str) -> None:
    """Route the user's reply through the conversation state machine."""
    # Allow restarting at any time
    if message.strip().lower() in {"restart", "reset", "start over", "new"}:
        reset_conversation()
        return

    state = st.session_state.conversation_state
    data = st.session_state.collected_data

    if try_handle_negotiation(message, state):
        return

    if state == "DONE":
        add_assistant_message("🤖 **Master Agent:** We're all done. Type `restart` to explore another application.")
        return

    if state == "COLLECT_PHONE":
        digits = re.sub(r"\D", "", message)
        if not digits:
            if is_greeting(message):
                add_assistant_message(
                    "🤖 **Master Agent:** Hey, it's nice to meet you! Whenever you're ready, drop the 10-digit number you use with us."
                )
                st.session_state.phone_retry_count = 0
            elif is_negative_response(message):
                add_assistant_message(
                    "🤖 **Master Agent:** No problem—if now's not a great time, we can pause. When you're ready to continue, just share the mobile number you bank with."
                )
            else:
                add_assistant_message(next_phone_prompt())
            return
        if len(digits) < 10:
            add_assistant_message(
                "🤖 **Master Agent:** Looks like a few digits might be missing. Could you share the full 10-digit number?"
            )
            add_assistant_message(next_phone_prompt())
            return
        phone = digits[-10:]
        data["customer_phone"] = phone
        st.session_state.phone_retry_count = 0
        add_assistant_message(
            f"🤖 **Master Agent:** Perfect, thanks! Let me get {phone} verified real quick."
        )
        verification = task_verify(phone)
        if not verification["verified"]:
            add_assistant_message(
                "🛂 **Verification Agent:** I couldn't find a customer with that number. Could you try another number?"
            )
            data.pop("customer_phone", None)
            return
        data["customer_name"] = verification.get("name")
        profile = crm_get_customer_by_phone(phone) or {}
        data["customer_profile"] = profile
        city = profile.get("city")
        limit = profile.get("pre_approved_limit")
        add_assistant_message(
            f"🛂 **Verification Agent:** All set! I've confirmed {verification.get('name', 'the customer')}'s details at "
            f"{verification.get('address', 'the registered address')}."
        )
        add_assistant_message(
            "🤖 **Master Agent:** Wonderful! "
            + (
                f"It's great to connect again with our {city} family. " if city else ""
            )
            + (
                f"You're currently pre-approved for up to {format_currency(limit)}. "
                "What loan amount are you hoping to secure?"
                if limit
                else "What loan amount are you hoping to secure today?"
            )
        )
        st.session_state.conversation_state = "COLLECT_LOAN"
        return

    if state == "COLLECT_LOAN":
        amount = extract_number(message)
        if amount is None:
            add_assistant_message("🤖 **Master Agent:** Please specify the desired loan amount (numbers only).")
            return
        if amount < MIN_LOAN:
            add_assistant_message(
                f"🤖 **Master Agent:** The minimum loan amount is ₹{MIN_LOAN:,.0f}. Could you confirm an amount above that?"
            )
            return
        data["loan_amount"] = float(amount)
        limit = (data.get("customer_profile") or {}).get("pre_approved_limit")
        if limit and amount > limit:
            add_assistant_message(
                f"🤖 **Master Agent:** Noted. That's a bit above your pre-approved {format_currency(limit)}, "
                "but let me see if underwriting can stretch."
            )
        else:
            add_assistant_message(
                "🤖 **Master Agent:** Perfect. Now, over how many months would you like to repay the loan?"
            )
            st.session_state.conversation_state = "COLLECT_TENURE"
            return

        add_assistant_message(
            "🤖 **Master Agent:** Over how many months would you like to space out the repayments?"
        )
        st.session_state.conversation_state = "COLLECT_TENURE"
        return

    if state == "COLLECT_TENURE":
        tenure = parse_tenure(message)
        if tenure is None:
            add_assistant_message("🤖 **Master Agent:** Could you share the tenure in months (or years)?")
            return
        if tenure < MIN_TENURE or tenure > MAX_TENURE:
            add_assistant_message(
                f"🤖 **Master Agent:** Please choose a tenure between {MIN_TENURE} and {MAX_TENURE} months."
            )
            return
        data["tenure_months"] = tenure
        add_assistant_message(
            "🤖 **Master Agent:** Great choice. If it's okay with you, can we note your monthly salary now? "
            "You can always say no and I'll only ask again if underwriting insists."
        )
        st.session_state.conversation_state = "ASK_SALARY_OPTION"
        return

    if state == "ASK_SALARY_OPTION":
        if is_positive_response(message):
            add_assistant_message(
                "🤖 **Master Agent:** Appreciate it! What's your approximate monthly salary (INR)?"
            )
            st.session_state.conversation_state = "COLLECT_SALARY"
            return
        if is_negative_response(message):
            add_assistant_message(
                "🤖 **Master Agent:** Totally fine. I'll proceed with underwriting and loop back only if they insist."
            )
            st.session_state.conversation_state = "READY_TO_RUN"
            run_master_pipeline()
            return
        add_assistant_message("🤖 **Master Agent:** I caught neither a yes nor a no. Could you confirm?")
        return

    if state == "COLLECT_SALARY":
        salary = extract_number(message)
        if salary is None or salary <= 0:
            add_assistant_message("🤖 **Master Agent:** Please share the salary as a numeric value.")
            return
        data["monthly_salary"] = float(salary)
        add_assistant_message(
            "🤖 **Master Agent:** Thanks! I'll highlight that figure while I liaise with underwriting."
        )
        st.session_state.conversation_state = "READY_TO_RUN"
        run_master_pipeline()
        return

    if state == "READY_TO_RUN":
        run_master_pipeline()
        return

    add_assistant_message("🤖 **Master Agent:** I'm not sure how to use that information. Let's continue with the flow.")


# ---- Initial Session Setup ----
if "chat_history" not in st.session_state:
    reset_conversation()


# Ensure the API key is available before continuing
if not os.environ.get("GOOGLE_API_KEY"):
    st.error("GOOGLE_API_KEY is not set in the environment. Please set it and restart the app.")
    st.stop()


# ---- Sidebar: Sample Data & Controls ----
with open(Path(__file__).parent / "sample_data.json", "r", encoding="utf-8") as f:
    SAMPLE_DATA = json.load(f)["customers"]

st.sidebar.header("👥 Test Customers")
labels = [f"{c['name']} — {c['phone']}" for c in SAMPLE_DATA]
selected_label = st.sidebar.selectbox("Preview available mock customers", labels, index=0)
selected_customer = SAMPLE_DATA[labels.index(selected_label)]

st.sidebar.markdown(
    f"""
    **City:** {selected_customer['city']}  
    **Credit Score:** {selected_customer['credit_score']}  
    **Pre-approved Limit:** ₹{selected_customer['pre_approved_limit']:,.0f}  
    **Monthly Salary:** ₹{selected_customer['monthly_salary']:,.0f}
    """
)
st.sidebar.info("Use the selected customer's phone number in chat to experience an end-to-end approval.")

if st.sidebar.button("Reset conversation", use_container_width=True):
    reset_conversation()
    trigger_rerun()

st.sidebar.divider()
st.sidebar.caption("© Demo for EY Techathon BFSI — Agentic AI Orchestration with CrewAI + Gemini + Streamlit")


# ---- Chat Conversation UI ----
for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

prompt = st.chat_input("Type your response")
if prompt:
    st.session_state.chat_history.append({"role": "user", "content": prompt})
    handle_user_message(prompt)
    trigger_rerun()


# ---- Post-Decision Outputs ----
if st.session_state.get("latest_status") == "APPROVED":
    payload = st.session_state.get("latest_payload") or {}
    pdf_path = payload.get("pdf_path")
    if pdf_path and Path(pdf_path).exists():
        with open(pdf_path, "rb") as fh:
            st.download_button(
                "⬇️ Download Sanction Letter (PDF)",
                data=fh,
                file_name=Path(pdf_path).name,
                mime="application/pdf",
            )

elif st.session_state.get("latest_status") == "REJECT":
    payload = st.session_state.get("latest_payload") or {}
    reason = payload.get("reason") or "No additional details provided."
    st.error(f"Loan application rejected — {reason}")
