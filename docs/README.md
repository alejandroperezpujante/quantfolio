# Background documentation

Researched background material for the **B1-T1 — Toolkit de Extracción, Análisis Bursátil y Gestión de Carteras**
assignment. These documents contain only definitions, standard formulas and cited facts. They do *not* contain
solutions, implementation guidance, or design advice.

- Assignment text (extracted): [assignment/Taller_B1_T1.md](assignment/Taller_B1_T1.md)
- All sources were accessed on **2026-10-01**.
- Trusted-source preference: central banks, BIS, IMF, World Bank, OECD, Eurostat, regulators, official index providers,
  exchanges, and university/established references. Investopedia and Wikipedia appear only as secondary/supporting
  references.

## Index

| Document                                                                           | Summary                                                                                                 | Sources |
|------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------|---------|
| [stock-market-indices.md](stock-market-indices.md)                                 | S&P 500, IBEX 35 and EURO STOXX 50: provider, constituents, weighting and currency.                     | 6       |
| [equity-securities.md](equity-securities.md)                                       | Common shares, tickers/ISINs, capitalization, dividends, splits, price vs total return.                 | 5       |
| [market-data-providers.md](market-data-providers.md)                               | yfinance, Alpha Vantage, Finnhub and Polygon.io/Massive, plus standard OHLCV and adjusted-close fields. | 9       |
| [trading-calendars-and-time-alignment.md](trading-calendars-and-time-alignment.md) | Trading days, holidays, session times/time zones, business-day conventions and temporal alignment.      | 5       |
| [returns-and-annualization.md](returns-and-annualization.md)                       | Simple vs log returns, total vs price return, arithmetic vs geometric average, annualization.           | 2       |
| [historical-volatility.md](historical-volatility.md)                               | Standard deviation of returns, realized vs implied volatility, root-time annualization, VIX.            | 4       |
| [modern-portfolio-theory.md](modern-portfolio-theory.md)                           | Markowitz mean-variance framework, diversification, efficient frontier, minimum-variance portfolio.     | 5       |
| [portfolio-return-and-variance.md](portfolio-return-and-variance.md)               | Weighted portfolio return, portfolio variance and the covariance-matrix form $w^{T} \Sigma w$.          | 5       |
| [correlation-and-covariance.md](correlation-and-covariance.md)                     | Covariance, Pearson correlation, covariance/correlation matrices and diversification.                   | 6       |
| [geometric-brownian-motion.md](geometric-brownian-motion.md)                       | GBM SDE and closed-form solution, lognormal prices, drift/volatility roles and limitations.             | 2       |
| [monte-carlo-simulation-in-finance.md](monte-carlo-simulation-in-finance.md)       | Random sampling, law of large numbers, pseudo-randomness, uses and $1/\sqrt{N}$ convergence.            | 3       |
| [portfolio-risk-measures.md](portfolio-risk-measures.md)                           | VaR (historical, parametric, Monte Carlo), expected shortfall, maximum drawdown and beta.               | 7       |
| [macroeconomic-indicators.md](macroeconomic-indicators.md)                         | GDP, inflation (CPI/HICP/PCE), interest rates and yield curves, unemployment, release calendars.        | 13      |
| [financial-statement-fundamentals.md](financial-statement-fundamentals.md)         | Balance sheet, income statement, cash flow, accounting identity, filings and common ratios.             | 6       |

## Notes on sourcing

- Some official pages (S&P Dow Jones Indices methodology, IMF World Economic Outlook, OECD indicator pages) returned
  HTTP 403 to automated retrieval; the affected documents state this caveat explicitly rather than substituting invented
  facts.
- Documents that depend mainly on university or established-general references (for example `modern-portfolio-theory.md`
  or `monte-carlo-simulation-in-finance.md`) count a smaller number of primary sources.
