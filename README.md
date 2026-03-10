# Real Estate Development Feasibility Calculator

AI-powered feasibility calculator for real estate development. Claude researches all financial assumptions live from the web.

## Setup

1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

2. Set your Anthropic API key:
   ```
   set ANTHROPIC_API_KEY=sk-ant-...        # Windows
   export ANTHROPIC_API_KEY=sk-ant-...     # macOS/Linux
   ```

3. Run the app:
   ```
   streamlit run app.py
   ```

## File Structure

| File | Purpose |
|------|---------|
| `app.py` | Streamlit UI — sidebar inputs, results tabs, export |
| `research.py` | Claude API calls with web_search — populates all assumptions |
| `calculations.py` | Financial model — costs, revenue, NOI, returns, IRR |
| `zoning_check.py` | Post-calculation zoning adjustment pass |
| `export.py` | Excel export (6-tab workbook) |

## Notes

- The first run for a new location takes 60–120 seconds while Claude researches ~10 data categories.
- Results are cached per (location, building type, use type) — changing these inputs triggers a fresh research pass.
- All dollar values come from live web research — no hardcoded assumptions.
- `web_search` tool requires `anthropic>=0.28.0` with the `web_search_20250305` tool enabled.
