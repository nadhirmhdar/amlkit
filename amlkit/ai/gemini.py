"""Gemini AI assistant for compliance workflows.

Provides AI-generated drafts and explanations to assist compliance officers
with case-writing tasks.  All outputs are advisory only and must be reviewed
by a qualified MLRO before being used in any regulatory filing.

Environment variables:
    GEMINI_API_KEY   — Google AI Studio key (required to call any function)
    GEMINI_MODEL     — model id (default: gemini-2.5-flash)

Functions return plain text.  They raise GeminiUnavailable when the API key
is missing or the call fails, so callers can degrade gracefully without
crashing the main request flow.
"""

from __future__ import annotations

import os
import textwrap
from typing import Any

GEMINI_MODEL: str = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")


class GeminiUnavailable(RuntimeError):
    """Raised when Gemini AI is not configured or the API call fails."""


def _client():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise GeminiUnavailable(
            "GEMINI_API_KEY is not set. "
            "Get a key at https://aistudio.google.com/apikey and set the env var."
        )
    try:
        import google.generativeai as genai
    except ImportError as exc:
        raise GeminiUnavailable(
            "google-generativeai is not installed. "
            "Run: pip install google-generativeai>=0.8"
        ) from exc

    genai.configure(api_key=api_key)
    return genai.GenerativeModel(GEMINI_MODEL)


def _call(prompt: str) -> str:
    model = _client()
    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as exc:
        raise GeminiUnavailable(f"Gemini API call failed: {exc}") from exc


def draft_str_narrative(
    customer: dict[str, Any],
    alerts: list[dict[str, Any]],
    risk: dict[str, Any] | None = None,
    notes: list[dict[str, Any]] | None = None,
) -> str:
    """Draft a Suspicious Transaction Report narrative from case data.

    Args:
        customer: Dict with keys: reference, full_name, customer_type,
                  nationality, sector, delivery_channel, onboarded_at.
        alerts:   List of alert dicts: matched_name, score, disposition, status,
                  entity dataset/programme info.
        risk:     Latest risk assessment dict: score, rating, factors.
        notes:    List of case note dicts: author, body, created_at.

    Returns:
        Draft STR narrative text.  Always label this "AI-GENERATED DRAFT —
        requires MLRO review" in any UI showing it.
    """
    alert_lines = "\n".join(
        f"  - Match: {a.get('matched_name', 'unknown')}  "
        f"score={a.get('score', 0):.2f}  "
        f"status={a.get('status', 'open')}"
        for a in alerts
    ) or "  (none)"

    risk_section = ""
    if risk:
        risk_section = (
            f"\nRisk assessment: score={risk.get('score', 0):.1f}, "
            f"rating={risk.get('rating', 'unknown')}, "
            f"EDD required={bool(risk.get('requires_edd'))}"
        )

    notes_section = ""
    if notes:
        notes_section = "\nCase notes:\n" + "\n".join(
            f"  [{n.get('created_at', '')}] {n.get('author', '')}: {n.get('body', '')}"
            for n in notes[:5]
        )

    prompt = textwrap.dedent(f"""
        You are a senior UAE AML compliance officer drafting a Suspicious Transaction
        Report (STR) for submission to the UAE Financial Intelligence Unit (FIU) via
        the goAML system.

        Write a concise, factual, third-person STR narrative paragraph (150–250 words)
        that:
        - States the nature of the suspicion without conclusory language
        - Describes the customer profile relevant to the suspicion
        - Summarises the sanctions/PEP matches that triggered the report
        - Notes any risk factors or case observations
        - Avoids any personal opinion, speculation, or legally sensitive language
        - Is suitable for submission to a financial regulator

        Customer profile:
          Reference:     {customer.get('reference', 'N/A')}
          Type:          {customer.get('customer_type', 'N/A')}
          Nationality:   {customer.get('nationality', 'N/A')}
          Sector:        {customer.get('sector', 'N/A')}
          Channel:       {customer.get('delivery_channel', 'N/A')}
          Onboarded:     {customer.get('onboarded_at', 'N/A')}

        Sanctions/PEP alerts:
        {alert_lines}
        {risk_section}
        {notes_section}

        Draft the narrative only — no headings, no bullet points, no explanatory text.
    """).strip()

    return _call(prompt)


def explain_risk_score(
    customer_ref: str,
    score: float,
    rating: str,
    factors: dict[str, Any],
    requires_edd: bool,
) -> str:
    """Explain a risk assessment score in plain language for a compliance officer.

    Args:
        customer_ref: Customer reference code.
        score:        Numeric risk score.
        rating:       low | medium | high
        factors:      Per-factor breakdown from risk_assessments.factors (JSON).
        requires_edd: Whether enhanced due diligence is required.

    Returns:
        Plain-language explanation of the risk score (2–3 short paragraphs).
    """
    factors_text = "\n".join(
        f"  - {k}: {v}"
        for k, v in (factors.items() if isinstance(factors, dict) else {})
    ) or "  (no factor detail available)"

    edd_note = "Enhanced due diligence IS required." if requires_edd else \
               "Standard due diligence is sufficient."

    prompt = textwrap.dedent(f"""
        You are a UAE AML compliance training assistant explaining risk assessment
        results to a compliance officer in clear, non-technical English.

        Explain why customer {customer_ref} received a risk score of {score:.1f}
        ({rating} risk) in 2–3 short paragraphs.  Cover:
        1. Which factors drove the score up most significantly
        2. What this rating means for the firm's obligations
        3. {edd_note}  Briefly state what that requires in practice.

        Factor breakdown:
        {factors_text}

        Keep the explanation factual and practical — no introductory pleasantries,
        no markdown, no bullet points, plain prose only.
    """).strip()

    return _call(prompt)


def summarize_adverse_media(
    customer_ref: str,
    findings: list[dict[str, Any]],
) -> str:
    """Summarise adverse media findings for a customer into one readable paragraph.

    Args:
        customer_ref: Customer reference code.
        findings:     List of adverse_media_findings dicts: title, domain,
                      published_at, severity, matched_terms.

    Returns:
        One paragraph summarising the findings, or a note that none were found.
    """
    if not findings:
        return (
            f"No adverse media findings were recorded for customer {customer_ref}. "
            "The media screening returned no articles matching the customer's name "
            "against known AML/CFT risk terms."
        )

    finding_lines = "\n".join(
        f"  - [{f.get('published_at', 'unknown date')}] "
        f"{f.get('title', 'untitled')} "
        f"(source: {f.get('domain', 'unknown')}, "
        f"severity: {f.get('severity', 'unknown')}, "
        f"terms: {', '.join(f.get('matched_terms', []) or [])})"
        for f in findings[:10]
    )

    prompt = textwrap.dedent(f"""
        You are a UAE AML compliance officer summarising adverse media findings
        for a customer file.

        Write one factual paragraph (100–150 words) summarising the adverse media
        findings for customer {customer_ref}.  The paragraph should:
        - State the number of findings and the overall severity
        - Highlight the most significant articles (by date and source)
        - Note which AML/CFT risk terms were matched
        - Avoid editorialising or speculating about guilt
        - Be written in third person, suitable for a compliance file note

        Findings:
        {finding_lines}

        Write the summary paragraph only — no headings, no bullet points.
    """).strip()

    return _call(prompt)


def suggest_alert_disposition(
    matched_name: str,
    score: float,
    entity_caption: str,
    entity_countries: list[str],
    customer_type: str,
    customer_nationality: str,
) -> str:
    """Suggest a disposition for a sanctions/PEP alert.

    This is a decision-support tool only.  The suggestion is not a compliance
    determination and must be reviewed by a qualified MLRO.

    Returns:
        A short reasoned suggestion (true_positive / false_positive / escalate)
        with a 2–3 sentence rationale.
    """
    prompt = textwrap.dedent(f"""
        You are a UAE AML compliance expert providing decision support on a
        sanctions screening alert.

        Alert details:
          Screened name:      {matched_name}
          Match score:        {score:.2f} (0–1 scale; ≥0.85 = strong match)
          Matched entity:     {entity_caption}
          Entity countries:   {', '.join(entity_countries) or 'unknown'}
          Customer type:      {customer_type}
          Customer nationality: {customer_nationality}

        Based on these facts alone (no additional information available), suggest
        one of:
          - TRUE POSITIVE: the match is likely the same person/entity
          - FALSE POSITIVE: the match is likely coincidental
          - ESCALATE: more information is needed before a determination

        Structure your response as:
        Suggestion: <TRUE POSITIVE / FALSE POSITIVE / ESCALATE>
        Rationale: <2–3 sentences explaining the reasoning>

        Be concise and factual.  Do not speculate beyond what the data shows.
    """).strip()

    return _call(prompt)
