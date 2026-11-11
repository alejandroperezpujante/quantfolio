# Common macroeconomic indicators

Macroeconomic indicators are aggregate statistics that describe the state and direction of an economy. **Gross
domestic product (GDP)** is the market value of final goods and services produced over a period, counted without
duplicating intermediate goods. *Nominal* GDP uses current prices. *Real* GDP adjusts for price changes and is the
standard measure of growth.

**Inflation** is the rate at which the general price level rises. It is commonly tracked with the U.S. Consumer Price
Index (CPI), the euro-area Harmonised Index of Consumer Prices (HICP) and the U.S. Personal Consumption Expenditures
(PCE) price index. The **year-over-year rate** compares a price index with its value twelve months earlier.

**Interest rates** include central-bank *policy rates* and *market rates*. The Federal Reserve sets a target range
for the federal funds rate. The ECB sets a deposit facility rate, a main refinancing rate and a marginal lending
rate. Sovereign bond **yields** are set by the market. The **yield curve** relates yields to remaining maturity and
is also called the term structure. The **unemployment rate** is the share of the labour force that is jobless and
actively seeking work.

## Use in Quantfolio

Read each release against its reference period and publication lag. Request ALFRED vintages with `as_of` to keep
revisions and look-ahead bias out of historical analysis.

## Facts and formulas

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

The toolkit ingests these series through ALFRED, FRED's vintage database, using its archival CSV export. Each
`MacroSeries` records the vintage it comes from in its `vintage_date` field, and `get_series(..., as_of=...)` returns the
values published as of a past date. This keeps revisions and release lags out of historical analysis and avoids
look-ahead bias. Observations not yet released at the requested vintage remain absent from the series. If the endpoint
serves a different vintage from the one requested, for example when ALFRED clamps a future date to its latest vintage,
`get_series` raises `ValueError`. It does not label the values with a date they do not belong to.

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
