from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import re

import pandas as pd
import streamlit as st


BASE_DIR = Path(__file__).resolve().parent
SAMPLE_FILE = BASE_DIR / "sample_data" / "sample_leads.csv"


FIELD_ALIASES = {
    "client_name": [
        "client name",
        "customer name",
        "full name",
        "name",
        "lead name",
        "contact",
    ],
    "email": [
        "email",
        "email address",
        "e-mail",
        "mail",
        "contact email",
    ],
    "phone": [
        "phone",
        "phone number",
        "phone#",
        "mobile",
        "tel",
        "telephone",
    ],
    "company": [
        "company",
        "business",
        "business name",
        "organization",
        "org",
    ],
    "service_needed": [
        "service",
        "service needed",
        "request",
        "need",
        "project type",
        "workflow issue",
    ],
    "notes": [
        "notes",
        "message",
        "comment",
        "details",
        "description",
    ],
    "submitted_at": [
        "submitted at",
        "created at",
        "timestamp",
        "date",
        "submission date",
    ],
}


DISPLAY_COLUMNS = [
    "client_name",
    "email",
    "phone",
    "company",
    "service_needed",
    "notes",
    "submitted_at",
    "lead_status",
]


@dataclass
class WorkflowResult:
    raw_data: pd.DataFrame
    clean_data: pd.DataFrame
    mapping: dict[str, str]
    issues: list[str]


def normalize_header(value: str) -> str:
    text = str(value).strip().lower()
    text = re.sub(r"[_\-]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text


def detect_field_mapping(columns: list[str]) -> dict[str, str]:
    normalized = {normalize_header(column): column for column in columns}
    mapping: dict[str, str] = {}

    for target_field, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                mapping[target_field] = normalized[alias]
                break

    return mapping


def clean_phone(value: object) -> str:
    if pd.isna(value):
        return ""
    digits = re.sub(r"\D", "", str(value))
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    return str(value).strip()


def clean_text(value: object, *, title_case: bool = False, lower_case: bool = False) -> str:
    if pd.isna(value):
        return ""
    text = re.sub(r"\s+", " ", str(value)).strip()
    if lower_case:
        return text.lower()
    if title_case:
        return text.title()
    return text


def clean_service(value: object) -> str:
    text = clean_text(value)
    replacements = {
        "sheet cleanup": "Spreadsheet Cleanup",
        "sheets cleanup": "Spreadsheet Cleanup",
        "csv import": "CSV Import Fix",
        "form fix": "Form Data Fix",
        "automation": "Workflow Automation",
        "workflow automation": "Workflow Automation",
    }
    key = text.lower()
    return replacements.get(key, text.title() if text else "")


def build_clean_dataframe(raw_data: pd.DataFrame) -> WorkflowResult:
    mapping = detect_field_mapping(list(raw_data.columns))
    clean_data = pd.DataFrame(index=raw_data.index)
    issues: list[str] = []

    for target_field in DISPLAY_COLUMNS:
        if target_field == "lead_status":
            continue
        source_field = mapping.get(target_field)
        if source_field:
            clean_data[target_field] = raw_data[source_field]
        else:
            clean_data[target_field] = ""
            issues.append(f"Missing field: {target_field}")

    clean_data["client_name"] = clean_data["client_name"].map(
        lambda value: clean_text(value, title_case=True)
    )
    clean_data["email"] = clean_data["email"].map(
        lambda value: clean_text(value, lower_case=True)
    )
    clean_data["phone"] = clean_data["phone"].map(clean_phone)
    clean_data["company"] = clean_data["company"].map(
        lambda value: clean_text(value, title_case=True)
    )
    clean_data["service_needed"] = clean_data["service_needed"].map(clean_service)
    clean_data["notes"] = clean_data["notes"].map(clean_text)
    clean_data["submitted_at"] = clean_data["submitted_at"].map(clean_text)
    clean_data["lead_status"] = clean_data.apply(calculate_status, axis=1)

    duplicate_count = int(clean_data.duplicated(subset=["email"], keep=False).sum())
    missing_email_count = int((clean_data["email"] == "").sum())
    if duplicate_count:
        issues.append(f"Duplicate email rows detected: {duplicate_count}")
    if missing_email_count:
        issues.append(f"Rows missing email: {missing_email_count}")

    return WorkflowResult(
        raw_data=raw_data,
        clean_data=clean_data[DISPLAY_COLUMNS],
        mapping=mapping,
        issues=issues,
    )


def calculate_status(row: pd.Series) -> str:
    if not row.get("email"):
        return "Needs review"
    if not row.get("client_name") or not row.get("service_needed"):
        return "Incomplete"
    return "Ready"


def load_csv(uploaded_file: BytesIO | None) -> pd.DataFrame:
    if uploaded_file is not None:
        return pd.read_csv(uploaded_file)
    return pd.read_csv(SAMPLE_FILE)


def build_email_preview(clean_data: pd.DataFrame) -> str:
    ready_rows = clean_data[clean_data["lead_status"] == "Ready"]
    review_rows = clean_data[clean_data["lead_status"] != "Ready"]
    top_services = clean_data["service_needed"].replace("", pd.NA).dropna().value_counts()
    service_summary = ", ".join(
        f"{service}: {count}" for service, count in top_services.head(3).items()
    )
    if not service_summary:
        service_summary = "No service categories detected"

    return f"""Subject: Cleaned lead workflow preview ready

Hi team,

The uploaded CSV has been reviewed and mapped into a Google Sheets style lead table.

Summary:
- Total rows: {len(clean_data)}
- Ready for follow-up: {len(ready_rows)}
- Need manual review: {len(review_rows)}
- Top service requests: {service_summary}

Suggested next action:
Review rows marked "Needs review" or "Incomplete", then copy the clean table into your working sheet.

This is a local preview only. No Gmail message was sent.
"""


def build_delivery_note(result: WorkflowResult) -> str:
    mapped_lines = [
        f"- {target}: {source}" for target, source in sorted(result.mapping.items())
    ]
    issue_lines = [f"- {issue}" for issue in result.issues] or [
        "- No critical data issues found in the preview."
    ]
    return f"""# Client Delivery Note

## What was cleaned
- Uploaded or sample CSV was loaded locally.
- Column names were mapped into a standard lead workflow table.
- Names, emails, phone numbers, company names, service labels, and empty fields were normalized.
- A Gmail-style notification was generated as preview text only.

## Field mapping
{chr(10).join(mapped_lines)}

## Items to review
{chr(10).join(issue_lines)}

## Safety boundary
- No Google Sheets API write was performed.
- No Gmail API send was performed.
- No OAuth login was requested.
- No API key, token, cookie, password, or real customer data is required.
"""


def render_metric(label: str, value: int | str) -> None:
    st.markdown(
        f"""
        <div class="metric-box">
            <span>{label}</span>
            <strong>{value}</strong>
        </div>
        """,
        unsafe_allow_html=True,
    )


def configure_page() -> None:
    st.set_page_config(
        page_title="Google Sheets Workflow Fix Toolkit",
        page_icon="",
        layout="wide",
    )
    st.markdown(
        """
        <style>
        :root {
            --border: #d9e2ec;
            --ink: #1f2933;
            --muted: #62748a;
            --surface: #ffffff;
            --accent: #2364aa;
            --ok: #157347;
            --warn: #9a5b00;
        }
        .stApp {
            background: #f6f8fb;
            color: var(--ink);
        }
        h1, h2, h3 {
            letter-spacing: 0;
        }
        .block-container {
            padding-top: 1.4rem;
            max-width: 1320px;
        }
        .app-header {
            border-bottom: 1px solid var(--border);
            padding-bottom: 0.85rem;
            margin-bottom: 1rem;
        }
        .app-header h1 {
            font-size: 2rem;
            margin: 0 0 0.3rem 0;
        }
        .app-header p {
            color: var(--muted);
            margin: 0;
            font-size: 1rem;
        }
        .metric-box {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 0.85rem 1rem;
            min-height: 84px;
        }
        .metric-box span {
            display: block;
            color: var(--muted);
            font-size: 0.85rem;
            margin-bottom: 0.45rem;
        }
        .metric-box strong {
            color: var(--ink);
            font-size: 1.75rem;
            line-height: 1;
        }
        .status-ready {
            color: var(--ok);
            font-weight: 700;
        }
        .status-review {
            color: var(--warn);
            font-weight: 700;
        }
        div[data-testid="stDataFrame"] {
            border: 1px solid var(--border);
            border-radius: 8px;
            overflow: hidden;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    configure_page()

    st.markdown(
        """
        <div class="app-header">
            <h1>Google Sheets Workflow Fix Toolkit</h1>
            <p>Client Workflow Preview: clean messy CSV leads, preview a sheet-ready table, and draft handoff text without connecting to Google services.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    upload_col, note_col = st.columns([1, 2], vertical_alignment="top")
    with upload_col:
        st.subheader("Input")
        uploaded_file = st.file_uploader("Upload a CSV file", type=["csv"])
        st.caption("Default sample: sample_data/sample_leads.csv")
    with note_col:
        st.subheader("Demo boundary")
        st.info(
            "This preview runs locally. It does not send Gmail messages, write to Google Sheets, request OAuth, or use API keys."
        )

    raw_data = load_csv(uploaded_file)
    result = build_clean_dataframe(raw_data)

    ready_count = int((result.clean_data["lead_status"] == "Ready").sum())
    review_count = int((result.clean_data["lead_status"] != "Ready").sum())

    metric_cols = st.columns(4)
    with metric_cols[0]:
        render_metric("Rows loaded", len(result.raw_data))
    with metric_cols[1]:
        render_metric("Mapped fields", len(result.mapping))
    with metric_cols[2]:
        render_metric("Ready rows", ready_count)
    with metric_cols[3]:
        render_metric("Review rows", review_count)

    left, right = st.columns([1, 1], gap="large")
    with left:
        st.subheader("Messy CSV preview")
        st.dataframe(result.raw_data, use_container_width=True, height=280)
    with right:
        st.subheader("Detected field mapping")
        mapping_df = pd.DataFrame(
            [{"Clean field": key, "CSV column": value} for key, value in result.mapping.items()]
        )
        st.dataframe(mapping_df, use_container_width=True, height=280, hide_index=True)

    st.subheader("Google Sheets style clean table")
    st.dataframe(
        result.clean_data,
        use_container_width=True,
        height=330,
        hide_index=True,
        column_config={
            "client_name": "Client Name",
            "email": "Email",
            "phone": "Phone",
            "company": "Company",
            "service_needed": "Service Needed",
            "notes": "Notes",
            "submitted_at": "Submitted At",
            "lead_status": "Lead Status",
        },
    )

    email_tab, delivery_tab = st.tabs(
        ["Gmail notification preview", "Client delivery note"]
    )
    with email_tab:
        st.text_area(
            "Generated Gmail preview",
            build_email_preview(result.clean_data),
            height=260,
        )
    with delivery_tab:
        st.download_button(
            "Download delivery note",
            build_delivery_note(result).encode("utf-8"),
            file_name="client_delivery_note.md",
            mime="text/markdown",
        )
        st.markdown(build_delivery_note(result))


if __name__ == "__main__":
    main()
