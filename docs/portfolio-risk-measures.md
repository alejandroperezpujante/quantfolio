# Portfolio Risk Measures Used in Reports

Portfolio risk measures summarise the potential for loss of a portfolio. **Value at Risk (VaR)** is a quantile measure:
the loss that is not expected to be exceeded over a given horizon at a given confidence level. VaR is defined by two
parameters, the **confidence level** (e.g. 95% or 99%) and the **horizon** (e.g. one day or ten days); these are chosen
by the analyst and are not fixed by the definition. The main estimation approaches are **historical simulation**, which
applies the observed historical distribution of returns without assuming a parametric form; the **parametric (
variance–covariance) approach**, which typically assumes normally distributed returns and linear exposures and uses a
mean vector and covariance matrix; and **Monte Carlo simulation**, which generates many scenarios from an assumed
stochastic model. **Expected shortfall (ES)**, also called conditional VaR or CVaR, is the average loss conditional on
the loss exceeding the VaR threshold; the Basel Committee's revised market-risk framework uses expected-shortfall models
within its internal models approach. **Maximum drawdown** is the largest peak-to-trough decline in portfolio value
before a new peak is reached. **Beta** measures systematic (market) risk: the sensitivity of an asset's returns to
market returns.

## Why it matters for the B1-T1 toolkit

These are the standard diagnostics and risk warnings expected in a portfolio report. Each measure answers a different
question — a single threshold (VaR), the average of the tail (ES), the worst historical peak-to-trough loss (drawdown),
and sensitivity to the market (beta).

## Key facts and formulas

- VaR is a quantile of the loss distribution;

  $$
  \operatorname{ES} (\operatorname{CVaR}) = \mathbb{E}[\text{loss} \mid \text{loss} > \text{VaR}].
  $$

- Beta:

  $$
  \beta = \frac{\operatorname{cov} (\text{asset return}, \text{market return})}{\operatorname{Var} (\text{market return})},
  $$

  it is a component of the CAPM.
- Maximum drawdown:

  $$
  \text{Maximum drawdown} = \frac{\text{trough value} - \text{peak value}}{\text{peak value}}.
  $$

- VaR is *not subadditive* in general: portfolio VaR can exceed the sum of component VaRs, so VaR is not a coherent risk
  measure; expected shortfall is coherent.
- VaR is *tail-blind*: it says nothing about the size of losses beyond the threshold, and it depends on the chosen
  horizon, confidence level and model (model risk).

## Sources

- <https://www.bis.org/publ/bcbs24.htm> (accessed 2026-10-01)
- <https://www.bis.org/bcbs/publ/d457.htm> (accessed 2026-10-01)
- <https://www.bis.org/basel_framework/> (accessed 2026-10-01)
- <https://www.ecb.europa.eu/pub/financial-stability/fsr/html/index.en.html> (accessed 2026-10-01)
- <https://ocw.mit.edu/courses/15-401-finance-theory-i-fall-2008/> (accessed 2026-10-01)
- <https://doi.org/10.1111/1467-9965.00068> (accessed 2026-10-01) — Artzner, Delbaen, Eber & Heath (1999), "Coherent
  Measures of Risk", Mathematical Finance 9 (3), 203–228
- <https://www.investopedia.com/terms/m/maximum-drawdown-mdd.asp> (accessed 2026-10-01) — secondary reference
