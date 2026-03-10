"""
zoning_check.py — Post-Calculation Zoning Adjustment Pass
Searches for local zoning laws, overlays, incentive programs, and recent ordinance
changes that could materially affect the model. Applies adjustments and re-runs calculations.
"""

import json
import re
import copy
import time
from datetime import date
from typing import Optional
import anthropic
import streamlit as st
from calculations import run_calculations

MODEL = "claude-sonnet-4-20250514"

def _get_client():
    try:
        return anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])
    except Exception:
        return anthropic.Anthropic()
TODAY = date.today().isoformat()

SYSTEM_ZONING = """You are a real estate entitlement and zoning research specialist. Your job is to find
zoning adjustments, overlays, incentive programs, and recent ordinance changes that could affect
a specific real estate development project.

Rules:
- Search municipal code, planning commission documents, state housing laws, and recent news.
- Only cite sources updated in 2024-2026.
- Return ONLY valid JSON — no preamble, no markdown.
- For each finding include: adjustment_type, description, revised_value, original_value, source_url, confidence (high/medium/low).
- If nothing applies, return an empty adjustments array.
- Do not fabricate — cite exact URLs.
"""


def run_zoning_adjustment_pass(
    location: str,
    building_type: str,
    use_type: str,
    initial_results: dict,
    assumptions: dict,
    user_inputs: dict,
) -> dict:
    """
    Search for zoning adjustments that could affect the model.
    Re-runs calculations with any high/medium confidence adjustments applied.

    Returns:
    {
        "adjustments": [...],
        "adjusted_assumptions": {...},
        "original_results": {...},
        "adjusted_results": {...},
        "any_changes": bool,
    }
    """

    # Build context from current assumptions for the prompt
    zoning = assumptions.get("zoning", {})

    def zval(key, fallback="unknown"):
        item = zoning.get(key, {})
        if isinstance(item, dict):
            v = item.get("value")
            return str(v) if v is not None else fallback
        return str(item) if item else fallback

    parking_1br = zval("parking_1br", "1.0")
    max_far = zval("max_far", "unknown")
    max_height = zval("max_height_stories", "unknown")

    prompt = f"""
I am evaluating a {building_type} {use_type} development project at or near {location}.

Current baseline zoning assumptions:
- Maximum FAR: {max_far}
- Maximum height: {max_height} stories
- Parking requirement (1BR): {parking_1br} spaces/unit

Search for the following that might apply to this location and project type:

1. DENSITY BONUSES — local ordinances allowing additional height or FAR in exchange for affordable units, green building, or other public benefits
2. PARKING REDUCTIONS OR EXEMPTIONS — overlay zones, TOD districts, form-based codes, or city policies that reduce or eliminate minimum parking requirements for this location and building type
3. AFFORDABLE HOUSING INCENTIVES — tax abatements (e.g., 421-a in NYC, LIHTC in other states), fee waivers, expedited permitting, or subsidies for the specific use type
4. HEIGHT OR FAR OVERLAYS — special districts, specific plans, or corridor overlays that change baseline zoning for this parcel
5. RECENT ZONING CHANGES — any rezoning, upzoning, or new ordinance passed in 2024-2026 that applies to this location
6. STATE-LEVEL PREEMPTION LAWS — any state housing law (e.g. California SB 9/SB 10/ADU laws, Texas SB 2, Virginia HB 2, Florida Live Local Act) that overrides local zoning and expands what is permissible
7. IMPACT FEE SCHEDULES — any local development impact fees that should be added to soft costs (school fees, transportation fees, park fees, etc.)

For each finding, return structured data about what changed and how it affects the financial model.

Return a JSON object:
{{
  "adjustments": [
    {{
      "adjustment_type": "PARKING_REDUCTION" | "DENSITY_BONUS" | "TAX_ABATEMENT" | "FAR_INCREASE" | "HEIGHT_INCREASE" | "FEE_WAIVER" | "IMPACT_FEE" | "STATE_PREEMPTION" | "REZONING",
      "description": "Plain English description of what was found",
      "financial_impact": "Which model input is affected and how",
      "revised_value": <new numeric value or null>,
      "original_value": <current numeric value or null>,
      "unit": "spaces/unit | stories | ratio | $ | %",
      "assumption_key": "The key in assumptions dict to update (e.g. zoning.parking_1br.value)",
      "source_url": "exact URL",
      "source_name": "site name",
      "confidence": "high" | "medium" | "low",
      "notes": "any caveats or conditions"
    }}
  ]
}}

Search: "{location} density bonus zoning ordinance {building_type} 2024 2025"
Also search: "{location} TOD transit overlay parking reduction {building_type}"
Also search: "{location} affordable housing incentive tax abatement fee waiver 2025"
Also search: "{location} zoning upzone rezoning 2024 2025"
Also search: "state housing law preemption {location} {building_type} 2024 2025"
Also search: "{location} development impact fees {building_type} 2025"
"""

    tools = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}]
    messages = [{"role": "user", "content": prompt}]

    max_retries = 4
    for attempt in range(max_retries):
        try:
            response = _get_client().messages.create(
                model=MODEL,
                max_tokens=3000,
                system=SYSTEM_ZONING,
                tools=tools,
                messages=messages,
            )
            break
        except anthropic.RateLimitError:
            if attempt < max_retries - 1:
                time.sleep(65 + 30 * attempt)  # 65, 95, 125s
            else:
                return {
                    "adjustments": [], "applicable_adjustments": [],
                    "adjusted_assumptions": assumptions, "original_results": initial_results,
                    "adjusted_results": initial_results, "any_changes": False,
                }

    # Parse response
    text_parts = []
    for block in response.content:
        if hasattr(block, "text"):
            text_parts.append(block.text)
    full_text = "\n".join(text_parts).strip()

    json_match = re.search(r"```(?:json)?\s*([\s\S]+?)```", full_text)
    if json_match:
        json_str = json_match.group(1).strip()
    else:
        json_match = re.search(r"(\{[\s\S]+\})", full_text)
        json_str = json_match.group(1) if json_match else '{"adjustments": []}'

    try:
        parsed = json.loads(json_str)
        adjustments = parsed.get("adjustments", [])
    except json.JSONDecodeError:
        adjustments = []

    # Filter to only high/medium confidence adjustments
    applicable = [a for a in adjustments if a.get("confidence") in ("high", "medium")]

    if not applicable:
        return {
            "adjustments": adjustments,
            "applicable_adjustments": [],
            "adjusted_assumptions": assumptions,
            "original_results": initial_results,
            "adjusted_results": initial_results,
            "any_changes": False,
        }

    # Apply adjustments to a copy of assumptions
    adjusted_assumptions = copy.deepcopy(assumptions)

    for adj in applicable:
        key_path = adj.get("assumption_key", "")
        revised = adj.get("revised_value")
        if not key_path or revised is None:
            continue

        # Navigate and update nested dict by dot-path.
        # Supports two key_path formats:
        #   "zoning.parking_1br"         → set ["zoning"]["parking_1br"]["value"]
        #   "zoning.parking_1br.value"   → same result (leaf ".value" handled explicitly)
        parts = key_path.split(".")
        # Strip trailing ".value" — we always write to the "value" field of a research dict
        if parts and parts[-1] == "value":
            parts = parts[:-1]
        d = adjusted_assumptions
        try:
            for part in parts[:-1]:
                if isinstance(d, dict):
                    if part not in d:
                        d[part] = {}
                    d = d[part]
            last = parts[-1]
            if isinstance(d, dict):
                if last in d and isinstance(d[last], dict):
                    # Update the value field of the existing research dict
                    d[last]["value"] = revised
                    d[last]["notes"] = f"Adjusted by zoning pass: {adj.get('description', '')}. Original: {d[last].get('notes', '')}"
                else:
                    # Create a new research dict entry
                    d[last] = {
                        "value": revised,
                        "unit": adj.get("unit", ""),
                        "source_url": adj.get("source_url", ""),
                        "source_name": adj.get("source_name", ""),
                        "date_retrieved": TODAY,
                        "notes": f"Adjusted by zoning pass: {adj.get('description', '')}",
                    }
        except (KeyError, TypeError):
            pass  # Skip if path is invalid

    # Re-run calculations with adjusted assumptions
    try:
        adjusted_results = run_calculations(user_inputs, adjusted_assumptions)
    except Exception as e:
        adjusted_results = initial_results  # Fall back to original if re-run fails

    # Add delta info to each applicable adjustment
    orig_roc = initial_results.get("return_on_cost", 0)
    adj_roc = adjusted_results.get("return_on_cost", 0)

    for adj in applicable:
        adj["roc_impact"] = adj_roc - orig_roc  # positive = improved feasibility

    return {
        "adjustments": adjustments,
        "applicable_adjustments": applicable,
        "adjusted_assumptions": adjusted_assumptions,
        "original_results": initial_results,
        "adjusted_results": adjusted_results,
        "any_changes": len(applicable) > 0,
        "roc_delta": adj_roc - orig_roc,
        "original_roc": orig_roc,
        "adjusted_roc": adj_roc,
    }
