# Common Macroeconomic Indicators

Macroeconomic indicators are aggregate statistics describing the state and direction of an economy. **Gross domestic
product (GDP)** measures the market value of the final goods and services produced in an economy over a period, without
double-counting intermediate goods. *Nominal* GDP is valued at current prices; *real* GDP is adjusted for price changes
and is the standard measure of growth. **Inflation** is the rate at which the general price level rises. It is tracked
with consumer price indices — the U.S. Consumer Price Index (CPI), the euro-area Harmonised Index of Consumer Prices
(HICP) and the U.S. Personal Consumption Expenditures (PCE) price index. The **year-over-year (annual) rate** compares a
price index with its value twelve months earlier. **Interest rates** divide into central-bank *policy rates* and *market
rates*. The Federal Reserve sets a target range for the federal funds rate; the ECB sets a deposit facility rate, main
refinancing rate and marginal lending rate. Sovereign bond **yields** are market-determined, and the **yield curve** is
the relationship between yields and remaining maturity (the term structure). The **unemployment rate** is the share of
the labour force that is jobless and actively seeking work.

## Why it matters for the B1-T1 toolkit

These series are the most common "extra data type" ingested alongside equity and index prices, and equity returns are
routinely interpreted against inflation, policy rates and growth. Because releases are scheduled and lag their reference
period, the calendar timing is part of the background.

## Key facts and formulas

- Expenditure identity: GDP = Consumption + Investment + Government spending + (Exports − Imports).
- Real GDP = nominal GDP adjusted for price changes; the GDP deflator is the broadest domestic price measure.
- Annual inflation = (index in month t / index in month t−12 − 1) × 100.
- The ECB defines its objective as 2% HICP inflation over the medium term; HICP is compiled by Eurostat using a common
  methodology.
- A yield curve with short-term yields above long-term yields is described as inverted (downward-sloping); the ECB
  publishes euro-area zero-coupon, forward and par yield curves.
- Unemployment rate = number unemployed / labour force.
- Releases lag the reference period and are revised: BLS publishes the CPI around the middle of the following month; BEA
  issues GDP in successive (advance, preliminary, third) estimates; official release calendars list forthcoming dates.

When the toolkit ingests these series it goes through ALFRED's archival CSV export, FRED's vintage database. Each
`MacroSeries` records the vintage it comes from in its `vintage_date` field, and `get_series(..., as_of=...)` returns the
values actually published as of a past date. Revisions and release lags therefore cannot leak into historical analysis
(the look-ahead bias these would otherwise introduce is avoided), and observations not yet released at the requested
vintage remain absent from the series.

## Sources

- <https://www.ecb.europa.eu/stats/macroeconomic_and_sectoral/hicp/html/index.en.html> (accessed 2026-10-01)
- <https://ec.europa.eu/eurostat/statistics-explained/index.php?title=Inflation_in_the_euro_area> (accessed 2026-10-01)
- <https://www.bea.gov/data/gdp/gross-domestic-product> (accessed 2026-10-01)
- <https://www.bea.gov/data/income-saving/personal-income> (accessed 2026-10-01)
- <https://data.worldbank.org/indicator/NY.GDP.MKTP.CD> (accessed 2026-10-01)
- <https://www.bls.gov/cpi/> (accessed 2026-10-01)
- <https://www.bls.gov/schedule/news_release/cpi.htm> (accessed 2026-10-01)
- <https://www.bls.gov/cps/> (accessed 2026-10-01)
- <https://www.federalreserve.gov/monetarypolicy/openmarket.htm> (accessed 2026-10-01)
- <https://www.ecb.europa.eu/stats/policy_and_exchange_rates/key_ecb_interest_rates/html/index.en.html> (accessed
  2026-10-01)
- <https://www.ecb.europa.eu/stats/financial_markets_and_interest_rates/euro_area_yield_curves/html/index.en.html>
  (accessed 2026-10-01)
- <https://www.ecb.europa.eu/press/calendars/statscal/html/index.en.html> (accessed 2026-10-01)
- <https://fred.stlouisfed.org/> (accessed 2026-10-01)
- Note: the IMF World Economic Outlook and OECD indicator pages could not be retrieved at the time of writing (HTTP 403
  responses) and are therefore not cited.
