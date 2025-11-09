from __future__ import annotations
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from datetime import datetime
from pathlib import Path

def generate_sanction_letter(output_path: Path, *, customer_name: str, phone: str,
                             loan_amount: float, tenure_months: int, annual_rate_pct: float,
                             emi: float) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(output_path), pagesize=A4)
    width, height = A4

    y = height - 72
    c.setFont("Helvetica-Bold", 16)
    c.drawString(72, y, "Personal Loan Sanction Letter")
    y -= 24

    c.setFont("Helvetica", 10)
    c.drawString(72, y, f"Date: {datetime.now().strftime('%Y-%m-%d')}")
    y -= 20
    c.drawString(72, y, f"To: {customer_name} ({phone})")
    y -= 20
    c.drawString(72, y, f"Subject: Sanction of Personal Loan")
    y -= 30

    body = [
        f"We are pleased to inform you that your personal loan has been sanctioned.",
        f"Sanction Amount: INR {loan_amount:,.2f}",
        f"Tenure: {tenure_months} months",
        f"Interest Rate: {annual_rate_pct:.2f}% p.a.",
        f"Calculated EMI: INR {emi:,.2f} (approx.)",
        "",
        "Please note: This is a system-generated letter for demonstration purposes only.",
    ]
    for line in body:
        c.drawString(72, y, line)
        y -= 16

    c.showPage()
    c.save()
    return output_path
