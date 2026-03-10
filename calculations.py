"""
calculations.py — Financial Model
Receives researched assumptions dict and user inputs.
Returns a comprehensive results dict with all financial metrics.
"""

import numpy_financial as npf
from typing import Optional


# ---------------------------------------------------------------------------
# Constants / Defaults (only used when research returns null)
# ---------------------------------------------------------------------------
DEFAULT_NET_TO_GROSS = 0.85          # NSF / GSF ratio
DEFAULT_SOFT_COST_RATE = 0.18        # 18% of hard costs
DEFAULT_COST_OF_SALE = 0.04          # 4% of exit value
DEFAULT_VACANCY_RATE = 0.05          # 5% vacancy
DEFAULT_CONSTRUCTION_PERIOD_MONTHS = 18
DEFAULT_PARKING_REVENUE_MONTH = 125  # $/space/month (surface, if rented)

# Feasibility thresholds
RENTAL_ROC_THRESHOLD = 0.06          # 6% return on cost
FOR_SALE_PROFIT_THRESHOLD = 0.15     # 15% profit margin

# Unit size defaults (SF) if research doesn't return them
DEFAULT_UNIT_SIZES = {
    "studio": 520, "1br": 720, "2br": 1000, "3br": 1250, "4br": 1500
}

# Building type-specific net-to-gross ratios
BUILDING_NTG = {
    "High-Rise 10+ stories": 0.82,
    "Mid-Rise 5-9 stories":  0.84,
    "Low-Rise 1-4 stories":  0.87,
    "Townhomes":             0.90,
}

# Parking ratio fallbacks by bedroom if zoning research is null
DEFAULT_PARKING_RATIOS = {
    "studio": 0.75, "1br": 1.0, "2br": 1.5, "3br": 2.0, "4br": 2.0
}


def _safe(val, default=0.0):
    """Return val if not None, else default."""
    if val is None:
        return default
    return float(val)


def _get_unit_sizes(rent_research: dict) -> dict:
    """Extract average unit sizes from market rent research."""
    sizes = {}
    for ut in ["studio", "1br", "2br", "3br", "4br"]:
        key = f"{ut}_avg_sf"
        v = rent_research.get(key, {})
        sizes[ut] = _safe(v.get("value") if isinstance(v, dict) else v, DEFAULT_UNIT_SIZES[ut])
    return sizes


def _weighted_avg_parking_ratio(unit_mix: dict, zoning: dict) -> float:
    """
    Compute weighted average parking ratio from unit mix and zoning requirements.
    unit_mix: {"studio": 20, "1br": 40, ...} (percentages)
    zoning:   result from research_zoning
    """
    mapping = {
        "studio": "parking_studio",
        "1br":    "parking_1br",
        "2br":    "parking_2br",
        "3br":    "parking_3br",
        "4br":    "parking_3br",   # use 3br rate for 4br if not available
    }
    total_pct = sum(unit_mix.values()) or 1
    weighted = 0.0
    for ut, pct in unit_mix.items():
        key = mapping.get(ut, "parking_2br")
        z_item = zoning.get(key, {})
        if isinstance(z_item, dict):
            ratio = _safe(z_item.get("value"), DEFAULT_PARKING_RATIOS.get(ut, 1.0))
        else:
            ratio = DEFAULT_PARKING_RATIOS.get(ut, 1.0)
        weighted += (pct / total_pct) * ratio
    return weighted


def run_calculations(
    user_inputs: dict,
    assumptions: dict,
) -> dict:
    """
    Main financial model.

    Parameters
    ----------
    user_inputs : dict
        {
          "location": str,
          "use_type": str,        # "Multifamily Rental" | "For-Sale Condo" | "Mixed-Use" | "Affordable / LIHTC"
          "lihtc_type": str,      # "4%" | "9%" | None
          "building_type": str,
          "num_units": int,
          "parcel_acres": float,
          "unit_mix": {"studio": %, "1br": %, "2br": %, "3br": %, "4br": %},  # sum = 100
          "affordability_mix": {"30%AMI": %, "50%AMI": %, "60%AMI": %, "80%AMI": %, "Market": %},  # sum = 100
        }

    assumptions : dict
        Flat dict containing all research results (each research function's output
        merged in, prefixed by category).
        Keys include: zoning, land, construction, rents, cap_rates,
        interest_rates, tax_rates, ami, opex, employment, for_sale_comps, lihtc

    Returns
    -------
    dict with full breakdown and feasibility verdict.
    """

    u = user_inputs
    num_units = int(u["num_units"])
    parcel_acres = float(u.get("parcel_acres") or 1.0)
    parcel_sf = parcel_acres * 43_560
    unit_mix_pct = u.get("unit_mix", {"1br": 100})
    use_type = u["use_type"]
    building_type = u["building_type"]
    is_affordable = (use_type == "Affordable / LIHTC")
    is_for_sale = (use_type in ("For-Sale Condo", "Mixed-Use"))

    # -------------------------------------------------------------------
    # Unpack assumptions (with safe fallbacks)
    # -------------------------------------------------------------------
    zoning = assumptions.get("zoning", {})
    land_res = assumptions.get("land", {})
    construction_res = assumptions.get("construction", {})
    rents_res = assumptions.get("rents", {})
    cap_res = assumptions.get("cap_rates", {})
    interest_res = assumptions.get("interest_rates", {})
    tax_res = assumptions.get("tax_rates", {})
    ami_res = assumptions.get("ami", {})
    opex_res = assumptions.get("opex", {})
    employment_res = assumptions.get("employment", {})
    for_sale_res = assumptions.get("for_sale_comps", {})
    lihtc_res = assumptions.get("lihtc", {})

    def rval(d, key, default=None):
        """Safely extract 'value' from a nested research dict."""
        item = d.get(key, {})
        if isinstance(item, dict):
            return item.get("value", default)
        return item if item is not None else default

    # -------------------------------------------------------------------
    # Unit Sizes & Net SF
    # -------------------------------------------------------------------
    unit_sizes = _get_unit_sizes(rents_res)
    total_pct = sum(unit_mix_pct.values()) or 100

    weighted_avg_size_sf = sum(
        (pct / total_pct) * unit_sizes.get(ut, DEFAULT_UNIT_SIZES.get(ut, 800))
        for ut, pct in unit_mix_pct.items()
    )

    total_nsf = num_units * weighted_avg_size_sf
    ntg_ratio = BUILDING_NTG.get(building_type, DEFAULT_NET_TO_GROSS)
    total_gsf = total_nsf / ntg_ratio

    # -------------------------------------------------------------------
    # Hard Costs
    # -------------------------------------------------------------------
    hard_cost_per_gsf = _safe(rval(construction_res, "hard_cost_per_gsf"), 300.0)
    hard_costs = hard_cost_per_gsf * total_gsf

    # -------------------------------------------------------------------
    # Parking
    # -------------------------------------------------------------------
    parking_ratio = _weighted_avg_parking_ratio(unit_mix_pct, zoning)
    num_parking_spaces = round(num_units * parking_ratio)

    # Determine parking type from building type
    if building_type in ("High-Rise 10+ stories", "Mid-Rise 5-9 stories"):
        cost_per_space = _safe(rval(construction_res, "parking_structured_per_space"), 35_000)
    else:
        cost_per_space = _safe(rval(construction_res, "parking_surface_per_space"), 5_000)

    parking_hard_cost = num_parking_spaces * cost_per_space

    # -------------------------------------------------------------------
    # Demolition Cost (if existing structures on site)
    # -------------------------------------------------------------------
    parcel_res = assumptions.get("parcel", {})
    existing_bldg_sf = _safe(rval(parcel_res, "existing_building_sf"), 0.0)
    # $15/SF is a conservative all-in demolition cost for mid-rise structures
    demolition_cost = existing_bldg_sf * 15.0 if existing_bldg_sf > 0 else 0.0

    # -------------------------------------------------------------------
    # Soft Costs
    # -------------------------------------------------------------------
    soft_cost_rate = DEFAULT_SOFT_COST_RATE
    soft_costs = soft_cost_rate * (hard_costs + parking_hard_cost)

    # -------------------------------------------------------------------
    # Land Cost
    # -------------------------------------------------------------------
    land_cost_per_sf = _safe(rval(land_res, "land_cost_per_sf"), 50.0)
    land_cost = land_cost_per_sf * parcel_sf

    # -------------------------------------------------------------------
    # Construction Financing
    # -------------------------------------------------------------------
    construction_rate_annual = _safe(rval(interest_res, "construction_loan_rate"), 0.085)
    construction_months = DEFAULT_CONSTRUCTION_PERIOD_MONTHS
    construction_loan_amount = (hard_costs + parking_hard_cost + soft_costs + demolition_cost) * 0.70  # 70% LTC
    # Simple interest on average balance (50% drawn on average)
    construction_interest = (
        construction_loan_amount * 0.5 *
        (construction_rate_annual / 12) *
        construction_months
    )

    # -------------------------------------------------------------------
    # Total Development Cost
    # -------------------------------------------------------------------
    total_dev_cost = hard_costs + parking_hard_cost + soft_costs + land_cost + construction_interest + demolition_cost

    # -------------------------------------------------------------------
    # Revenue
    # -------------------------------------------------------------------
    vacancy_rate = _safe(rval(rents_res, "vacancy_rate"), DEFAULT_VACANCY_RATE)
    affordability_mix = u.get("affordability_mix", {"Market": 100})
    market_pct = affordability_mix.get("Market", 100) / 100.0

    # Market rent revenue
    market_units = round(num_units * market_pct)
    affordable_units = num_units - market_units

    # Weighted monthly market rent per unit
    monthly_rents = {
        "studio": _safe(rval(rents_res, "studio"), 1500),
        "1br":    _safe(rval(rents_res, "1br"), 2000),
        "2br":    _safe(rval(rents_res, "2br"), 2600),
        "3br":    _safe(rval(rents_res, "3br"), 3200),
        "4br":    _safe(rval(rents_res, "4br"), 3800),
    }
    weighted_monthly_rent = sum(
        (pct / total_pct) * monthly_rents.get(ut, 2000)
        for ut, pct in unit_mix_pct.items()
    )

    market_rent_annual = market_units * weighted_monthly_rent * 12

    # Affordable rent revenue
    affordable_rent_annual = 0.0
    affordable_unit_revenue_detail = {}
    if is_affordable and affordable_units > 0:
        ami_total_pct = sum(v for k, v in affordability_mix.items() if k != "Market") or 1
        for ami_label, ami_pct in affordability_mix.items():
            if ami_label == "Market" or ami_pct == 0:
                continue
            ami_key = f"ami_{ami_label.replace('%', '').replace(' AMI', '').lower()}"
            ami_data = ami_res.get(ami_key, {})
            # Use 1BR rent as weighted proxy; real app would use unit mix
            ami_rent_1br = _safe(
                ami_data.get("max_rent_1br", {}).get("value") if isinstance(ami_data, dict) else None,
                weighted_monthly_rent * 0.65
            )
            ami_units_this_level = round(num_units * (ami_pct / 100.0))
            rev = ami_units_this_level * ami_rent_1br * 12
            affordable_rent_annual += rev
            affordable_unit_revenue_detail[ami_label] = {
                "units": ami_units_this_level,
                "monthly_rent": ami_rent_1br,
                "annual": rev,
            }

    # Parking revenue (modest — some spaces rented)
    parking_revenue_annual = num_parking_spaces * DEFAULT_PARKING_REVENUE_MONTH * 12 * 0.50

    gross_revenue = market_rent_annual + affordable_rent_annual + parking_revenue_annual
    egi = gross_revenue * (1 - vacancy_rate)

    # -------------------------------------------------------------------
    # Operating Expenses
    # -------------------------------------------------------------------
    opex_per_unit_year = _safe(rval(opex_res, "total_opex_per_unit_year"), 6500)
    total_opex = opex_per_unit_year * num_units

    # Management fee
    mgmt_fee_pct = _safe(rval(opex_res, "management_fee_pct_egi"), 0.04)
    mgmt_fee = egi * mgmt_fee_pct

    # Property taxes
    effective_tax_rate = _safe(rval(tax_res, "effective_tax_rate"), 0.012)
    # Estimate assessed value ~ 90% of total dev cost as a reasonable proxy
    assessed_value = total_dev_cost * 0.90
    property_taxes = assessed_value * effective_tax_rate

    # CapEx reserve
    capex_per_unit = _safe(rval(opex_res, "capex_reserve_per_unit_year"), 300)
    capex_reserve = capex_per_unit * num_units

    total_expenses = total_opex + mgmt_fee + property_taxes + capex_reserve

    # -------------------------------------------------------------------
    # NOI and Returns
    # -------------------------------------------------------------------
    noi = egi - total_expenses
    return_on_cost = noi / total_dev_cost if total_dev_cost > 0 else 0

    # Feasibility threshold
    if is_for_sale:
        threshold = FOR_SALE_PROFIT_THRESHOLD
    else:
        threshold = RENTAL_ROC_THRESHOLD

    # -------------------------------------------------------------------
    # For-Sale specific: profit margin
    # -------------------------------------------------------------------
    for_sale_margin = None
    total_for_sale_revenue = None
    if is_for_sale:
        price_per_sf = _safe(rval(for_sale_res, "median_sale_price_per_sf"), 600)
        total_for_sale_revenue = price_per_sf * total_nsf
        profit = total_for_sale_revenue - total_dev_cost
        for_sale_margin = profit / total_for_sale_revenue if total_for_sale_revenue > 0 else 0
        return_on_cost = for_sale_margin  # use margin as primary metric for for-sale

    # -------------------------------------------------------------------
    # Exit Value (rental only)
    # -------------------------------------------------------------------
    cap_rate = _safe(rval(cap_res, "cap_rate"), 0.055)
    exit_value = noi / cap_rate if cap_rate > 0 else 0
    cost_of_sale = DEFAULT_COST_OF_SALE
    net_exit_proceeds = exit_value * (1 - cost_of_sale)

    # -------------------------------------------------------------------
    # Simplified Levered IRR (rental only)
    # -------------------------------------------------------------------
    # Cash flows: equity outlay, then stabilized NOI for 5 years, then exit
    irr = None
    if not is_for_sale:
        equity_invested = total_dev_cost - construction_loan_amount
        perm_loan_rate = _safe(rval(interest_res, "perm_loan_rate"), 0.07)
        perm_loan_amount = exit_value * 0.65  # 65% LTV at exit/refi
        annual_debt_service = perm_loan_amount * perm_loan_rate * 1.15  # approx P&I
        annual_levered_cf = noi - annual_debt_service

        # 5-year hold: year 0 equity, years 1-5 levered NOI, year 5 + net sale proceeds
        if equity_invested > 0:
            cash_flows = [-equity_invested] + [annual_levered_cf] * 4 + [
                annual_levered_cf + net_exit_proceeds - perm_loan_amount
            ]
            try:
                irr_val = npf.irr(cash_flows)
                irr = float(irr_val) if irr_val is not None and not (irr_val != irr_val) else None
            except Exception:
                irr = None

    # -------------------------------------------------------------------
    # Back-solve: required rent to be feasible
    # -------------------------------------------------------------------
    if not is_for_sale:
        # Solve for rent that achieves RENTAL_ROC_THRESHOLD
        # NOI_target = total_dev_cost * threshold
        # EGI_target = NOI_target + total_expenses
        # gross_rev_target = EGI_target / (1 - vacancy_rate)
        noi_target = total_dev_cost * RENTAL_ROC_THRESHOLD
        egi_target = noi_target + total_expenses
        gross_rev_target = egi_target / (1 - vacancy_rate) if (1 - vacancy_rate) > 0 else egi_target
        # Remove parking revenue (assumed fixed)
        rent_rev_target = gross_rev_target - parking_revenue_annual
        # Market units drive this (affordable rents assumed fixed)
        if market_units > 0:
            required_monthly_rent = (rent_rev_target - affordable_rent_annual) / (market_units * 12)
        else:
            required_monthly_rent = rent_rev_target / (num_units * 12)
    else:
        # For-sale: required price/SF to hit 15% margin
        # total_rev_target = total_dev_cost / (1 - threshold)
        rev_target = total_dev_cost / (1 - FOR_SALE_PROFIT_THRESHOLD) if FOR_SALE_PROFIT_THRESHOLD < 1 else 0
        required_monthly_rent = rev_target / total_nsf  # here it means required $/SF sale price

    # -------------------------------------------------------------------
    # Feasibility Verdict
    # -------------------------------------------------------------------
    is_feasible = return_on_cost >= threshold

    # Demand context from employment research
    demand_narrative = ""
    if isinstance(employment_res, dict):
        dn = employment_res.get("demand_narrative", {})
        if isinstance(dn, dict):
            demand_narrative = dn.get("value", "") or ""
        elif isinstance(dn, str):
            demand_narrative = dn

    gap_pct = abs(return_on_cost - threshold) / threshold * 100 if threshold > 0 else 0
    if is_feasible:
        verdict_explanation = (
            f"Project achieves a {return_on_cost:.1%} return on cost, exceeding the "
            f"{threshold:.0%} threshold by {gap_pct:.1f}%. "
        )
    else:
        if is_for_sale:
            cost_excess = total_dev_cost - (total_for_sale_revenue or 0) * (1 - threshold)
            verdict_explanation = (
                f"Development costs exceed projected sale revenue by {cost_excess:,.0f}, "
                f"yielding only a {return_on_cost:.1%} profit margin vs. the {threshold:.0%} threshold. "
            )
        else:
            rent_gap_pct = ((required_monthly_rent - weighted_monthly_rent) / weighted_monthly_rent * 100
                            if weighted_monthly_rent > 0 else 0)
            verdict_explanation = (
                f"Construction and land costs generate only a {return_on_cost:.1%} return on cost "
                f"vs. the {threshold:.0%} threshold — rents would need to be "
                f"~{rent_gap_pct:.0f}% higher (${required_monthly_rent:,.0f}/mo) to be feasible. "
            )

    if demand_narrative:
        verdict_explanation += demand_narrative

    # -------------------------------------------------------------------
    # Assemble results dict
    # -------------------------------------------------------------------
    return {
        # ---- Feasibility ----
        "is_feasible": is_feasible,
        "return_on_cost": return_on_cost,
        "return_on_cost_threshold": threshold,
        "verdict_explanation": verdict_explanation,
        "for_sale_margin": for_sale_margin,

        # ---- Sizing ----
        "num_units": num_units,
        "market_units": market_units,
        "affordable_units": affordable_units,
        "weighted_avg_unit_size_sf": weighted_avg_size_sf,
        "total_nsf": total_nsf,
        "total_gsf": total_gsf,
        "ntg_ratio": ntg_ratio,
        "num_parking_spaces": num_parking_spaces,
        "parking_ratio": parking_ratio,

        # ---- Development Costs ----
        "hard_cost_per_gsf": hard_cost_per_gsf,
        "hard_costs": hard_costs,
        "parking_hard_cost": parking_hard_cost,
        "soft_cost_rate": soft_cost_rate,
        "soft_costs": soft_costs,
        "land_cost_per_sf": land_cost_per_sf,
        "land_cost": land_cost,
        "construction_interest": construction_interest,
        "demolition_cost": demolition_cost,
        "existing_building_sf": existing_bldg_sf,
        "total_dev_cost": total_dev_cost,
        "cost_per_unit": total_dev_cost / num_units if num_units else 0,

        # ---- Revenue ----
        "weighted_monthly_rent": weighted_monthly_rent,
        "market_rent_annual": market_rent_annual,
        "affordable_rent_annual": affordable_rent_annual,
        "affordable_unit_revenue_detail": affordable_unit_revenue_detail,
        "parking_revenue_annual": parking_revenue_annual,
        "gross_revenue": gross_revenue,
        "vacancy_rate": vacancy_rate,
        "egi": egi,

        # ---- OpEx ----
        "opex_per_unit_year": opex_per_unit_year,
        "total_opex": total_opex,
        "mgmt_fee": mgmt_fee,
        "property_taxes": property_taxes,
        "effective_tax_rate": effective_tax_rate,
        "capex_reserve": capex_reserve,
        "total_expenses": total_expenses,

        # ---- NOI & Exit ----
        "noi": noi,
        "cap_rate": cap_rate,
        "exit_value": exit_value,
        "net_exit_proceeds": net_exit_proceeds,
        "irr": irr,

        # ---- For-Sale ----
        "total_for_sale_revenue": total_for_sale_revenue,

        # ---- Back-solve ----
        "required_monthly_rent": required_monthly_rent,

        # ---- Monthly rents by unit type ----
        "monthly_rents": monthly_rents,
    }


def build_cash_flow_waterfall(results: dict, construction_months: int = 18, hold_years: int = 9) -> list:
    """
    Build a 120-month cash flow waterfall for export.
    Returns list of dicts: {month, period, gross_revenue, vacancy_loss, egi, opex, noi, debt_service, levered_cf}
    """
    rows = []
    total_months = construction_months + hold_years * 12

    gross_monthly = results["gross_revenue"] / 12
    opex_monthly = results["total_expenses"] / 12
    noi_monthly = results["noi"] / 12
    vacancy_rate = results["vacancy_rate"]

    construction_loan = results["total_dev_cost"] * 0.70
    perm_loan = results["exit_value"] * 0.65 if results["exit_value"] > 0 else 0

    for m in range(1, total_months + 1):
        if m <= construction_months:
            period = "Construction"
            gross = 0
            vac = 0
            egi = 0
            opex = 0
            noi = 0
            ds = -(construction_loan * 0.5 * (results.get("hard_cost_per_gsf", 0.085) / 12))
        else:
            period = "Operations"
            gross = gross_monthly
            vac = gross * vacancy_rate
            egi = gross - vac
            opex = opex_monthly
            noi = noi_monthly
            ds = -(perm_loan * 0.07 / 12 * 1.15) if perm_loan > 0 else 0

        rows.append({
            "month": m,
            "period": period,
            "gross_revenue": round(gross, 2),
            "vacancy_loss": round(-vac, 2),
            "egi": round(egi, 2),
            "opex": round(-opex, 2),
            "noi": round(noi, 2),
            "debt_service": round(ds, 2),
            "levered_cf": round(noi + ds, 2),
        })

    return rows
