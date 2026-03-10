"""
app.py — Streamlit UI
Real Estate Development Feasibility Calculator
"""

import streamlit as st
import pandas as pd
import numpy as np
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from location_data import STATES

from research import (
    research_zoning,
    research_land_costs,
    research_construction_costs,
    research_market_rents,
    research_cap_rates,
    research_interest_rates,
    research_tax_rates,
    research_ami_and_affordable_rents,
    research_opex_benchmarks,
    research_employment_and_demand,
    research_for_sale_comps,
    research_lihtc_rules,
    research_parcel,
)
from calculations import run_calculations
from zoning_check import run_zoning_adjustment_pass
from export import export_to_excel

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Default unit counts and mixes by building type
# Based on typical recently-built multifamily developments
# ---------------------------------------------------------------------------
UNITS_PER_ACRE = {
    "High-Rise 10+ stories": 200,
    "Mid-Rise 5-9 stories":  80,
    "Low-Rise 1-4 stories":  35,
    "Townhomes":             14,
}

DEFAULT_UNIT_MIX = {
    "High-Rise 10+ stories": {"studio": 20, "1br": 45, "2br": 28, "3br": 7,  "4br": 0},
    "Mid-Rise 5-9 stories":  {"studio": 12, "1br": 42, "2br": 35, "3br": 11, "4br": 0},
    "Low-Rise 1-4 stories":  {"studio": 5,  "1br": 35, "2br": 42, "3br": 16, "4br": 2},
    "Townhomes":             {"studio": 0,  "1br": 8,  "2br": 47, "3br": 38, "4br": 7},
}

st.set_page_config(
    page_title="Development Feasibility",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .stMetric { background: #f8f9fa; border-radius: 8px; padding: 12px; }
    .feasible-badge { background: #375623; color: white; border-radius: 8px;
        padding: 12px 24px; font-size: 1.4em; font-weight: bold; text-align: center; }
    .infeasible-badge { background: #9C0006; color: white; border-radius: 8px;
        padding: 12px 24px; font-size: 1.4em; font-weight: bold; text-align: center; }
    .source-chip { background: #e8f4f8; border-radius: 4px; padding: 2px 8px;
        font-size: 0.8em; color: #1a6ea8; }
    .adj-card { background: #fff3cd; border-left: 4px solid #ffc107;
        padding: 10px; border-radius: 4px; margin: 4px 0; }
    .adj-card-good { background: #d4edda; border-left: 4px solid #28a745; }
    .adj-card-bad { background: #f8d7da; border-left: 4px solid #dc3545; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Session state helpers
# ---------------------------------------------------------------------------
def _cache_key(location: str, building_type: str, use_type: str) -> str:
    return f"{location.strip().lower()}|{building_type}|{use_type}"


def _needs_refresh(location: str, building_type: str, use_type: str) -> bool:
    key = _cache_key(location, building_type, use_type)
    return st.session_state.get("last_research_key") != key


def _invalidate_cache():
    for k in ["research_cache", "zoning_cache", "last_research_key"]:
        if k in st.session_state:
            del st.session_state[k]


# ---------------------------------------------------------------------------
# Sidebar — User Inputs
# ---------------------------------------------------------------------------
def _is_specific_enough(site_str: str) -> bool:
    """Accept street addresses, parcel IDs, coordinates, or any description 4+ words long."""
    if not site_str or len(site_str.strip()) < 4:
        return False
    # Has a digit → address number, parcel ID, or coordinates
    if any(c.isdigit() for c in site_str):
        return True
    # 4+ words → likely a real description (e.g. "Northeast corner of Main and Oak")
    if len(site_str.split()) >= 4:
        return True
    return False

with st.sidebar:
    st.title("🏗️ Project Inputs")

    # ---- Location (multi-field) ----
    st.subheader("📍 Location")

    loc_city = st.text_input(
        "City / County",
        placeholder="e.g. Chicago, Cook County",
        key="loc_city",
    )
    loc_state = st.selectbox(
        "State",
        [""] + STATES,
        key="loc_state",
    )
    loc_site  = st.text_input(
        "Specific Site",
        placeholder="e.g. 1301 S Michigan Ave  or  14-21-315-018  or  41.8677, -87.6245",
        key="loc_site",
        help="Enter a street address, parcel ID/APN, or lat/lon coordinates. "
             "Avoid neighborhood or city names alone — the more specific, the better the research.",
    )
    lot_size_input = st.text_input(
        "Lot Size (acres)",
        placeholder="e.g. 0.5  — leave blank to look up from records",
        key="lot_size_input",
    )
    try:
        lot_size_acres = float(lot_size_input) if lot_size_input.strip() else None
    except ValueError:
        lot_size_acres = None
        if lot_size_input.strip():
            st.warning("Lot size must be a number (e.g. 0.5).")

    site_ok = _is_specific_enough(loc_site)
    if loc_site and not site_ok:
        st.warning("Please enter a street address, parcel ID, or coordinates — neighborhood names alone are too broad.")

    # Compose full location string for research functions
    location_parts = [p for p in [loc_site, loc_city, loc_state] if p.strip()]
    location = ", ".join(location_parts)

    st.divider()

    # ---- Development Program ----
    st.subheader("🏢 Development Program")

    use_type = st.selectbox(
        "Use Type",
        ["Multifamily Rental", "For-Sale Condo", "Mixed-Use", "Affordable / LIHTC"],
    )

    lihtc_type = None
    if use_type == "Affordable / LIHTC":
        lihtc_type = st.selectbox("LIHTC Credit Type", ["9%", "4%"])

    building_type = st.selectbox(
        "Building Type",
        [
            "High-Rise 10+ stories",
            "Mid-Rise 5-9 stories",
            "Low-Rise 1-4 stories",
            "Townhomes",
        ],
    )

    # Unit mix from building type defaults; parcel size and unit count come from research
    unit_mix = DEFAULT_UNIT_MIX[building_type]

    affordability_mix = {"Market": 100}
    if use_type == "Affordable / LIHTC":
        st.divider()
        st.subheader("Affordability Mix")
        st.caption("Must sum to 100%")
        aff_30     = st.slider("30% AMI", 0, 100, 10, 5)
        aff_50     = st.slider("50% AMI", 0, 100, 20, 5)
        aff_60     = st.slider("60% AMI", 0, 100, 30, 5)
        aff_80     = st.slider("80% AMI", 0, 100, 20, 5)
        aff_market = st.slider("Market Rate", 0, 100, 20, 5)
        aff_total  = aff_30 + aff_50 + aff_60 + aff_80 + aff_market
        if aff_total != 100:
            st.error(f"Sums to {aff_total}% — must equal 100%")
        affordability_mix = {
            "30% AMI": aff_30, "50% AMI": aff_50, "60% AMI": aff_60,
            "80% AMI": aff_80, "Market": aff_market,
        }

    st.divider()
    inputs_ready = bool(loc_state and loc_city and loc_site and site_ok)
    run_button = st.button(
        "Run Analysis", type="primary", use_container_width=True,
        disabled=not inputs_ready,
    )

# ---------------------------------------------------------------------------
# Main panel
# ---------------------------------------------------------------------------
st.title("Development Feasibility Calculator")

if not inputs_ready and "results_cache" not in st.session_state:
    st.info("Complete all location fields in the sidebar to begin.")
    st.stop()

# ---------------------------------------------------------------------------
# Research + Calculation pipeline
# ---------------------------------------------------------------------------
user_inputs = {
    "location": location,
    "loc_site": loc_site,
    "loc_city": loc_city,
    "loc_state": loc_state,
    "use_type": use_type,
    "lihtc_type": lihtc_type,
    "building_type": building_type,
    "num_units": 0,       # filled in after parcel research
    "parcel_acres": 0.0,  # filled in after parcel research
    "unit_mix": unit_mix,
    "affordability_mix": affordability_mix,
}

cache_key = _cache_key(location, building_type, use_type)
needs_refresh = _needs_refresh(location, building_type, use_type)

if run_button:
    _invalidate_cache()
    assumptions = {}
    zoning_result = {"adjustments": [], "applicable_adjustments": [], "any_changes": False, "roc_delta": 0}

    progress = st.progress(0, text="Starting research...")

    research_steps = []
    result_keys = []

    if lot_size_acres is None:
        research_steps.append(("Looking up parcel data...", lambda: research_parcel(location, loc_site)))
        result_keys.append("parcel")

    research_steps += [
        ("Researching zoning regulations...",        lambda: research_zoning(location, building_type)),
        ("Researching land costs...",                lambda: research_land_costs(location, building_type)),
        ("Researching construction costs...",        lambda: research_construction_costs(location, building_type)),
        ("Researching market rents...",              lambda: research_market_rents(location, building_type, unit_mix)),
        ("Researching cap rates...",                 lambda: research_cap_rates(location, use_type)),
        ("Fetching current interest rates...",       lambda: research_interest_rates()),
        ("Researching property tax rates...",        lambda: research_tax_rates(location)),
        ("Researching operating expense benchmarks...", lambda: research_opex_benchmarks(use_type, building_type)),
        ("Researching employment & demand signals...", lambda: research_employment_and_demand(location)),
    ]
    result_keys += ["zoning", "land", "construction", "rents", "cap_rates",
                    "interest_rates", "tax_rates", "opex", "employment"]

    if use_type == "Affordable / LIHTC":
        ami_levels = [int(k.replace("% AMI", "")) for k in affordability_mix if k != "Market"]
        research_steps.append(
            (f"Fetching HUD AMI limits for {location}...",
             lambda: research_ami_and_affordable_rents(location, ami_levels))
        )
        result_keys.append("ami")

        if lihtc_type:
            state = location.split(",")[-1].strip() if "," in location else location
            research_steps.append(
                (f"Researching LIHTC rules for {state}...",
                 lambda: research_lihtc_rules(state, lihtc_type))
            )
            result_keys.append("lihtc")

    if use_type in ("For-Sale Condo", "Mixed-Use"):
        research_steps.append(
            ("Researching for-sale comps...",
             lambda: research_for_sale_comps(location, building_type))
        )
        result_keys.append("for_sale_comps")

    # Run research calls with 5 parallel workers.
    # 3 of the 10 steps use no web search and complete in ~3-5s.
    # The 7 web-search steps run concurrently; each does 1 search (low TPM).
    total_steps = len(research_steps)
    completed_count = [0]
    lock = threading.Lock()

    def _run_step(idx, label, fn, key):
        try:
            result = fn()
        except Exception as e:
            result = {}
            st.warning(f"Research step failed ({label}): {e}")
        with lock:
            completed_count[0] += 1
            pct = int(completed_count[0] / total_steps * 80)
            progress.progress(pct, text=f"Completed: {label}")
        return key, result

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(_run_step, i, label, fn, result_keys[i]): i
            for i, (label, fn) in enumerate(research_steps)
        }
        for future in as_completed(futures):
            key, result = future.result()
            assumptions[key] = result

    # Determine parcel size: user input takes priority over research lookup
    if lot_size_acres is not None:
        parcel_acres = lot_size_acres
    else:
        _p_item = assumptions.get("parcel", {}).get("parcel_area_acres", {})
        _p_val  = _p_item.get("value") if isinstance(_p_item, dict) else _p_item
        parcel_acres = float(_p_val) if _p_val else 1.0
    num_units = max(1, round(UNITS_PER_ACRE[building_type] * parcel_acres))
    user_inputs["parcel_acres"] = parcel_acres
    user_inputs["num_units"]    = num_units

    progress.progress(82, text="Running financial model...")
    try:
        results = run_calculations(user_inputs, assumptions)
    except Exception as e:
        st.error(f"Calculation error: {e}")
        st.stop()

    progress.progress(100, text="Complete!")
    progress.empty()

    st.session_state["research_cache"]    = assumptions
    st.session_state["results_cache"]     = results
    st.session_state["zoning_cache"]      = zoning_result
    st.session_state["user_inputs_cache"] = user_inputs
    st.session_state["last_research_key"] = cache_key

elif "results_cache" in st.session_state:
    results      = st.session_state["results_cache"]
    assumptions  = st.session_state["research_cache"]
    zoning_result = st.session_state.get("zoning_cache", {
        "adjustments": [], "applicable_adjustments": [], "any_changes": False, "roc_delta": 0
    })
    # Use cached inputs (needed so demo mode renders correctly)
    user_inputs  = st.session_state.get("user_inputs_cache", user_inputs)
else:
    st.info("Press **Run Analysis** to start.")
    st.stop()

# ---------------------------------------------------------------------------
# Helpers shared across tabs
# ---------------------------------------------------------------------------

# Keys to exclude from assumptions display (employment/demographic data)
_EXCLUDE_ASSUMPTION_KEYS = {
    "job_growth_rate_annual", "unemployment_rate", "median_household_income",
    "median_wage", "top_sectors", "notable_employers", "demand_narrative",
}

# Human-readable labels and descriptions for every assumption key
_ASSUMPTION_META = {
    # Parcel
    "parcel_area_acres":            ("Parcel Area (acres)",                   "Total parcel area from official county assessor/GIS records. Drives unit count and land cost calculations."),
    "parcel_area_sf":               ("Parcel Area (square feet)",             "Total parcel area in square feet from official records."),
    "current_land_use":             ("Current Land Use",                      "Official land use classification from the county assessor. Indicates whether the site is vacant, improved, or in another use."),
    "current_zoning":               ("Current Zoning Designation",            "The zoning code applicable to this parcel from official city/county records. Used to cross-check the zoning research."),
    "existing_building_sf":         ("Existing Building — Gross SF",          "Total gross square footage of any existing structure(s) on the parcel. If > 0, demolition is required and its cost ($15/SF) is included in the development budget."),
    "existing_building_stories":    ("Existing Building — Stories",           "Number of floors in existing structure(s)."),
    "existing_building_year_built": ("Existing Building — Year Built",        "Year the existing structure was originally constructed."),
    "assessed_value_land":          ("Assessed Value — Land Only",            "Land-only assessed value per county assessor records. A proxy for land market value (adjust for assessment ratio)."),
    "assessed_value_total":         ("Assessed Value — Total",                "Total assessed value (land + improvements) per county assessor."),
    "demolition_required":          ("Demolition Required",                   "Whether existing structures must be cleared before construction. When true, demolition cost at $15/SF of existing building is added to the development budget."),
    # Zoning
    "max_far":                   ("Maximum Floor Area Ratio (FAR)",          "The zoning code's limit on total building floor area relative to parcel area. A FAR of 4.0 on a 10,000 SF lot allows up to 40,000 SF of floor area. Higher FAR enables more units on the same land."),
    "max_height_stories":        ("Maximum Building Height (Stories)",        "The tallest the building can be under base zoning. Affects total buildable area and structural cost."),
    "parking_studio":            ("Parking Minimum — Studio Units",           "Required parking spaces per studio apartment under local zoning. Parking construction is one of the largest cost drivers — structured spaces cost $28K–$40K each."),
    "parking_1br":               ("Parking Minimum — 1-Bedroom Units",        "Required parking spaces per 1-bedroom apartment."),
    "parking_2br":               ("Parking Minimum — 2-Bedroom Units",        "Required parking spaces per 2-bedroom apartment."),
    "parking_3br":               ("Parking Minimum — 3-Bedroom Units",        "Required parking spaces per 3-bedroom apartment."),
    "setback_front_ft":          ("Front Setback (feet)",                     "Minimum distance the building must sit back from the front property line. Reduces usable footprint."),
    "setback_side_ft":           ("Side Setback (feet)",                      "Minimum distance from side property lines."),
    "setback_rear_ft":           ("Rear Setback (feet)",                      "Minimum distance from rear property line."),
    # Land
    "land_cost_per_sf":          ("Land Cost — per Square Foot",              "Price per land square foot based on comparable recent sales near the site. Land cost is typically the single largest swing factor in urban development feasibility."),
    "land_cost_per_acre":        ("Land Cost — per Acre",                     "Total land price per acre. Useful for comparing across sites of different sizes."),
    # Construction
    "hard_cost_per_gsf":         ("Hard Construction Cost — per Gross SF",    "All-in vertical construction cost: structure, mechanical/electrical/plumbing, finishes, and contingency. Sourced from RSMeans regional benchmarks and local permit data."),
    "parking_structured_per_space": ("Structured Parking — Cost per Space",  "Cost to build one above-grade or podium parking space, including ramps and mechanical systems. Typically $28K–$45K depending on market."),
    "parking_surface_per_space": ("Surface Parking — Cost per Space",         "Cost to build one surface parking space including paving, striping, and drainage. Typically $4K–$8K."),
    # Rents
    "studio":                    ("Studio — Market Asking Rent",              "Current asking rent for studio apartments near the site, drawn from active listings. Vacancy is applied to convert asking to effective rent."),
    "1br":                       ("1-Bedroom — Market Asking Rent",           "Current asking rent for 1-bedroom apartments near the site."),
    "2br":                       ("2-Bedroom — Market Asking Rent",           "Current asking rent for 2-bedroom apartments."),
    "3br":                       ("3-Bedroom — Market Asking Rent",           "Current asking rent for 3-bedroom apartments."),
    "4br":                       ("4-Bedroom — Market Asking Rent",           "Current asking rent for 4-bedroom apartments."),
    "studio_avg_sf":             ("Studio — Average Unit Size (SF)",          "Typical net square footage of studio units in comparable new developments in the submarket."),
    "1br_avg_sf":                ("1-Bedroom — Average Unit Size (SF)",       "Typical net SF of 1BR units in comparable new developments."),
    "2br_avg_sf":                ("2-Bedroom — Average Unit Size (SF)",       "Typical net SF of 2BR units."),
    "3br_avg_sf":                ("3-Bedroom — Average Unit Size (SF)",       "Typical net SF of 3BR units."),
    "4br_avg_sf":                ("4-Bedroom — Average Unit Size (SF)",       "Typical net SF of 4BR units."),
    "vacancy_rate":              ("Submarket Vacancy Rate",                   "Expected percentage of units vacant at any given time in the submarket. Applied to gross potential rent to calculate Effective Gross Income (EGI)."),
    # Cap rates
    "cap_rate":                  ("Market Capitalization Rate",               "The rate the market uses to value stabilized rental income: Exit Value = NOI ÷ Cap Rate. Lower cap rates produce higher valuations. Sourced from broker market reports."),
    "cap_rate_range_low":        ("Cap Rate — Low End of Submarket Range",    "Lower bound of cap rates observed in recent comparable sales in this submarket."),
    "cap_rate_range_high":       ("Cap Rate — High End of Submarket Range",   "Upper bound of cap rates observed in recent comparable sales."),
    # Interest rates
    "sofr_rate":                 ("SOFR Rate (Current)",                      "Secured Overnight Financing Rate — the market benchmark used to price floating-rate construction loans. Sourced from the Federal Reserve."),
    "federal_funds_rate":        ("Federal Funds Rate",                       "The Federal Reserve's overnight lending target rate, which anchors the broader rate environment."),
    "construction_loan_spread_bps": ("Construction Loan Spread over SOFR",   "The additional spread lenders charge above SOFR for construction loans, reflecting project risk during the build period. Typically 250–350 bps."),
    "construction_loan_rate":    ("All-In Construction Loan Rate",            "Total construction financing rate (SOFR + spread). Applied to approximately 50% of the loan balance over the 18-month construction period to estimate interest carry cost."),
    "perm_loan_spread_bps":      ("Permanent Loan Spread over SOFR",          "Spread for stabilized permanent financing (e.g., agency debt, CMBS) after construction is complete. Typically 175–250 bps."),
    "perm_loan_rate":            ("All-In Permanent Loan Rate",               "Total permanent loan rate used to estimate annual debt service in the 5-year operating model."),
    # Tax
    "effective_tax_rate":        ("Effective Property Tax Rate",              "Blended annual tax rate applied to assessed value. Used to calculate property tax expense in the operating pro forma. Accounts for assessment ratio and mill rate."),
    "mill_rate":                 ("Property Tax Mill Rate",                   "Tax expressed as dollars per $1,000 of assessed value. Converted to an effective rate using the assessment ratio."),
    "assessment_ratio":          ("Assessment Ratio",                         "The ratio of a property's assessed value to its market value for tax purposes. For example, Cook County assesses commercial property at 25% of market value."),
    # OpEx
    "total_opex_per_unit_year":  ("Total Operating Expenses — per Unit per Year", "All annual operating costs per unit: maintenance, management, insurance, administrative, and utilities. Benchmarked against IREM and NMHC data for comparable properties."),
    "management_fee_pct_egi":    ("Property Management Fee (% of Income)",    "Fee paid to the property management company, typically 4–6% of Effective Gross Income. Covers leasing, rent collection, and day-to-day operations."),
    "maintenance_per_unit_year": ("Maintenance and Repairs — per Unit per Year", "Routine maintenance costs: janitorial, landscaping, unit turn costs, and minor repairs."),
    "insurance_per_unit_year":   ("Property Insurance — per Unit per Year",   "Annual property and liability insurance cost allocated per unit."),
    "capex_reserve_per_unit_year": ("Capital Expenditure Reserve — per Unit per Year", "Annual reserve set aside for future major replacements: roofs, HVAC, elevators, appliances. Treated as an operating expense in the pro forma."),
    # AMI
    "median_family_income":      ("Area Median Income (AMI)",                 "HUD-published median family income for the metro area. Used as the basis for calculating maximum affordable rents at each AMI level."),
    # For-sale
    "median_sale_price_per_sf":  ("Comparable Sale Price — per Square Foot",  "Median sale price per SF of recent condo/townhome sales within ~1 mile of the site."),
    "median_sale_price":         ("Comparable Median Sale Price",              "Median total sale price of comparable for-sale units in the submarket."),
    "median_days_on_market":     ("Median Days on Market",                    "How long comparable units typically sit on the market — a proxy for absorption pace."),
    "absorption_rate_units_per_month": ("Absorption Rate (Units per Month)",  "How many units are selling per month in the submarket. Used to estimate sellout timeline and carrying cost."),
    "profit_margin_benchmark":   ("Developer Profit Margin Benchmark",        "Typical net profit margin for for-sale product in this market. The model uses 15% as the minimum feasibility threshold."),
    # LIHTC
    "credit_rate":               ("LIHTC Credit Rate",                        "The annual federal tax credit rate — 4% for tax-exempt bond deals, 9% for competitive credit allocations."),
    "qualified_basis_pct":       ("Qualified Basis Percentage",               "The percentage of eligible basis (construction cost) that qualifies for tax credits."),
    "investor_pricing_per_credit": ("Equity Investor Pricing (per $1 of Credit)", "How much equity investors pay per $1 of annual tax credit — typically $0.80–$0.95. Drives total equity proceeds."),
    "per_capita_cap":            ("Per-Capita Credit Allocation Cap",         "IRS limit on total LIHTC credits a state may allocate annually, based on state population."),
    "project_credit_cap":        ("Per-Project Credit Cap",                   "Maximum annual credits a single project may receive, as set by the state housing finance agency."),
    "application_cycle":         ("Application / Award Cycle",                "When the state housing finance agency accepts and awards LIHTC applications."),
}

def _fmt_assumption_row(category, key, item):
    meta = _ASSUMPTION_META.get(key, (key.replace("_", " ").title(), ""))
    label, description = meta if len(meta) == 2 else (meta[0], "")
    val = item.get("value")
    unit = item.get("unit", "")
    if isinstance(val, float):
        val_str = f"{val:.4g} {unit}".strip()
    elif val is not None:
        val_str = f"{val} {unit}".strip()
    else:
        val_str = "—"
    return {
        "Assumption": label,
        "Value": val_str,
        "Description & Rationale": description + (" " + item.get("notes", "") if item.get("notes") else ""),
        "Source": item.get("source_name", ""),
        "URL": item.get("source_url", ""),
        "Retrieved": item.get("date_retrieved", ""),
    }

# Scenario engine for "How to Make It Work"
import copy as _copy

def _run_scenario(base_assumptions, base_user_inputs, modifier_fn):
    adj_assumptions = _copy.deepcopy(base_assumptions)
    adj_inputs      = _copy.deepcopy(base_user_inputs)
    modifier_fn(adj_assumptions, adj_inputs)
    return run_calculations(adj_inputs, adj_assumptions)

def _set_val(d, *path_and_val):
    """Set a nested value: _set_val(d, 'construction', 'hard_cost_per_gsf', 'value', 250)"""
    keys, val = path_and_val[:-1], path_and_val[-1]
    node = d
    for k in keys[:-1]:
        node = node.setdefault(k, {})
    if isinstance(node.get(keys[-1]), dict):
        node[keys[-1]]["value"] = val
    else:
        node[keys[-1]] = val

SCENARIOS = {
    "Surface parking instead of structured": {
        "description": "Replace above-grade structured parking with surface parking lots. Saves ~$26,500 per space, though may reduce usable land area.",
        "modifier": lambda a, u: _set_val(a, "construction", "parking_structured_per_space", "value",
                                          (a.get("construction", {}).get("parking_surface_per_space", {}) or {}).get("value", 5500)),
    },
    "Eliminate parking (transit overlay)": {
        "description": "Remove all parking requirements under a transit-oriented development (TOD) overlay or Connected Communities ordinance. Eliminates parking construction cost entirely.",
        "modifier": lambda a, u: (
            _set_val(a, "zoning", "parking_studio", "value", 0),
            _set_val(a, "zoning", "parking_1br",    "value", 0),
            _set_val(a, "zoning", "parking_2br",    "value", 0),
            _set_val(a, "zoning", "parking_3br",    "value", 0),
        ),
    },
    "Property tax abatement (50% reduction)": {
        "description": "A municipal tax abatement program (e.g., Cook County Class 9, NYC 421-a equivalent) halves the effective property tax rate for the first 10–15 years.",
        "modifier": lambda a, u: _set_val(a, "tax_rates", "effective_tax_rate", "value",
                                          ((a.get("tax_rates", {}).get("effective_tax_rate") or {}).get("value") or 0.02) * 0.5),
    },
    "Construction costs 10% lower": {
        "description": "Hard costs 10% below the current benchmark — achievable through value-engineering, modular construction, or a softening materials market.",
        "modifier": lambda a, u: _set_val(a, "construction", "hard_cost_per_gsf", "value",
                                          ((a.get("construction", {}).get("hard_cost_per_gsf") or {}).get("value") or 300) * 0.90),
    },
    "Land cost 20% lower": {
        "description": "Land acquired at 20% below the current comparable — possible through seller financing, land banking, or a distressed sale.",
        "modifier": lambda a, u: _set_val(a, "land", "land_cost_per_sf", "value",
                                          ((a.get("land", {}).get("land_cost_per_sf") or {}).get("value") or 100) * 0.80),
    },
    "Rents 10% above current market": {
        "description": "Achievable with premium positioning, Class A finishes, or strong lease-up in a supply-constrained submarket.",
        "modifier": lambda a, u: [
            _set_val(a, "rents", k, "value", ((a.get("rents", {}).get(k) or {}).get("value") or 0) * 1.10)
            for k in ["studio", "1br", "2br", "3br", "4br"]
        ],
    },
    "Density bonus: 15% more units": {
        "description": "Local density bonus program allows 15% additional units in exchange for providing 10% affordable units on-site. Spreads fixed costs over more revenue-generating units.",
        "modifier": lambda a, u: u.update({"num_units": round(u.get("num_units", 100) * 1.15)}),
    },
    "Combine: surface parking + tax abatement": {
        "description": "Stack two incentives: eliminate structured parking and apply a 50% tax abatement. Shows combined effect of multiple policy levers.",
        "modifier": lambda a, u: (
            _set_val(a, "zoning", "parking_1br", "value", 0),
            _set_val(a, "zoning", "parking_2br", "value", 0),
            _set_val(a, "zoning", "parking_3br", "value", 0),
            _set_val(a, "zoning", "parking_studio", "value", 0),
            _set_val(a, "tax_rates", "effective_tax_rate", "value",
                     ((a.get("tax_rates", {}).get("effective_tax_rate") or {}).get("value") or 0.02) * 0.5),
        ),
    },
}

# ---------------------------------------------------------------------------
# Results Tabs
# ---------------------------------------------------------------------------
tab_results, tab_assumptions, tab_sensitivity, tab_howto = st.tabs([
    "Results", "Assumptions", "Rent & Cost Sensitivity", "How to Make It Work"
])

with tab_results:
    is_feasible = results.get("is_feasible", False)
    roc         = results.get("return_on_cost", 0)
    threshold   = results.get("return_on_cost_threshold", 0.06)

    # ---- Feasibility badge ----
    badge_html = (
        f'<div class="feasible-badge">FEASIBLE</div>'
        if is_feasible else
        f'<div class="infeasible-badge">NOT FEASIBLE</div>'
    )
    st.markdown(badge_html, unsafe_allow_html=True)

    # Project summary line
    _pa = user_inputs.get('parcel_acres', 0) or 0
    _existing_sf = results.get("existing_building_sf", 0)
    _demo_note = f" · {_existing_sf:,.0f} SF existing structure (demolition required)" if _existing_sf > 0 else " · Vacant / clear site"
    st.caption(
        f"{user_inputs.get('loc_site', '')} · {user_inputs.get('loc_city', '')}, {user_inputs.get('loc_state', '')} · "
        f"{results.get('num_units', 0)} units · {_pa:.2f} acres{_demo_note} · "
        f"{user_inputs.get('building_type', '')}"
    )

    # Feasibility rationale (first sentence only — no demographics)
    verdict = results.get("verdict_explanation", "")
    # Keep only the first sentence (ends at first period followed by space or end)
    first_sentence = verdict.split(". ")[0].rstrip(".") + "."
    st.markdown(f"*{first_sentence}*")

    st.divider()

    # ---- ROC Gap visualization ----
    max_bar = max(threshold * 1.8, roc * 1.3, 0.12)
    actual_pct  = min(roc / max_bar * 100, 100)
    needed_pct  = min(threshold / max_bar * 100, 100)
    gap         = threshold - roc
    bar_color   = "#375623" if is_feasible else "#9C0006"
    st.markdown(f"""
<div style="margin:16px 0 24px 0;">
  <div style="display:flex;justify-content:space-between;margin-bottom:6px;font-weight:600;">
    <span>Return on Cost</span>
    <span style="color:{bar_color};">{roc:.2%} actual &nbsp;·&nbsp; {threshold:.0%} required &nbsp;·&nbsp; gap: {gap:+.2%}</span>
  </div>
  <div style="background:#e9ecef;border-radius:6px;height:28px;position:relative;overflow:visible;">
    <div style="background:{bar_color};width:{actual_pct:.1f}%;height:100%;border-radius:6px;position:absolute;top:0;left:0;"></div>
    <div style="background:#333;width:3px;height:40px;position:absolute;left:{needed_pct:.1f}%;top:-6px;border-radius:2px;"></div>
    <div style="position:absolute;left:calc({needed_pct:.1f}% + 6px);top:-24px;font-size:0.75em;color:#333;white-space:nowrap;">Required: {threshold:.0%}</div>
  </div>
</div>
""", unsafe_allow_html=True)

    # ---- Key metrics ----
    nu = results.get("num_units") or 1
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Development Cost",      f"${results.get('total_dev_cost', 0):,.0f}")
    c2.metric("Net Operating Income",        f"${results.get('noi', 0):,.0f}")
    if results.get("irr") is not None:
        c3.metric("Levered Internal Rate of Return (5-Year)", f"{results.get('irr', 0):.1%}")
    elif results.get("for_sale_margin") is not None:
        c3.metric("Developer Profit Margin", f"{results.get('for_sale_margin', 0):.1%}")
    else:
        c3.metric("Stabilized Exit Valuation", f"${results.get('exit_value', 0):,.0f}")
    c4.metric("Development Cost per Unit",   f"${results.get('cost_per_unit', 0):,.0f}")

    st.divider()
    excel_bytes = export_to_excel(results, user_inputs, assumptions, zoning_result)
    st.download_button(
        "Export to Excel",
        data=excel_bytes,
        file_name=f"feasibility_{user_inputs.get('loc_site','site').replace(' ','_')}_{date.today()}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
    )


# ---------------------------------------------------------------------------
with tab_assumptions:
    st.caption("All values sourced from live research. Sources and retrieval dates are included.")

    rows = []
    for category, cat_data in assumptions.items():
        if not isinstance(cat_data, dict):
            continue
        for key, item in cat_data.items():
            if not isinstance(item, dict) or key in _EXCLUDE_ASSUMPTION_KEYS:
                continue
            rows.append(_fmt_assumption_row(category, key, item))

    if rows:
        df_assum = pd.DataFrame(rows)
        st.dataframe(
            df_assum,
            use_container_width=True,
            hide_index=True,
            height=600,
            column_config={
                "URL":      st.column_config.LinkColumn("Source URL"),
                "Assumption": st.column_config.TextColumn("Assumption", width="medium"),
                "Value":    st.column_config.TextColumn("Value", width="small"),
                "Description & Rationale": st.column_config.TextColumn("Description & Rationale", width="large"),
                "Source":   st.column_config.TextColumn("Source", width="medium"),
                "Retrieved":st.column_config.TextColumn("Retrieved", width="small"),
            },
        )
    else:
        st.info("No assumptions loaded yet.")

    # ---- Project Cost & Revenue Breakdown ----
    st.divider()
    st.markdown("### Project Cost & Revenue Breakdown")
    st.caption("Financial model output based on the researched assumptions applied to this specific project.")

    nu_assum = results.get("num_units") or 1
    col_left_a, col_right_a = st.columns(2)
    with col_left_a:
        st.markdown("**Development Cost Breakdown**")
        cost_rows_a = [
            ("Land",                    results.get("land_cost", 0)),
            ("Hard Construction Costs", results.get("hard_costs", 0)),
            ("Parking Construction",    results.get("parking_hard_cost", 0)),
            ("Demolition",              results.get("demolition_cost", 0)),
            ("Soft Costs",              results.get("soft_costs", 0)),
            ("Construction Interest",   results.get("construction_interest", 0)),
            ("Total",                   results.get("total_dev_cost", 0)),
        ]
        df_ca = pd.DataFrame(cost_rows_a, columns=["Category", "Total"])
        df_ca["Per Unit"] = df_ca["Total"] / nu_assum
        df_ca["Total"]    = df_ca["Total"].map("${:,.0f}".format)
        df_ca["Per Unit"] = df_ca["Per Unit"].map("${:,.0f}".format)
        st.dataframe(df_ca, use_container_width=True, hide_index=True)

    with col_right_a:
        st.markdown("**Income & Expense Statement**")
        rev_rows_a = [
            ("Gross Rental Revenue",      results.get("gross_revenue", 0)),
            ("Less: Vacancy",             -results.get("gross_revenue", 0) * results.get("vacancy_rate", 0.05)),
            ("Effective Gross Income",     results.get("egi", 0)),
            ("Operating Expenses",        -results.get("total_opex", 0)),
            ("Management Fee",            -results.get("mgmt_fee", 0)),
            ("Property Taxes",            -results.get("property_taxes", 0)),
            ("Capital Reserve",           -results.get("capex_reserve", 0)),
            ("Net Operating Income",       results.get("noi", 0)),
        ]
        df_ra = pd.DataFrame(rev_rows_a, columns=["Item", "Annual"])
        df_ra["Annual"] = df_ra["Annual"].map("${:,.0f}".format)
        st.dataframe(df_ra, use_container_width=True, hide_index=True)

    # ---- Zoning Adjustments ----
    zoning_adj_a = zoning_result.get("applicable_adjustments", [])
    all_zoning_a = zoning_result.get("adjustments", [])
    if all_zoning_a:
        st.divider()
        st.markdown("### Zoning Adjustments")
        with st.expander(
            f"{len(zoning_adj_a)} adjustment(s) applied to the model" if zoning_adj_a else "No zoning adjustments applied",
            expanded=bool(zoning_adj_a),
        ):
            if zoning_adj_a:
                roc_delta_a = zoning_result.get("roc_delta", 0)
                st.success(f"{len(zoning_adj_a)} adjustment(s) applied · Return on Cost impact: {roc_delta_a:+.2%}")
            for adj_a in all_zoning_a:
                is_applied_a = adj_a in zoning_adj_a
                card_class_a = "adj-card-good" if is_applied_a else "adj-card"
                roc_imp_a = adj_a.get("roc_impact")
                roc_str_a = f" · Return on Cost impact: {roc_imp_a:+.2%}" if roc_imp_a is not None else ""
                applied_str_a = "Applied" if is_applied_a else f"Not applied (confidence: {adj_a.get('confidence', 'low')})"
                st.markdown(f"""
<div class="{card_class_a}">
<strong>{adj_a.get('adjustment_type', '').replace('_', ' ').title()}</strong> — {applied_str_a}{roc_str_a}<br>
{adj_a.get('description', '')}<br>
<small>{adj_a.get('original_value')} → {adj_a.get('revised_value')} {adj_a.get('unit', '')} &nbsp;|&nbsp;
<a href="{adj_a.get('source_url', '#')}">{adj_a.get('source_name', 'Source')}</a></small>
</div>""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
with tab_sensitivity:
    st.caption(
        "How does the return on cost change as rents or total development costs shift? "
        f"The minimum feasible return is {threshold:.0%}. Green = feasible, red = not."
    )

    base_noi  = results.get("noi", 0)
    base_cost = results.get("total_dev_cost", 1)
    base_rent = results.get("weighted_monthly_rent", 0)
    total_nsf = results.get("total_nsf", 1) or 1
    threshold = results.get("return_on_cost_threshold", 0.06)

    # ---- Rent sensitivity bar chart ----
    st.markdown("#### How do returns change if rents are higher or lower than today?")
    rent_scenarios = [
        ("Rents 20% below market",  -0.20),
        ("Rents 15% below market",  -0.15),
        ("Rents 10% below market",  -0.10),
        ("Rents 5% below market",   -0.05),
        ("At current market rents",  0.00),
        ("Rents 5% above market",   +0.05),
        ("Rents 10% above market",  +0.10),
        ("Rents 15% above market",  +0.15),
        ("Rents 20% above market",  +0.20),
    ]
    rent_rows = []
    for label, delta in rent_scenarios:
        adj_noi = base_noi * (1 + delta)
        roc_val = adj_noi / base_cost if base_cost > 0 else 0
        rent_rows.append({
            "Rent Scenario": label,
            "Avg Monthly Rent": f"${base_rent * (1 + delta):,.0f}",
            "Return on Cost": roc_val,
            "Feasible?": "Yes" if roc_val >= threshold else "No",
        })

    # Feasibility breakeven row — exact rent needed to hit threshold ROC
    _req_rent_delta = (base_cost * threshold / base_noi) - 1 if base_noi > 0 else 0
    _req_rent_feas  = base_rent * (1 + _req_rent_delta)
    rent_rows.append({
        "Rent Scenario": f"Needed for feasibility ({_req_rent_delta:+.1%} vs today)",
        "Avg Monthly Rent": f"${_req_rent_feas:,.0f}",
        "Return on Cost": threshold,
        "Feasible?": "Yes",
    })

    df_rent = pd.DataFrame(rent_rows)

    def _style_rent_row(row):
        if row.name == len(df_rent) - 1:
            return ["background-color:#1a3a5c;color:white;font-weight:bold"] * len(row)
        styles = [""] * len(row)
        roc_idx = list(df_rent.columns).index("Return on Cost")
        v = row["Return on Cost"]
        if v >= threshold * 1.05:    styles[roc_idx] = "background-color:#c6efce;color:#375623"
        elif v >= threshold:         styles[roc_idx] = "background-color:#d4edda;color:#155724"
        elif v >= threshold * 0.85:  styles[roc_idx] = "background-color:#fff3cd;color:#856404"
        else:                        styles[roc_idx] = "background-color:#f8d7da;color:#721c24"
        return styles

    st.dataframe(
        df_rent.style
            .apply(_style_rent_row, axis=1)
            .format({"Return on Cost": "{:.2%}"}),
        use_container_width=True, hide_index=True,
    )

    st.divider()

    # ---- Breakeven table ----
    st.markdown("#### What rent is needed to break even at different cost levels?")
    st.caption(
        "If costs come in lower (or higher) than projected, the rent you need to hit "
        f"the {threshold:.0%} return threshold changes. The gap per SF shows how far "
        "current market rents are from what the project needs."
    )

    cost_scenarios = [
        ("Costs 20% lower than projected",  -0.20),
        ("Costs 15% lower than projected",  -0.15),
        ("Costs 10% lower than projected",  -0.10),
        ("Costs 5% lower than projected",   -0.05),
        ("At projected costs (baseline)",    0.00),
        ("Costs 5% higher than projected",  +0.05),
        ("Costs 10% higher than projected", +0.10),
        ("Costs 15% higher than projected", +0.15),
        ("Costs 20% higher than projected", +0.20),
    ]
    be_rows = []
    expenses = results.get("total_expenses", 0)
    vacancy  = results.get("vacancy_rate", 0.05)
    parking_rev = results.get("parking_revenue_annual", 0)
    num_units_r = results.get("num_units", 1) or 1

    for label, cd in cost_scenarios:
        adj_cost    = base_cost * (1 + cd)
        req_noi     = adj_cost * threshold
        req_egi     = req_noi + expenses
        req_gross   = req_egi / (1 - vacancy) if (1 - vacancy) > 0 else req_egi
        req_rent_annual = req_gross - parking_rev
        req_rent_mo = req_rent_annual / (num_units_r * 12) if num_units_r > 0 else 0
        req_rent_sf = req_rent_annual / total_nsf / 12 if total_nsf > 0 else 0
        gap_mo      = req_rent_mo - base_rent
        be_rows.append({
            "Cost Scenario":             label,
            "Required Monthly Rent":     req_rent_mo,
            "Current Market Rent":       base_rent,
            "Gap (per month, per unit)": gap_mo,
            "Required Rent (per SF/mo)": req_rent_sf,
        })

    # Feasibility breakeven row — cost level where current market rents are exactly sufficient
    _req_cost_feas   = base_noi / threshold if threshold > 0 else base_cost
    _cost_delta_feas = (_req_cost_feas - base_cost) / base_cost if base_cost > 0 else 0
    _feas_req_noi    = _req_cost_feas * threshold          # = base_noi
    _feas_req_egi    = _feas_req_noi + expenses
    _feas_req_gross  = _feas_req_egi / (1 - vacancy) if (1 - vacancy) > 0 else _feas_req_egi
    _feas_rent_mo    = (_feas_req_gross - parking_rev) / (num_units_r * 12) if num_units_r > 0 else 0
    _feas_rent_sf    = (_feas_req_gross - parking_rev) / total_nsf / 12 if total_nsf > 0 else 0
    be_rows.append({
        "Cost Scenario":             f"Needed for feasibility ({_cost_delta_feas:+.1%} vs projected)",
        "Required Monthly Rent":     _feas_rent_mo,
        "Current Market Rent":       base_rent,
        "Gap (per month, per unit)": _feas_rent_mo - base_rent,
        "Required Rent (per SF/mo)": _feas_rent_sf,
    })

    df_be = pd.DataFrame(be_rows)

    def _style_be_row(row):
        if row.name == len(df_be) - 1:
            return ["background-color:#1a3a5c;color:white;font-weight:bold"] * len(row)
        styles = [""] * len(row)
        gap_idx = list(df_be.columns).index("Gap (per month, per unit)")
        v = row["Gap (per month, per unit)"]
        if v <= 0:    styles[gap_idx] = "background-color:#c6efce;color:#375623"
        elif v < 200: styles[gap_idx] = "background-color:#fff3cd;color:#856404"
        else:         styles[gap_idx] = "background-color:#f8d7da;color:#721c24"
        return styles

    st.dataframe(
        df_be.style
            .apply(_style_be_row, axis=1)
            .format({
                "Required Monthly Rent":     "${:,.0f}",
                "Current Market Rent":       "${:,.0f}",
                "Gap (per month, per unit)": "${:+,.0f}",
                "Required Rent (per SF/mo)": "${:.2f}",
            }),
        use_container_width=True, hide_index=True,
    )
    st.caption("Green = market rents already cover it · Yellow = small gap · Red = large gap · Navy = feasibility breakeven")


# ---------------------------------------------------------------------------
with tab_howto:
    _threshold_h = results.get("return_on_cost_threshold", 0.06)

    # ---- Scenario deep-dive (top) ----
    st.markdown("#### How could this project become feasible?")
    st.caption("Select a scenario to run the full financial model with one variable changed.")

    scenario_name = st.selectbox("Scenario", list(SCENARIOS.keys()), index=0, key="howto_scenario_sel")
    chosen = SCENARIOS[scenario_name]
    st.info(chosen["description"])

    try:
        scenario_results = _run_scenario(assumptions, user_inputs, chosen["modifier"])
        s_roc      = scenario_results.get("return_on_cost", 0)
        s_cost     = scenario_results.get("total_dev_cost", 0)
        s_noi      = scenario_results.get("noi", 0)
        s_feasible = scenario_results.get("is_feasible", False)
        base_roc_r = results.get("return_on_cost", 0)
        delta_roc  = s_roc - base_roc_r
        delta_cost = s_cost - results.get("total_dev_cost", 0)
        delta_noi  = s_noi - results.get("noi", 0)

        s_badge       = "FEASIBLE" if s_feasible else "NOT FEASIBLE"
        s_badge_color = "#375623" if s_feasible else "#9C0006"
        st.markdown(
            f'<div style="background:{s_badge_color};color:white;border-radius:6px;'
            f'padding:10px 18px;font-weight:bold;font-size:1.1em;display:inline-block;margin:8px 0;">'
            f'{s_badge} — {s_roc:.2%} Return on Cost</div>',
            unsafe_allow_html=True,
        )

        sc1, sc2, sc3 = st.columns(3)
        sc1.metric("Return on Cost",         f"{s_roc:.2%}",    delta=f"{delta_roc:+.2%} vs baseline")
        sc2.metric("Total Development Cost", f"${s_cost:,.0f}", delta=f"${delta_cost:+,.0f} vs baseline",
                   delta_color="inverse")
        sc3.metric("Net Operating Income",   f"${s_noi:,.0f}",  delta=f"${delta_noi:+,.0f} vs baseline")

        st.markdown("**Baseline vs. Scenario — Key Lines**")
        compare_rows = [
            ("Total Development Cost",    results.get("total_dev_cost", 0), s_cost),
            ("  Land",                    results.get("land_cost", 0),       scenario_results.get("land_cost", 0)),
            ("  Hard Construction Costs", results.get("hard_costs", 0),      scenario_results.get("hard_costs", 0)),
            ("  Parking Construction",    results.get("parking_hard_cost", 0), scenario_results.get("parking_hard_cost", 0)),
            ("  Demolition",              results.get("demolition_cost", 0), scenario_results.get("demolition_cost", 0)),
            ("  Soft Costs",              results.get("soft_costs", 0),      scenario_results.get("soft_costs", 0)),
            ("Net Operating Income",      results.get("noi", 0),             s_noi),
            ("  Gross Revenue",           results.get("gross_revenue", 0),   scenario_results.get("gross_revenue", 0)),
            ("  Total Expenses",          results.get("total_expenses", 0),  scenario_results.get("total_expenses", 0)),
            ("  Property Taxes",          results.get("property_taxes", 0),  scenario_results.get("property_taxes", 0)),
            ("Return on Cost",            results.get("return_on_cost", 0),  s_roc),
        ]
        df_cmp = pd.DataFrame(compare_rows, columns=["Line Item", "Baseline", "Scenario"])

        def _fmt_cmp(row):
            if "Return on Cost" in row["Line Item"]:
                return [row["Line Item"], f"{row['Baseline']:.2%}", f"{row['Scenario']:.2%}"]
            return [row["Line Item"], f"${row['Baseline']:,.0f}", f"${row['Scenario']:,.0f}"]

        df_cmp_fmt = pd.DataFrame([_fmt_cmp(r) for _, r in df_cmp.iterrows()],
                                   columns=["Line Item", "Baseline", "Scenario"])
        st.dataframe(df_cmp_fmt, use_container_width=True, hide_index=True)

        if delta_roc > 0:
            st.success(
                f"This scenario improves the return on cost by **{delta_roc:+.2%}** "
                f"(from {base_roc_r:.2%} to {s_roc:.2%})"
                + (" — and makes the project feasible." if s_feasible and not results.get("is_feasible") else ".")
            )
        elif delta_roc < 0:
            st.warning(f"This scenario reduces the return on cost by {delta_roc:.2%}.")
        else:
            st.info("This scenario does not materially change the return on cost.")

    except Exception as e:
        st.error(f"Could not run scenario: {e}")

    st.divider()

    # ---- All-scenarios ranked table (below) ----
    st.markdown("#### Levers that could change feasibility")
    st.caption(
        f"All scenarios run the full financial model with one variable changed. "
        f"Needs {_threshold_h:.0%} return on cost to be feasible. "
        "Ranked best lever first."
    )

    _base_roc_h  = results.get("return_on_cost", 0)
    _base_cost_h = results.get("total_dev_cost", 0)

    _howto_rows = []
    for _s_name, _s_def in SCENARIOS.items():
        try:
            _sr = _run_scenario(assumptions, user_inputs, _s_def["modifier"])
            _s_roc_h  = _sr.get("return_on_cost", 0)
            _s_cost_h = _sr.get("total_dev_cost", 0)
            _s_noi_h  = _sr.get("noi", 0)
            _howto_rows.append({
                "Scenario":     _s_name,
                "What changes": _s_def["description"],
                "ROC Change":   _s_roc_h - _base_roc_h,
                "New ROC":      _s_roc_h,
                "Cost Change":  _s_cost_h - _base_cost_h,
                "New NOI":      _s_noi_h,
                "Feasible?":    "Yes" if _sr.get("is_feasible", False) else "No",
            })
        except Exception:
            pass

    _howto_rows.sort(key=lambda r: r["ROC Change"], reverse=True)

    if _howto_rows:
        _df_howto = pd.DataFrame(_howto_rows)

        def _color_howto_roc(val):
            if val > 0.005: return "background-color:#c6efce;color:#375623"
            if val > 0:     return "background-color:#d4edda;color:#155724"
            return "background-color:#f8d7da;color:#721c24"

        def _color_howto_feasible(val):
            if val == "Yes": return "background-color:#c6efce;color:#375623"
            return "background-color:#f8d7da;color:#721c24"

        st.dataframe(
            _df_howto.style
                .applymap(_color_howto_roc,      subset=["ROC Change"])
                .applymap(_color_howto_feasible, subset=["Feasible?"])
                .format({
                    "ROC Change":  "{:+.2%}",
                    "New ROC":     "{:.2%}",
                    "Cost Change": "${:+,.0f}",
                    "New NOI":     "${:,.0f}",
                }),
            use_container_width=True,
            hide_index=True,
            height=360,
        )

        _top = _howto_rows[0]
        if _top["ROC Change"] > 0:
            st.success(
                f"**Biggest lever:** {_top['Scenario']} improves ROC by {_top['ROC Change']:+.2%} "
                f"(to {_top['New ROC']:.2%})"
                + (" — this alone makes the project feasible." if _top["Feasible?"] == "Yes" else ".")
            )
    else:
        st.info("Could not compute scenarios.")
