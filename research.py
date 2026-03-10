"""
research.py — AI Research Layer
Uses Anthropic API with web_search tool to populate all financial assumptions.
Results are structured dicts with: value, unit, source_url, source_name, date_retrieved, notes.
"""

import json
import re
import time
from datetime import date
from typing import Optional
import os
import anthropic

MODEL = "claude-sonnet-4-20250514"

def _get_client():
    key = os.environ.get("ANTHROPIC_API_KEY")
    return anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()


SYSTEM_BASE = """You are a real estate research assistant. Your job is to find accurate, current financial data for real estate development feasibility analysis.

Rules:
- Prioritize government websites, then established data providers (CoStar, Lightcast, Redfin, Zillow, CBRE, JLL), then reputable industry sources.
- Only use sources updated in 2025 or 2026.
- Return ONLY valid JSON — no preamble, no markdown, no explanation outside the JSON.
- If a value cannot be found with confidence, set "value" to null and explain in "notes".
- NEVER fabricate a number — always cite the exact URL you found it at.
- For each data point return: {"value": <number or null>, "unit": "<unit string>", "source_url": "<full URL>", "source_name": "<site name>", "date_retrieved": "<YYYY-MM-DD>", "notes": "<any caveats>"}
"""

TODAY = date.today().isoformat()


SYSTEM_VALIDATE = """You are an address verification specialist. Your ONLY job is to confirm whether a specific street address or parcel actually exists.

Rules:
- Search for the exact address using mapping services, county assessor sites, or government records.
- Return valid=true ONLY if you find the specific building number + street in a real, verifiable source.
- A city name or neighborhood alone is NOT sufficient — the specific address must be found.
- If the address appears fabricated, nonsensical, or cannot be found in any real source, return valid=false.
- Return ONLY valid JSON. No preamble.
"""


def validate_address(site_identifier: str, location: str) -> dict:
    """
    Verifies the address exists using 1 web search.
    Returns {"valid": True, "found": "description of what was found"}
         or {"valid": False, "reason": "why it wasn't found"}.
    """
    prompt = f"""
Search to verify this address exists: {site_identifier}, {location}

Search for it on Google Maps, a county assessor site, or any government/mapping source.

Return JSON:
{{
  "valid": <true if the specific address was found in a real source, false otherwise>,
  "found": "<what you found, e.g. 'Confirmed: 123 Main St exists per Cook County Assessor' or 'Address not found in any source'>",
  "source_url": "<URL where it was confirmed, or null>"
}}

Only return valid=true if the specific street number and street name appear in a real record.
"""
    client = _get_client()
    tools = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 1}]
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=200,
            system=SYSTEM_VALIDATE,
            tools=tools,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception:
        # On any error, fail open so a network hiccup doesn't block the user
        return {"valid": True, "found": "Validation skipped due to API error", "source_url": None}

    text_parts = [b.text for b in response.content if hasattr(b, "text")]
    full_text = "\n".join(text_parts).strip()

    json_match = re.search(r"```(?:json)?\s*([\s\S]+?)```", full_text)
    if json_match:
        json_str = json_match.group(1).strip()
    else:
        json_match = re.search(r"(\{[\s\S]+\})", full_text)
        json_str = json_match.group(1) if json_match else full_text

    try:
        result = json.loads(json_str)
        return {
            "valid": bool(result.get("valid", False)),
            "found": result.get("found", ""),
            "source_url": result.get("source_url"),
        }
    except (json.JSONDecodeError, AttributeError):
        return {"valid": False, "found": "Could not parse validation response", "source_url": None}


def _run_research(prompt: str, system_extra: str = "", web_search: bool = True,
                  max_uses: int = 1, max_tokens: int = 1200) -> dict:
    """Execute a Claude call and parse JSON response.
    web_search=False uses Claude's built-in knowledge only (much faster, ~3-5s vs ~20-25s).
    Retries up to 4 times with exponential backoff on rate limit errors.
    """
    system = SYSTEM_BASE + ("\n\n" + system_extra if system_extra else "")
    tools = [{"type": "web_search_20250305", "name": "web_search", "max_uses": max_uses}] if web_search else []

    messages = [{"role": "user", "content": prompt}]
    client = _get_client()

    max_retries = 4
    for attempt in range(max_retries):
        try:
            kwargs = dict(
                model=MODEL,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
            )
            if tools:
                kwargs["tools"] = tools
            response = client.messages.create(**kwargs)
            break  # success
        except anthropic.RateLimitError as e:
            wait = 65 + 30 * attempt  # 65, 95, 125, 155 seconds
            if attempt < max_retries - 1:
                time.sleep(wait)
            else:
                raise e

    # Collect all text blocks from the response
    text_parts = []
    for block in response.content:
        if hasattr(block, "text"):
            text_parts.append(block.text)

    full_text = "\n".join(text_parts).strip()

    # Extract JSON — handle both bare JSON and code-fenced JSON
    json_match = re.search(r"```(?:json)?\s*([\s\S]+?)```", full_text)
    if json_match:
        json_str = json_match.group(1).strip()
    else:
        json_match = re.search(r"(\{[\s\S]+\}|\[[\s\S]+\])", full_text)
        json_str = json_match.group(1) if json_match else full_text

    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return {
            "value": None,
            "unit": None,
            "source_url": None,
            "source_name": None,
            "date_retrieved": TODAY,
            "notes": f"Failed to parse JSON response. Raw: {full_text[:500]}",
        }


def research_zoning(location: str, building_type: str) -> dict:
    """
    Returns typical zoning parameters from Claude's training data.
    No web search — uses known zoning norms for the city/region.
    """
    prompt = f"""
Based on your knowledge of typical US zoning codes, provide base zoning parameters for a {building_type} development in {location}. Use the most common zoning district that would apply to this building type in this city.

Return a JSON object:
{{
  "max_far": {{"value": <number>, "unit": "ratio", "source_url": null, "source_name": "typical municipal code", "date_retrieved": "{TODAY}", "notes": "typical base zoning for this city/building type"}},
  "max_height_stories": {{"value": <number>, "unit": "stories", "source_url": null, "source_name": "typical municipal code", "date_retrieved": "{TODAY}", "notes": ""}},
  "parking_studio": {{"value": <number>, "unit": "spaces/unit", "source_url": null, "source_name": "typical municipal code", "date_retrieved": "{TODAY}", "notes": ""}},
  "parking_1br": {{"value": <number>, "unit": "spaces/unit", "source_url": null, "source_name": "typical municipal code", "date_retrieved": "{TODAY}", "notes": ""}},
  "parking_2br": {{"value": <number>, "unit": "spaces/unit", "source_url": null, "source_name": "typical municipal code", "date_retrieved": "{TODAY}", "notes": ""}},
  "parking_3br": {{"value": <number>, "unit": "spaces/unit", "source_url": null, "source_name": "typical municipal code", "date_retrieved": "{TODAY}", "notes": ""}},
  "setback_front_ft": {{"value": <number>, "unit": "feet", "source_url": null, "source_name": "typical municipal code", "date_retrieved": "{TODAY}", "notes": ""}},
  "setback_side_ft": {{"value": <number>, "unit": "feet", "source_url": null, "source_name": "typical municipal code", "date_retrieved": "{TODAY}", "notes": ""}},
  "setback_rear_ft": {{"value": <number>, "unit": "feet", "source_url": null, "source_name": "typical municipal code", "date_retrieved": "{TODAY}", "notes": ""}}
}}
"""
    return _run_research(prompt, web_search=False)


def research_land_costs(location: str, building_type: str) -> dict:
    """
    Returns land cost estimates from Claude's training data.
    No web search — uses known land value ranges for the market.
    """
    prompt = f"""
Based on your knowledge of US land markets, provide typical land cost estimates for a {building_type} development site in {location} as of 2024-2025.

Return a JSON object:
{{
  "land_cost_per_sf": {{"value": <number>, "unit": "$/land SF", "source_url": null, "source_name": "market estimate", "date_retrieved": "{TODAY}", "notes": "typical range for this market and building type"}},
  "land_cost_per_acre": {{"value": <number>, "unit": "$/acre", "source_url": null, "source_name": "market estimate", "date_retrieved": "{TODAY}", "notes": ""}}
}}
"""
    return _run_research(prompt, web_search=False)


def research_construction_costs(location: str, building_type: str) -> dict:
    """
    Returns hard cost benchmarks ($/GSF) from Claude's training data.
    No web search — construction costs are stable enough for regional estimates.
    """
    prompt = f"""
Based on your knowledge of US construction costs, provide hard cost benchmarks for {building_type} in {location} or its metro area as of 2024-2025. Use RSMeans regional data and typical developer benchmarks you know.

Return a JSON object:
{{
  "hard_cost_per_gsf": {{"value": <number>, "unit": "$/GSF", "source_url": null, "source_name": "RSMeans / industry benchmark", "date_retrieved": "{TODAY}", "notes": "regional estimate based on city cost index"}},
  "parking_structured_per_space": {{"value": <number>, "unit": "$/space", "source_url": null, "source_name": "industry benchmark", "date_retrieved": "{TODAY}", "notes": "structured/podium parking"}},
  "parking_surface_per_space": {{"value": <number>, "unit": "$/space", "source_url": null, "source_name": "industry benchmark", "date_retrieved": "{TODAY}", "notes": "surface parking"}}
}}
"""
    return _run_research(prompt, web_search=False)


def research_market_rents(location: str, building_type: str, unit_mix: dict) -> dict:
    """
    Search Apartments.com, Zillow, Redfin, CoStar for current asking rents.
    Returns weighted average $/NSF/month by bedroom type.
    Cross-references at least two sources.
    """
    unit_types = [ut for ut, pct in unit_mix.items() if pct > 0]
    unit_list = ", ".join(unit_types) if unit_types else "Studio, 1BR, 2BR, 3BR"

    prompt = f"""
Based on your knowledge of US rental markets, provide typical market-rate rents for {building_type} apartments in {location} as of 2024-2025.

Return a JSON object:
{{
  "studio": {{"value": <monthly rent $>, "unit": "$/month", "source_url": null, "source_name": "market estimate", "date_retrieved": "{TODAY}", "notes": "typical for this submarket"}},
  "1br": {{"value": <monthly rent $>, "unit": "$/month", "source_url": null, "source_name": "market estimate", "date_retrieved": "{TODAY}", "notes": ""}},
  "2br": {{"value": <monthly rent $>, "unit": "$/month", "source_url": null, "source_name": "market estimate", "date_retrieved": "{TODAY}", "notes": ""}},
  "3br": {{"value": <monthly rent $>, "unit": "$/month", "source_url": null, "source_name": "market estimate", "date_retrieved": "{TODAY}", "notes": ""}},
  "4br": {{"value": <monthly rent $>, "unit": "$/month", "source_url": null, "source_name": "market estimate", "date_retrieved": "{TODAY}", "notes": ""}},
  "studio_avg_sf": {{"value": <SF>, "unit": "SF", "source_url": null, "source_name": "market estimate", "date_retrieved": "{TODAY}", "notes": ""}},
  "1br_avg_sf": {{"value": <SF>, "unit": "SF", "source_url": null, "source_name": "market estimate", "date_retrieved": "{TODAY}", "notes": ""}},
  "2br_avg_sf": {{"value": <SF>, "unit": "SF", "source_url": null, "source_name": "market estimate", "date_retrieved": "{TODAY}", "notes": ""}},
  "3br_avg_sf": {{"value": <SF>, "unit": "SF", "source_url": null, "source_name": "market estimate", "date_retrieved": "{TODAY}", "notes": ""}},
  "4br_avg_sf": {{"value": <SF>, "unit": "SF", "source_url": null, "source_name": "market estimate", "date_retrieved": "{TODAY}", "notes": ""}},
  "vacancy_rate": {{"value": <decimal e.g. 0.05>, "unit": "decimal", "source_url": null, "source_name": "market estimate", "date_retrieved": "{TODAY}", "notes": "submarket vacancy rate"}}
}}
"""
    return _run_research(prompt, web_search=False)


def research_cap_rates(location: str, use_type: str) -> dict:
    """
    Search CoStar, CBRE, JLL, Marcus & Millichap for current cap rates.
    Returns cap rate and source for asset type in submarket.
    """
    prompt = f"""
Based on your knowledge of US real estate markets, provide typical cap rates for {use_type} properties in {location} as of 2024-2025.

Return a JSON object:
{{
  "cap_rate": {{"value": <decimal e.g. 0.055>, "unit": "decimal", "source_url": null, "source_name": "market estimate", "date_retrieved": "{TODAY}", "notes": "typical for this market and asset class"}},
  "cap_rate_range_low": {{"value": <decimal>, "unit": "decimal", "source_url": null, "source_name": "market estimate", "date_retrieved": "{TODAY}", "notes": ""}},
  "cap_rate_range_high": {{"value": <decimal>, "unit": "decimal", "source_url": null, "source_name": "market estimate", "date_retrieved": "{TODAY}", "notes": ""}}
}}
"""
    return _run_research(prompt, web_search=False)


def research_interest_rates() -> dict:
    """
    Always re-fetched. Searches Federal Reserve for current SOFR/federal funds rate.
    Returns current rate + typical construction loan spread (250bps) and permanent loan spread.
    """
    prompt = f"""
Based on your knowledge of US interest rates and lending markets as of 2024-2025, provide current rate estimates for multifamily construction and permanent loans.

Return a JSON object:
{{
  "sofr_rate": {{"value": <decimal e.g. 0.053>, "unit": "decimal", "source_url": null, "source_name": "Federal Reserve estimate", "date_retrieved": "{TODAY}", "notes": "approximate SOFR as of training data"}},
  "federal_funds_rate": {{"value": <decimal>, "unit": "decimal", "source_url": null, "source_name": "Federal Reserve estimate", "date_retrieved": "{TODAY}", "notes": ""}},
  "construction_loan_spread_bps": {{"value": 250, "unit": "basis points", "source_url": null, "source_name": "industry benchmark", "date_retrieved": "{TODAY}", "notes": "typical spread over SOFR"}},
  "construction_loan_rate": {{"value": <sofr + 0.025>, "unit": "decimal", "source_url": null, "source_name": "industry benchmark", "date_retrieved": "{TODAY}", "notes": "SOFR + 250bps"}},
  "perm_loan_spread_bps": {{"value": <number>, "unit": "basis points", "source_url": null, "source_name": "industry benchmark", "date_retrieved": "{TODAY}", "notes": "typical spread for permanent multifamily loan"}},
  "perm_loan_rate": {{"value": <decimal>, "unit": "decimal", "source_url": null, "source_name": "industry benchmark", "date_retrieved": "{TODAY}", "notes": "SOFR + permanent spread"}}
}}
"""
    return _run_research(prompt, web_search=False)


def research_tax_rates(location: str) -> dict:
    """
    Returns property tax estimates from Claude's training data.
    No web search — uses known effective rates by state/county.
    """
    prompt = f"""
Based on your knowledge of US property tax rates, provide the typical effective property tax rate for commercial/multifamily real estate in {location} as of 2024-2025.

Return a JSON object:
{{
  "effective_tax_rate": {{"value": <decimal e.g. 0.012>, "unit": "decimal (of assessed value)", "source_url": null, "source_name": "state/county rate estimate", "date_retrieved": "{TODAY}", "notes": "typical effective rate for this jurisdiction"}},
  "mill_rate": {{"value": <mills or null>, "unit": "mills ($/1000 assessed value)", "source_url": null, "source_name": "state/county rate estimate", "date_retrieved": "{TODAY}", "notes": ""}},
  "assessment_ratio": {{"value": <decimal or null>, "unit": "decimal (assessed/market value)", "source_url": null, "source_name": "state/county rate estimate", "date_retrieved": "{TODAY}", "notes": ""}}
}}
"""
    return _run_research(prompt, web_search=False)


def research_ami_and_affordable_rents(location: str, ami_levels: list) -> dict:
    """
    Search HUD income limits (huduser.gov) for the relevant metro area.
    Returns household AMI by size and max rents at each AMI level.
    ami_levels: list of ints, e.g. [30, 50, 60, 80]
    """
    ami_str = ", ".join(f"{a}% AMI" for a in ami_levels)
    prompt = f"""
Search HUD's income limits database at huduser.gov for the current (2025) Area Median Income (AMI) limits for {location} or its HUD metro area.

I need income limits and maximum affordable rents for: {ami_str}

Maximum affordable rent = (AMI × income_limit_percentage × 0.30) / 12
Use 3-person household income as the standard for computing rents (HUD standard for 1BR).

Return a JSON object with a key for each AMI level:
{{
  "metro_area": "...",
  "median_family_income": {{"value": <$>, "unit": "$/year", "source_url": "https://www.huduser.gov/...", "source_name": "HUD", "date_retrieved": "{TODAY}", "notes": ""}},
  "ami_30": {{
    "income_limit_1person": {{"value": <$>, "unit": "$/year", ...}},
    "income_limit_4person": {{"value": <$>, "unit": "$/year", ...}},
    "max_rent_studio": {{"value": <$>, "unit": "$/month", ...}},
    "max_rent_1br": {{"value": <$>, "unit": "$/month", ...}},
    "max_rent_2br": {{"value": <$>, "unit": "$/month", ...}},
    "max_rent_3br": {{"value": <$>, "unit": "$/month", ...}}
  }},
  "ami_50": {{ ... }},
  "ami_60": {{ ... }},
  "ami_80": {{ ... }}
}}

Only include AMI levels from: {ami_str}

"""
    return _run_research(prompt, web_search=False)


def research_opex_benchmarks(use_type: str, building_type: str) -> dict:
    """
    Returns opex benchmarks from Claude's training data (NMHC/IREM industry standards).
    No web search — these are stable industry benchmarks.
    """
    prompt = f"""
Based on your knowledge of NMHC and IREM industry benchmarks, provide operating expense estimates for {use_type} {building_type} multifamily properties as of 2024-2025.

Return a JSON object:
{{
  "total_opex_per_unit_year": {{"value": <number>, "unit": "$/unit/year", "source_url": null, "source_name": "NMHC/IREM benchmark", "date_retrieved": "{TODAY}", "notes": "includes management, maintenance, insurance, admin"}},
  "management_fee_pct_egi": {{"value": <decimal e.g. 0.04>, "unit": "decimal (% of EGI)", "source_url": null, "source_name": "NMHC/IREM benchmark", "date_retrieved": "{TODAY}", "notes": ""}},
  "maintenance_per_unit_year": {{"value": <number>, "unit": "$/unit/year", "source_url": null, "source_name": "NMHC/IREM benchmark", "date_retrieved": "{TODAY}", "notes": ""}},
  "insurance_per_unit_year": {{"value": <number>, "unit": "$/unit/year", "source_url": null, "source_name": "NMHC/IREM benchmark", "date_retrieved": "{TODAY}", "notes": ""}},
  "admin_per_unit_year": {{"value": <number>, "unit": "$/unit/year", "source_url": null, "source_name": "NMHC/IREM benchmark", "date_retrieved": "{TODAY}", "notes": "payroll, leasing, G&A"}},
  "capex_reserve_per_unit_year": {{"value": <number>, "unit": "$/unit/year", "source_url": null, "source_name": "NMHC/IREM benchmark", "date_retrieved": "{TODAY}", "notes": "replacement reserve"}}
}}
"""
    return _run_research(prompt, web_search=False)


def research_employment_and_demand(location: str) -> dict:
    """
    Returns employment/demand context from Claude's training data.
    No web search — uses known economic profile of the metro area.
    """
    prompt = f"""
Based on your knowledge, provide employment and economic demand context for {location} or its metro area as of 2024-2025.

Return a JSON object:
{{
  "top_sectors": [
    {{"sector": "...", "employment_count": null, "source_url": null, "source_name": "BLS/Lightcast estimate", "date_retrieved": "{TODAY}", "notes": ""}}
  ],
  "job_growth_rate_annual": {{"value": <decimal e.g. 0.02>, "unit": "decimal (annual %)", "source_url": null, "source_name": "BLS estimate", "date_retrieved": "{TODAY}", "notes": "approximate"}},
  "unemployment_rate": {{"value": <decimal>, "unit": "decimal", "source_url": null, "source_name": "BLS estimate", "date_retrieved": "{TODAY}", "notes": "approximate"}},
  "median_household_income": {{"value": <$>, "unit": "$/year", "source_url": null, "source_name": "Census/ACS estimate", "date_retrieved": "{TODAY}", "notes": "approximate"}},
  "median_wage": {{"value": <$>, "unit": "$/year", "source_url": null, "source_name": "BLS estimate", "date_retrieved": "{TODAY}", "notes": "all occupations"}},
  "notable_employers": [
    {{"name": "...", "note": "major employer", "source_url": null, "date_retrieved": "{TODAY}"}}
  ],
  "demand_narrative": {{"value": "...", "unit": "text", "source_url": null, "source_name": "market knowledge", "date_retrieved": "{TODAY}", "notes": "1-2 sentence summary"}}
}}
"""
    return _run_research(prompt, web_search=False)


def research_for_sale_comps(location: str, building_type: str) -> dict:
    """
    Called only when use type is For-Sale Condo or Mixed-Use.
    Returns median sale price/SF, days on market, absorption rate.
    """
    prompt = f"""
Based on your knowledge of US for-sale residential markets, provide typical condo/townhome sale price benchmarks for {building_type} in {location} as of 2024-2025.

Return a JSON object:
{{
  "median_sale_price_per_sf": {{"value": <number>, "unit": "$/SF", "source_url": null, "source_name": "market estimate", "date_retrieved": "{TODAY}", "notes": "typical for this submarket"}},
  "median_sale_price": {{"value": <number>, "unit": "$", "source_url": null, "source_name": "market estimate", "date_retrieved": "{TODAY}", "notes": ""}},
  "median_days_on_market": {{"value": <number>, "unit": "days", "source_url": null, "source_name": "market estimate", "date_retrieved": "{TODAY}", "notes": ""}},
  "absorption_rate_units_per_month": {{"value": <number>, "unit": "units/month", "source_url": null, "source_name": "market estimate", "date_retrieved": "{TODAY}", "notes": ""}},
  "profit_margin_benchmark": {{"value": <decimal e.g. 0.18>, "unit": "decimal", "source_url": null, "source_name": "industry benchmark", "date_retrieved": "{TODAY}", "notes": "typical developer margin"}}
}}
"""
    return _run_research(prompt, web_search=False)


SYSTEM_PARCEL = """You are a property records lookup specialist. Your ONLY job is to retrieve data directly from official county assessor or city auditor websites.

Rules:
- ONLY search official government assessor/auditor/treasurer sites for the relevant county or city. Do NOT search Zillow, Redfin, news sites, or any non-government source.
- If you cannot find the parcel on an official assessor/auditor site, set ALL values to null and set "notes" to "Not found on official assessor/auditor records".
- Do NOT estimate, infer, or fabricate any values.
- Return ONLY valid JSON — no preamble, no markdown.
"""


def research_parcel(location: str, site_identifier: str) -> dict:
    """
    Look up official parcel data from county assessor / city auditor only.
    Returns parcel area, existing improvements, zoning, and assessed value.
    If not found, all values are null with a "not found" note.
    """
    prompt = f"""
Look up official property records for: {site_identifier}, {location}

ONLY search the county assessor or city auditor website for this address. For example:
- Cook County → cookcountyassessor.com
- Los Angeles County → assessor.lacounty.gov
- Search: "{location} county assessor" or "{location} city auditor property search" to find the right site.

If you find the parcel on an official assessor/auditor site, return:
{{
  "parcel_area_acres": {{"value": <number or null>, "unit": "acres", "source_url": "<assessor URL>", "source_name": "<assessor site name>", "date_retrieved": "{TODAY}", "notes": ""}},
  "parcel_area_sf": {{"value": <number or null>, "unit": "SF", "source_url": "<assessor URL>", "source_name": "<assessor site name>", "date_retrieved": "{TODAY}", "notes": ""}},
  "current_land_use": {{"value": "<description or null>", "unit": "text", "source_url": "<assessor URL>", "source_name": "<assessor site name>", "date_retrieved": "{TODAY}", "notes": ""}},
  "current_zoning": {{"value": "<zoning code or null>", "unit": "text", "source_url": "<assessor URL>", "source_name": "<assessor site name>", "date_retrieved": "{TODAY}", "notes": ""}},
  "existing_building_sf": {{"value": <number or 0 if vacant>, "unit": "SF", "source_url": "<assessor URL>", "source_name": "<assessor site name>", "date_retrieved": "{TODAY}", "notes": "0 if vacant land"}},
  "existing_building_stories": {{"value": <number or 0>, "unit": "stories", "source_url": "<assessor URL>", "source_name": "<assessor site name>", "date_retrieved": "{TODAY}", "notes": ""}},
  "existing_building_year_built": {{"value": <year or null>, "unit": "year", "source_url": "<assessor URL>", "source_name": "<assessor site name>", "date_retrieved": "{TODAY}", "notes": "null if vacant land"}},
  "assessed_value_land": {{"value": <number or null>, "unit": "$", "source_url": "<assessor URL>", "source_name": "<assessor site name>", "date_retrieved": "{TODAY}", "notes": ""}},
  "assessed_value_total": {{"value": <number or null>, "unit": "$", "source_url": "<assessor URL>", "source_name": "<assessor site name>", "date_retrieved": "{TODAY}", "notes": ""}},
  "demolition_required": {{"value": <true or false>, "unit": "boolean", "source_url": "<assessor URL>", "source_name": "<assessor site name>", "date_retrieved": "{TODAY}", "notes": ""}}
}}

If the parcel CANNOT be found on an official assessor/auditor site, return the same JSON structure with ALL values set to null and each "notes" field set to "Not found on official assessor/auditor records".

Search: "{location} county assessor property search"
"""
    tools = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 1}]
    system = SYSTEM_PARCEL
    messages = [{"role": "user", "content": prompt}]
    client = _get_client()

    max_retries = 4
    for attempt in range(max_retries):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=2000,
                system=system,
                tools=tools,
                messages=messages,
            )
            break
        except anthropic.RateLimitError as e:
            wait = 65 + 30 * attempt
            if attempt < max_retries - 1:
                time.sleep(wait)
            else:
                raise e

    text_parts = []
    for block in response.content:
        if hasattr(block, "text"):
            text_parts.append(block.text)
    full_text = "\n".join(text_parts).strip()

    json_match = re.search(r"```(?:json)?\s*([\s\S]+?)```", full_text)
    if json_match:
        json_str = json_match.group(1).strip()
    else:
        json_match = re.search(r"(\{[\s\S]+\}|\[[\s\S]+\])", full_text)
        json_str = json_match.group(1) if json_match else full_text

    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        not_found_note = "Not found on official assessor/auditor records"
        return {k: {"value": None, "unit": "", "source_url": None, "source_name": None,
                    "date_retrieved": TODAY, "notes": not_found_note}
                for k in ["parcel_area_acres", "parcel_area_sf", "current_land_use",
                           "current_zoning", "existing_building_sf", "existing_building_stories",
                           "existing_building_year_built", "assessed_value_land",
                           "assessed_value_total", "demolition_required"]}


def research_lihtc_rules(state: str, lihtc_type: str) -> dict:
    """
    Only called when LIHTC is selected.
    Searches state housing finance agency for current QAP rules.
    lihtc_type: "4%" or "9%"
    """
    prompt = f"""
Based on your knowledge of LIHTC programs, provide typical parameters for {lihtc_type} tax credits in {state} as of 2024-2025.

Return a JSON object:
{{
  "state_hfa_name": "...",
  "credit_rate": {{"value": <decimal e.g. 0.04 or null>, "unit": "decimal (annual credit rate)", "source_url": "...", "source_name": "...", "date_retrieved": "{TODAY}", "notes": "4% or 9% credit rate, IRS or state-set"}},
  "qualified_basis_pct": {{"value": <decimal e.g. 1.0 or null>, "unit": "decimal", "source_url": "...", "source_name": "...", "date_retrieved": "{TODAY}", "notes": "eligible basis percentage"}},
  "investor_pricing_per_credit": {{"value": <$ e.g. 0.85 or null>, "unit": "$/credit", "source_url": "...", "source_name": "...", "date_retrieved": "{TODAY}", "notes": "current equity investor pricing"}},
  "per_capita_cap": {{"value": <$ or null>, "unit": "$/capita statewide", "source_url": "...", "source_name": "...", "date_retrieved": "{TODAY}", "notes": "IRS per-capita allocation limit"}},
  "project_credit_cap": {{"value": <$ or null>, "unit": "$/project", "source_url": "...", "source_name": "...", "date_retrieved": "{TODAY}", "notes": "state-imposed per-project limit"}},
  "application_cycle": {{"value": "...", "unit": "text", "source_url": "...", "source_name": "...", "date_retrieved": "{TODAY}", "notes": "when applications are accepted"}}
}}

"""
    return _run_research(prompt, web_search=False)


# ---------------------------------------------------------------------------
# Batched research functions — 2 calls instead of 10
# ---------------------------------------------------------------------------

def research_market_batch(location: str, building_type: str, use_type: str, unit_mix: dict) -> dict:
    """
    Single call covering all location-specific market data.
    Uses up to 3 web searches: rents, zoning, cap rates/land.
    If a search finds nothing quickly, falls back to training data immediately.
    Returns dict with keys: rents, cap_rates, zoning, land, tax_rates.
    """
    unit_list = ", ".join(ut for ut, pct in unit_mix.items() if pct > 0) or "Studio, 1BR, 2BR, 3BR"
    prompt = f"""
Research market data for a {building_type} {use_type} development in {location} as of {TODAY}.

Perform up to 3 focused searches — stop each search as soon as you have the data; do not retry if a search yields no results, just use your best estimate:
1. "{location} {building_type} apartments rent average" — get current asking rents
2. "{location} zoning code {building_type} FAR parking" — get zoning parameters
3. "{location} multifamily cap rate 2024 2025" — get cap rates and land costs

For each value: if found via search, set source_url to the real URL; if using an estimate, set source_url to null.

Return JSON with these five keys (fill every field — never omit a key):
{{"rents":{{"studio":{{"value":<$>,"unit":"$/month","source_url":<url>,"source_name":"<site>","date_retrieved":"{TODAY}","notes":""}},"1br":{{"value":<$>,"unit":"$/month","source_url":<url>,"source_name":"<site>","date_retrieved":"{TODAY}","notes":""}},"2br":{{"value":<$>,"unit":"$/month","source_url":<url>,"source_name":"<site>","date_retrieved":"{TODAY}","notes":""}},"3br":{{"value":<$>,"unit":"$/month","source_url":<url>,"source_name":"<site>","date_retrieved":"{TODAY}","notes":""}},"4br":{{"value":<$>,"unit":"$/month","source_url":null,"source_name":"estimate","date_retrieved":"{TODAY}","notes":""}},"studio_avg_sf":{{"value":<SF>,"unit":"SF","source_url":null,"source_name":"estimate","date_retrieved":"{TODAY}","notes":""}},"1br_avg_sf":{{"value":<SF>,"unit":"SF","source_url":null,"source_name":"estimate","date_retrieved":"{TODAY}","notes":""}},"2br_avg_sf":{{"value":<SF>,"unit":"SF","source_url":null,"source_name":"estimate","date_retrieved":"{TODAY}","notes":""}},"3br_avg_sf":{{"value":<SF>,"unit":"SF","source_url":null,"source_name":"estimate","date_retrieved":"{TODAY}","notes":""}},"4br_avg_sf":{{"value":<SF>,"unit":"SF","source_url":null,"source_name":"estimate","date_retrieved":"{TODAY}","notes":""}},"vacancy_rate":{{"value":<0.05>,"unit":"decimal","source_url":null,"source_name":"estimate","date_retrieved":"{TODAY}","notes":""}}}},"cap_rates":{{"cap_rate":{{"value":<decimal>,"unit":"decimal","source_url":<url>,"source_name":"<site>","date_retrieved":"{TODAY}","notes":""}},"cap_rate_range_low":{{"value":<decimal>,"unit":"decimal","source_url":<url>,"source_name":"<site>","date_retrieved":"{TODAY}","notes":""}},"cap_rate_range_high":{{"value":<decimal>,"unit":"decimal","source_url":<url>,"source_name":"<site>","date_retrieved":"{TODAY}","notes":""}}}},"zoning":{{"max_far":{{"value":<number>,"unit":"ratio","source_url":<url>,"source_name":"<site>","date_retrieved":"{TODAY}","notes":"district if known"}},"max_height_stories":{{"value":<number>,"unit":"stories","source_url":<url>,"source_name":"<site>","date_retrieved":"{TODAY}","notes":""}},"parking_studio":{{"value":<number>,"unit":"spaces/unit","source_url":<url>,"source_name":"<site>","date_retrieved":"{TODAY}","notes":""}},"parking_1br":{{"value":<number>,"unit":"spaces/unit","source_url":<url>,"source_name":"<site>","date_retrieved":"{TODAY}","notes":""}},"parking_2br":{{"value":<number>,"unit":"spaces/unit","source_url":<url>,"source_name":"<site>","date_retrieved":"{TODAY}","notes":""}},"parking_3br":{{"value":<number>,"unit":"spaces/unit","source_url":<url>,"source_name":"<site>","date_retrieved":"{TODAY}","notes":""}},"setback_front_ft":{{"value":<number>,"unit":"feet","source_url":<url>,"source_name":"<site>","date_retrieved":"{TODAY}","notes":""}},"setback_side_ft":{{"value":<number>,"unit":"feet","source_url":<url>,"source_name":"<site>","date_retrieved":"{TODAY}","notes":""}},"setback_rear_ft":{{"value":<number>,"unit":"feet","source_url":<url>,"source_name":"<site>","date_retrieved":"{TODAY}","notes":""}}}},"land":{{"land_cost_per_sf":{{"value":<number>,"unit":"$/land SF","source_url":<url>,"source_name":"<site>","date_retrieved":"{TODAY}","notes":""}},"land_cost_per_acre":{{"value":<number>,"unit":"$/acre","source_url":<url>,"source_name":"<site>","date_retrieved":"{TODAY}","notes":""}}}},"tax_rates":{{"effective_tax_rate":{{"value":<decimal>,"unit":"decimal","source_url":null,"source_name":"estimate","date_retrieved":"{TODAY}","notes":""}},"mill_rate":{{"value":null,"unit":"mills","source_url":null,"source_name":"estimate","date_retrieved":"{TODAY}","notes":""}},"assessment_ratio":{{"value":null,"unit":"decimal","source_url":null,"source_name":"estimate","date_retrieved":"{TODAY}","notes":""}}}}}}
Unit types: {unit_list}
"""
    return _run_research(prompt, web_search=True, max_uses=3, max_tokens=2000)


def research_general_batch(location: str, building_type: str, use_type: str) -> dict:
    """
    Single call: construction, opex, interest_rates.
    No web search — uses Claude's training knowledge.
    Returns dict with keys: construction, opex, interest_rates.
    """
    prompt = f"""
Based on your knowledge, provide financial benchmarks for a {building_type} {use_type} development in {location} as of 2024-2025.

Return a JSON object with exactly these three keys:
{{
  "construction": {{
    "hard_cost_per_gsf":            {{"value": <$/GSF>,  "unit": "$/GSF",   "source_url": null, "source_name": "RSMeans/industry", "date_retrieved": "{TODAY}", "notes": "regional estimate"}},
    "parking_structured_per_space": {{"value": <$/space>,"unit": "$/space", "source_url": null, "source_name": "industry",         "date_retrieved": "{TODAY}", "notes": "structured/podium"}},
    "parking_surface_per_space":    {{"value": <$/space>,"unit": "$/space", "source_url": null, "source_name": "industry",         "date_retrieved": "{TODAY}", "notes": "surface parking"}}
  }},
  "opex": {{
    "total_opex_per_unit_year":    {{"value": <number>, "unit": "$/unit/year",       "source_url": null, "source_name": "NMHC/IREM", "date_retrieved": "{TODAY}", "notes": ""}},
    "management_fee_pct_egi":      {{"value": <decimal>,"unit": "decimal (% EGI)",   "source_url": null, "source_name": "NMHC/IREM", "date_retrieved": "{TODAY}", "notes": ""}},
    "maintenance_per_unit_year":   {{"value": <number>, "unit": "$/unit/year",       "source_url": null, "source_name": "NMHC/IREM", "date_retrieved": "{TODAY}", "notes": ""}},
    "insurance_per_unit_year":     {{"value": <number>, "unit": "$/unit/year",       "source_url": null, "source_name": "NMHC/IREM", "date_retrieved": "{TODAY}", "notes": ""}},
    "admin_per_unit_year":         {{"value": <number>, "unit": "$/unit/year",       "source_url": null, "source_name": "NMHC/IREM", "date_retrieved": "{TODAY}", "notes": ""}},
    "capex_reserve_per_unit_year": {{"value": <number>, "unit": "$/unit/year",       "source_url": null, "source_name": "NMHC/IREM", "date_retrieved": "{TODAY}", "notes": ""}}
  }},
  "interest_rates": {{
    "sofr_rate":                   {{"value": <decimal>, "unit": "decimal", "source_url": null, "source_name": "Fed estimate", "date_retrieved": "{TODAY}", "notes": "approximate SOFR"}},
    "federal_funds_rate":          {{"value": <decimal>, "unit": "decimal", "source_url": null, "source_name": "Fed estimate", "date_retrieved": "{TODAY}", "notes": ""}},
    "construction_loan_spread_bps":{{"value": 250,       "unit": "bps",    "source_url": null, "source_name": "industry",     "date_retrieved": "{TODAY}", "notes": "typical spread"}},
    "construction_loan_rate":      {{"value": <sofr+0.025>,"unit": "decimal","source_url": null,"source_name": "industry",    "date_retrieved": "{TODAY}", "notes": "SOFR+250bps"}},
    "perm_loan_spread_bps":        {{"value": <number>,  "unit": "bps",    "source_url": null, "source_name": "industry",     "date_retrieved": "{TODAY}", "notes": ""}},
    "perm_loan_rate":              {{"value": <decimal>, "unit": "decimal", "source_url": null, "source_name": "industry",     "date_retrieved": "{TODAY}", "notes": ""}}
  }}
}}
"""
    return _run_research(prompt, web_search=False)
