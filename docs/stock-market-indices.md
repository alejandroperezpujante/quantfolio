# Major Stock Market Indices (S&P 500, IBEX 35, EURO STOXX 50)

An equity market index is a value computed from the prices of a defined basket of shares, used as a benchmark for a
market or market segment. Three indices are relevant to this workshop.

The **S&P 500** is administered by S&P Dow Jones Indices (a division of S&P Global). It measures the
large-capitalization segment of the U.S. equity market, is composed of 500 constituent companies, and is weighted by
float-adjusted market capitalization. It is calculated in U.S. dollars and is quoted both as a price index and as
total-return versions.

The **IBEX 35** is the benchmark of the Spanish equity market, administered by Sociedad de Bolsas, S.A. (a BME Group
company; BME is a SIX company). It comprises the 35 most liquid stocks traded on the Spanish continuous market (SIBE),
is free-float market-capitalization weighted with a maximum weight limit of 20% per constituent at reviews, is
euro-denominated, and is a price-return index (total-return and net-return variants also exist). Its base level was
3,000 on 29 December 1989.

The **EURO STOXX 50** is administered by STOXX Ltd (Deutsche Börse Group / ISS STOXX). It tracks 50 Eurozone blue-chip
supersector leaders, is free-float market-capitalization weighted with a maximum weight of 10% per constituent, and is
euro-denominated, with real-time dissemination between 09:00 and 18:00 CET.

Index levels themselves are not directly investable; investors obtain exposure through replicating instruments such as
index funds, exchange-traded funds (ETFs) and derivatives that track the index.

## Why it matters for the B1-T1 toolkit

The toolkit ingests index and equity price series and treats them as comparable time series. Indices supply the
benchmarks against which single stocks and portfolios are assessed, and each index's provider, weighting scheme and
currency determine how its series behaves.

## Key facts and formulas

- A capitalization-weighted index level equals the sum of (price × index shares) across constituents, divided by a
  divisor:

  $$
  \text{Index} = \frac{\sum_i \text{price}_i \times \text{shares}_i}{\text{divisor}}.
  $$

  The divisor is adjusted to keep the level continuous through corporate actions and rebalancing.
- S&P 500: 500 constituent companies; float-adjusted market-capitalization weighted; U.S. large-cap; calculated in USD.
- IBEX 35: 35 constituents; free-float market-capitalization weighted (20% cap); EUR; base level 3,000 on 29 December
  1989; launched 14 January 1992.
- EURO STOXX 50: 50 constituents; free-float market-capitalization weighted (10% cap); EUR; real-time 09:00–18:00 CET.
- "You cannot invest directly in a market index" — exposure is obtained indirectly through index funds/ETFs that track
  it.

## Sources

- <https://www.spglobal.com/spdji/en/methodology/article/sp-us-indices-methodology/> (accessed 2026-10-01; this official
  S&P DJI page returned HTTP 403 to automated retrieval at access time)
- <https://www.bolsasymercados.es/en/bme-exchange/faqs/what-is-ibex35.html> (accessed 2026-10-01)
- <https://www.bolsasymercados.es/dam/descargas/indices/regulacion/technical-regulations-calculation-ibex-indices-en.pdf>
  (accessed 2026-10-01)
- <https://stoxx.com/index/sx5e/> (accessed 2026-10-01)
- <https://www.investor.gov/introduction-investing/investing-basics/investment-products/mutual-funds-and-exchange-traded-4>
  (accessed 2026-10-01)
- <https://eur-lex.europa.eu/eli/reg/2016/1011/oj> (accessed 2026-10-01)
