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


def _run_research(prompt: str, system_extra: str = "") -> dict:
    """Execute a web-search-enabled Claude call and parse JSON response.
    Retries up to 4 times with exponential backoff on rate limit errors.
    """
    system = SYSTEM_BASE + ("\n\n" + system_extra if system_extra else "")
    tools = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}]

    messages = [{"role": "user", "content": prompt}]
    client = _get_client()

    max_retries = 4
    for attempt in range(max_retries):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=3000,
                system=system,
                tools=tools,
                messages=messages,
            )
            break  # success
        except anthropic.RateLimitError as e:
            # Wait long enough to guarantee the rolling 1-minute TPM window resets.
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
        # Try to find raw JSON object or array
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
    Search local zoning code for: maximum FAR, maximum height (stories),
    minimum parking requirements by bedroom type, minimum setbacks.
    Does NOT apply transit-based reductions (handled in zoning_check.py).
    """
    prompt = f"""
Search the municipal code and planning department websites for {location} to find current zoning regulations applicable to a {building_type} development.

Find and return a JSON object with these keys:
{{
  "max_far": {{"value": <number>, "unit": "ratio", "source_url": "...", "source_name": "...", "date_retrieved": "{TODAY}", "notes": "..."}},
  "max_height_stories": {{"value": <number>, "unit": "stories", "source_url": "...", "source_name": "...", "date_retrieved": "{TODAY}", "notes": "..."}},
  "parking_studio": {{"value": <number>, "unit": "spaces/unit", "source_url": "...", "source_name": "...", "date_retrieved": "{TODAY}", "notes": "..."}},
  "parking_1br": {{"value": <number>, "unit": "spaces/unit", "source_url": "...", "source_name": "...", "date_retrieved": "{TODAY}", "notes": "..."}},
  "parking_2br": {{"value": <number>, "unit": "spaces/unit", "source_url": "...", "source_name": "...", "date_retrieved": "{TODAY}", "notes": "..."}},
  "parking_3br": {{"value": <number>, "unit": "spaces/unit", "source_url": "...", "source_name": "...", "date_retrieved": "{TODAY}", "notes": "..."}},
  "setback_front_ft": {{"value": <number>, "unit": "feet", "source_url": "...", "source_name": "...", "date_retrieved": "{TODAY}", "notes": "..."}},
  "setback_side_ft": {{"value": <number>, "unit": "feet", "source_url": "...", "source_name": "...", "date_retrieved": "{TODAY}", "notes": "..."}},
  "setback_rear_ft": {{"value": <number>, "unit": "feet", "source_url": "...", "source_name": "...", "date_retrieved": "{TODAY}", "notes": "..."}}
}}

Search: "{location} zoning code {building_type} parking requirements FAR height limits setbacks"
Also search: "{location} municipal code multifamily development standards"
Do NOT apply any transit-oriented or overlay reductions — return base zoning only.
"""
    return _run_research(prompt)


def research_land_costs(location: str, building_type: str) -> dict:
    """
    Search for recent comparable land sales within ~1 mile of location.
    Returns $/land SF for the relevant building type.
    """
    prompt = f"""
Search for recent (2024-2026) comparable land/lot sales near {location} suitable for {building_type} development.

Search CoStar, LoopNet, Redfin (land/lot listings and sold data), and county transaction records.

Return a JSON object:
{{
  "land_cost_per_sf": {{"value": <number or null>, "unit": "$/land SF", "source_url": "...", "source_name": "...", "date_retrieved": "{TODAY}", "notes": "comparable sales details, number of comps found"}},
  "land_cost_per_acre": {{"value": <number or null>, "unit": "$/acre", "source_url": "...", "source_name": "...", "date_retrieved": "{TODAY}", "notes": "..."}}
}}

Search: "{location} land sale {building_type} site comparable 2024 2025"
Also search: "{location} multifamily development site $/acre $/SF sold"
"""
    return _run_research(prompt)


def research_construction_costs(location: str, building_type: str) -> dict:
    """
    Search for current hard cost benchmarks ($/GSF) for building type in the metro area.
    Uses RSMeans regional data, local permit filings, broker/developer reports 2025-2026.
    """
    prompt = f"""
Search for current construction hard cost benchmarks ($/gross square foot) for {building_type} in {location} or its metro area.

Use RSMeans regional cost data, ENR Building Cost Index, local permit filings, and developer/broker reports from 2025-2026.

Return a JSON object:
{{
  "hard_cost_per_gsf": {{"value": <number or null>, "unit": "$/GSF", "source_url": "...", "source_name": "...", "date_retrieved": "{TODAY}", "notes": "source methodology, year of data"}},
  "parking_structured_per_space": {{"value": <number or null>, "unit": "$/space", "source_url": "...", "source_name": "...", "date_retrieved": "{TODAY}", "notes": "structured/podium parking cost"}},
  "parking_surface_per_space": {{"value": <number or null>, "unit": "$/space", "source_url": "...", "source_name": "...", "date_retrieved": "{TODAY}", "notes": "surface parking cost"}}
}}

Search: "{location} construction cost per square foot {building_type} 2025"
Also search: "RSMeans {building_type} construction cost {location} metro 2025"
Also search: "{location} multifamily construction cost per SF permit 2025 2026"
"""
    return _run_research(prompt)


def research_market_rents(location: str, building_type: str, unit_mix: dict) -> dict:
    """
    Search Apartments.com, Zillow, Redfin, CoStar for current asking rents.
    Returns weighted average $/NSF/month by bedroom type.
    Cross-references at least two sources.
    """
    unit_types = [ut for ut, pct in unit_mix.items() if pct > 0]
    unit_list = ", ".join(unit_types) if unit_types else "Studio, 1BR, 2BR, 3BR"

    prompt = f"""
Search for current market-rate asking rents for {building_type} apartments near {location}.
Unit types needed: {unit_list}

Search Apartments.com, Zillow (rental listings and Zillow Rent Index), Redfin (rental comps), and CoStar.
Cross-reference at least two sources and note any material discrepancy.

Return a JSON object:
{{
  "studio": {{"value": <monthly rent $ or null>, "unit": "$/month", "source_url": "...", "source_name": "...", "date_retrieved": "{TODAY}", "notes": "avg NSF, $/NSF, sources cross-referenced"}},
  "1br": {{"value": <monthly rent $ or null>, "unit": "$/month", "source_url": "...", "source_name": "...", "date_retrieved": "{TODAY}", "notes": "avg NSF, $/NSF"}},
  "2br": {{"value": <monthly rent $ or null>, "unit": "$/month", "source_url": "...", "source_name": "...", "date_retrieved": "{TODAY}", "notes": "avg NSF, $/NSF"}},
  "3br": {{"value": <monthly rent $ or null>, "unit": "$/month", "source_url": "...", "source_name": "...", "date_retrieved": "{TODAY}", "notes": "avg NSF, $/NSF"}},
  "4br": {{"value": <monthly rent $ or null>, "unit": "$/month", "source_url": "...", "source_name": "...", "date_retrieved": "{TODAY}", "notes": "avg NSF, $/NSF"}},
  "studio_avg_sf": {{"value": <SF or null>, "unit": "SF", "source_url": "...", "source_name": "...", "date_retrieved": "{TODAY}", "notes": "..."}},
  "1br_avg_sf": {{"value": <SF or null>, "unit": "SF", "source_url": "...", "source_name": "...", "date_retrieved": "{TODAY}", "notes": "..."}},
  "2br_avg_sf": {{"value": <SF or null>, "unit": "SF", "source_url": "...", "source_name": "...", "date_retrieved": "{TODAY}", "notes": "..."}},
  "3br_avg_sf": {{"value": <SF or null>, "unit": "SF", "source_url": "...", "source_name": "...", "date_retrieved": "{TODAY}", "notes": "..."}},
  "4br_avg_sf": {{"value": <SF or null>, "unit": "SF", "source_url": "...", "source_name": "...", "date_retrieved": "{TODAY}", "notes": "..."}},
  "vacancy_rate": {{"value": <decimal e.g. 0.05 or null>, "unit": "decimal", "source_url": "...", "source_name": "...", "date_retrieved": "{TODAY}", "notes": "submarket vacancy rate"}}
}}

Search: "{location} apartments for rent {building_type} 2025 average rent"
Also search: "Zillow Rent Index {location} 2025"
Also search: "{location} apartment vacancy rate 2025"
"""
    return _run_research(prompt)


def research_cap_rates(location: str, use_type: str) -> dict:
    """
    Search CoStar, CBRE, JLL, Marcus & Millichap for current cap rates.
    Returns cap rate and source for asset type in submarket.
    """
    prompt = f"""
Search for current (2025-2026) market cap rates for {use_type} properties in {location} or its metro area.

Search CoStar, CBRE research reports, JLL research, Marcus & Millichap market reports.

Return a JSON object:
{{
  "cap_rate": {{"value": <decimal e.g. 0.055 or null>, "unit": "decimal", "source_url": "...", "source_name": "...", "date_retrieved": "{TODAY}", "notes": "range if available, trend direction"}},
  "cap_rate_range_low": {{"value": <decimal or null>, "unit": "decimal", "source_url": "...", "source_name": "...", "date_retrieved": "{TODAY}", "notes": "..."}},
  "cap_rate_range_high": {{"value": <decimal or null>, "unit": "decimal", "source_url": "...", "source_name": "...", "date_retrieved": "{TODAY}", "notes": "..."}}
}}

Search: "{location} {use_type} cap rate 2025 market"
Also search: "CBRE JLL multifamily cap rate {location} metro 2025"
Also search: "Marcus Millichap {location} apartment cap rate 2025"
"""
    return _run_research(prompt)


def research_interest_rates() -> dict:
    """
    Always re-fetched. Searches Federal Reserve for current SOFR/federal funds rate.
    Returns current rate + typical construction loan spread (250bps) and permanent loan spread.
    """
    prompt = f"""
Search the Federal Reserve website (federalreserve.gov) and SOFR data sources for the current federal funds rate and SOFR rate as of today {TODAY}.

Also search for typical construction loan spreads and permanent/perm loan spreads over SOFR for multifamily development in 2025-2026.

Return a JSON object:
{{
  "sofr_rate": {{"value": <decimal e.g. 0.053 or null>, "unit": "decimal", "source_url": "https://www.federalreserve.gov/...", "source_name": "Federal Reserve", "date_retrieved": "{TODAY}", "notes": "current SOFR or effective federal funds rate"}},
  "federal_funds_rate": {{"value": <decimal or null>, "unit": "decimal", "source_url": "https://www.federalreserve.gov/...", "source_name": "Federal Reserve", "date_retrieved": "{TODAY}", "notes": "..."}},
  "construction_loan_spread_bps": {{"value": 250, "unit": "basis points", "source_url": "...", "source_name": "...", "date_retrieved": "{TODAY}", "notes": "typical spread over SOFR for construction loans"}},
  "construction_loan_rate": {{"value": <sofr + 0.025 or null>, "unit": "decimal", "source_url": "...", "source_name": "...", "date_retrieved": "{TODAY}", "notes": "SOFR + 250bps"}},
  "perm_loan_spread_bps": {{"value": <number or null>, "unit": "basis points", "source_url": "...", "source_name": "...", "date_retrieved": "{TODAY}", "notes": "typical spread for permanent multifamily loan"}},
  "perm_loan_rate": {{"value": <decimal or null>, "unit": "decimal", "source_url": "...", "source_name": "...", "date_retrieved": "{TODAY}", "notes": "SOFR + permanent spread"}}
}}

Search: "current SOFR rate 2025 federal reserve"
Also search: "federalreserve.gov current federal funds rate"
Also search: "multifamily construction loan interest rate spread SOFR 2025"
"""
    return _run_research(prompt)


def research_tax_rates(location: str) -> dict:
    """
    Search county assessor or treasurer website for current property tax mill rate / effective rate.
    """
    prompt = f"""
Search the county assessor, county treasurer, or tax collector website for {location} to find the current property tax mill rate or effective property tax rate for commercial/multifamily real estate.

Return a JSON object:
{{
  "effective_tax_rate": {{"value": <decimal e.g. 0.012 or null>, "unit": "decimal (of assessed value)", "source_url": "...", "source_name": "county assessor/treasurer", "date_retrieved": "{TODAY}", "notes": "mill rate if applicable, assessment ratio"}},
  "mill_rate": {{"value": <mills or null>, "unit": "mills ($/1000 assessed value)", "source_url": "...", "source_name": "...", "date_retrieved": "{TODAY}", "notes": "..."}},
  "assessment_ratio": {{"value": <decimal or null>, "unit": "decimal (assessed/market value)", "source_url": "...", "source_name": "...", "date_retrieved": "{TODAY}", "notes": "ratio of assessed to market value"}}
}}

Search: "{location} county property tax rate multifamily 2025"
Also search: "{location} county assessor millage rate commercial property tax"
Also search: "{location} property tax mill rate 2024 2025"
"""
    return _run_research(prompt)


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

Search: "HUD income limits {location} 2025 huduser.gov"
Also search: "huduser.gov income limits {location} area median income 2025"
"""
    return _run_research(prompt)


def research_opex_benchmarks(use_type: str, building_type: str) -> dict:
    """
    Search NMHC, NAHB, published developer proformas for operating expense benchmarks.
    Returns $/unit/year for building type and use.
    """
    prompt = f"""
Search for current (2024-2026) operating expense benchmarks for {use_type} {building_type} multifamily properties.

Use NMHC (National Multifamily Housing Council), NAHB, Institute of Real Estate Management (IREM), published developer proformas, and industry reports.

Return a JSON object:
{{
  "total_opex_per_unit_year": {{"value": <number or null>, "unit": "$/unit/year", "source_url": "...", "source_name": "...", "date_retrieved": "{TODAY}", "notes": "includes management, maintenance, insurance, admin"}},
  "management_fee_pct_egi": {{"value": <decimal e.g. 0.04 or null>, "unit": "decimal (% of EGI)", "source_url": "...", "source_name": "...", "date_retrieved": "{TODAY}", "notes": "..."}},
  "maintenance_per_unit_year": {{"value": <number or null>, "unit": "$/unit/year", "source_url": "...", "source_name": "...", "date_retrieved": "{TODAY}", "notes": "..."}},
  "insurance_per_unit_year": {{"value": <number or null>, "unit": "$/unit/year", "source_url": "...", "source_name": "...", "date_retrieved": "{TODAY}", "notes": "..."}},
  "admin_per_unit_year": {{"value": <number or null>, "unit": "$/unit/year", "source_url": "...", "source_name": "...", "date_retrieved": "{TODAY}", "notes": "payroll, leasing, G&A"}},
  "capex_reserve_per_unit_year": {{"value": <number or null>, "unit": "$/unit/year", "source_url": "...", "source_name": "...", "date_retrieved": "{TODAY}", "notes": "replacement reserve"}}
}}

Search: "NMHC multifamily operating expenses per unit 2024 2025"
Also search: "IREM apartment operating costs per unit {building_type} 2025"
Also search: "{use_type} apartment operating expense benchmark $/unit 2025"
"""
    return _run_research(prompt)


def research_employment_and_demand(location: str) -> dict:
    """
    Search Lightcast for local employment trends, wage growth, dominant industries.
    Returns qualitative demand signals for feasibility narrative.
    """
    prompt = f"""
Search Lightcast (lightcast.io), Bureau of Labor Statistics (bls.gov), and local economic development sources for employment and economic data in {location} or its metro area.

Find: top employment sectors, recent job growth rate (%), median wage, notable employer concentrations or recent expansions, housing demand signals.

Return a JSON object:
{{
  "top_sectors": [
    {{"sector": "...", "employment_count": <number or null>, "source_url": "...", "source_name": "...", "date_retrieved": "{TODAY}", "notes": "..."}}
  ],
  "job_growth_rate_annual": {{"value": <decimal e.g. 0.02 or null>, "unit": "decimal (annual %)", "source_url": "...", "source_name": "...", "date_retrieved": "{TODAY}", "notes": "most recent 12 months"}},
  "unemployment_rate": {{"value": <decimal or null>, "unit": "decimal", "source_url": "...", "source_name": "BLS", "date_retrieved": "{TODAY}", "notes": "..."}},
  "median_household_income": {{"value": <$ or null>, "unit": "$/year", "source_url": "...", "source_name": "...", "date_retrieved": "{TODAY}", "notes": "..."}},
  "median_wage": {{"value": <$ or null>, "unit": "$/year", "source_url": "...", "source_name": "...", "date_retrieved": "{TODAY}", "notes": "all occupations median"}},
  "notable_employers": [
    {{"name": "...", "note": "recent expansion or major employer", "source_url": "...", "date_retrieved": "{TODAY}"}}
  ],
  "demand_narrative": {{"value": "...", "unit": "text", "source_url": "...", "source_name": "...", "date_retrieved": "{TODAY}", "notes": "1-2 sentence summary of demand drivers for housing"}}
}}

Search: "Lightcast employment {location} 2025"
Also search: "BLS metropolitan employment {location} 2025"
Also search: "{location} job growth economy 2025 housing demand"
"""
    return _run_research(prompt)


def research_for_sale_comps(location: str, building_type: str) -> dict:
    """
    Called only when use type is For-Sale Condo or Mixed-Use.
    Returns median sale price/SF, days on market, absorption rate.
    """
    prompt = f"""
Search for recent condo and townhome sales near {location} (past 12 months, within ~1 mile) suitable for {building_type} development.

Search Redfin and Zillow for recent sold listings. Cross-reference with CoStar where available.

Return a JSON object:
{{
  "median_sale_price_per_sf": {{"value": <number or null>, "unit": "$/SF", "source_url": "...", "source_name": "...", "date_retrieved": "{TODAY}", "notes": "number of comps, date range"}},
  "median_sale_price": {{"value": <number or null>, "unit": "$", "source_url": "...", "source_name": "...", "date_retrieved": "{TODAY}", "notes": "median total sale price"}},
  "median_days_on_market": {{"value": <number or null>, "unit": "days", "source_url": "...", "source_name": "...", "date_retrieved": "{TODAY}", "notes": "..."}},
  "absorption_rate_units_per_month": {{"value": <number or null>, "unit": "units/month", "source_url": "...", "source_name": "...", "date_retrieved": "{TODAY}", "notes": "how many units sold per month in submarket"}},
  "profit_margin_benchmark": {{"value": <decimal e.g. 0.18 or null>, "unit": "decimal", "source_url": "...", "source_name": "...", "date_retrieved": "{TODAY}", "notes": "typical developer profit margin for for-sale product in this market"}}
}}

Search: "{location} condo townhome sold price per SF 2024 2025 Redfin Zillow"
Also search: "{location} new construction condo sale price $/SF 2025"
"""
    return _run_research(prompt)


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
Search the {state} state housing finance agency (HFA) website for the current Qualified Allocation Plan (QAP) and LIHTC program rules for {lihtc_type} tax credits.

Find: credit rate, qualified basis percentage, investor equity pricing ($/credit), per-capita credit cap, maximum project credit cap, application deadlines/cycles.

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

Search: "{state} LIHTC QAP {lihtc_type} tax credit housing finance agency 2025"
Also search: "{state} housing finance agency qualified allocation plan 2025"
Also search: "{state} low income housing tax credit investor pricing 2025"
"""
    return _run_research(prompt)
