# BFSI Agentic AI Demo (CrewAI + Gemini + Streamlit)

This is a minimal, end-to-end demo for the EY Techathon BFSI problem statement using:
- **CrewAI** for agent orchestration
- **Gemini** (via LangChain) as the LLM
- **Streamlit** for the front-end chat
- **Mock APIs** for CRM, credit bureau, and offer mart
- **ReportLab** to generate a simple sanction letter PDF

## Project Structure
```
.
├── app.py                 # Streamlit front-end
├── agents.py              # CrewAI agents and tasks
├── tools.py               # Mock API tools and helpers
├── underwriting.py        # Underwriting logic
├── sanction.py            # Sanction letter PDF generator
├── sample_data.json       # Synthetic customer dataset
├── requirements.txt
└── README.md
```

## Quick Start

1) **Create & activate a virtualenv (recommended)**
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
```

2) **Install requirements**
```bash
pip install -r requirements.txt
```

3) **Set your API key for Gemini (Google Generative AI)**
```bash
export GOOGLE_API_KEY="YOUR_KEY"   # Windows: set GOOGLE_API_KEY=YOUR_KEY
```

4) **Run the Streamlit app**
```bash
streamlit run app.py
```

5) **Open the UI** (Streamlit will show a local URL).

---

## How it Works

- **Master Agent** (orchestrator): Routes conversation and work to:
  - **Sales Agent:** Persuasion + collects loan amount, tenure, salary (if needed)
  - **Verification Agent:** KYC check against dummy CRM
  - **Underwriting Agent:** Fetches credit score (mock), applies rules, requests salary slip when needed
  - **Sanction Agent:** Generates a PDF sanction letter using ReportLab

**Eligibility Rules (from the problem statement):**
- If `loan_amount <= pre_approved_limit` ⇒ **approve instantly**.
- If `loan_amount <= 2x pre_approved_limit` ⇒ **request salary slip** and approve only if `EMI <= 50% of salary`.
- If `loan_amount > 2x pre_approved_limit` or `credit_score < 700` ⇒ **reject**.

The UI lets you simulate users (10 synthetic customers). Select a user, enter desired loan parameters, and converse.
When the flow reaches a decision, the app will generate a **Sanction Letter** PDF and provide a download link.

---

## Notes
- This is a minimal educational demo—**do not** use in production as-is.
- Replace mock data/APIs with your real services later.
- You can swap the LLM by editing `agents.py` (e.g., OpenAI, Azure OpenAI) if desired.
