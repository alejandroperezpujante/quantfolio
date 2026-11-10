# Portfolio risk measures used in reports

Portfolio risk measures summarize the potential for loss. **Value at Risk (VaR)** is the loss that is not expected to
be exceeded over a given horizon at a given confidence level. Analysts choose its two parameters, the **confidence
level** (for example, 95% or 99%) and the **horizon** (for example, one day or ten days); VaR itself does not fix
them.

There are three common estimation methods. **Historical simulation** applies the observed distribution of returns
without assuming a parametric form. The **parametric variance-covariance approach** usually assumes normally
distributed returns and linear exposures, then uses a mean vector and covariance matrix. **Monte Carlo simulation**
generates scenarios from an assumed stochastic model.

**Expected shortfall (ES)**, also called conditional VaR or CVaR, is the average loss when the loss exceeds the VaR
threshold. The Basel Committee's revised market-risk framework uses expected-shortfall models within its internal
models approach. **Maximum drawdown** is the largest peak-to-trough decline before the portfolio reaches a new peak.
**Beta** measures systematic, or market, risk: the sensitivity of an asset's returns to market returns.

## Why it matters for the B1-T1 toolkit

These diagnostics answer different questions. VaR gives a loss threshold, ES gives the average tail loss, maximum
drawdown gives the worst historical peak-to-trough loss, and beta gives sensitivity to the market.

## Facts and formulas

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
- <https://doi.org/10.1111/1467-9965.00068> (accessed 2026-10-01). Artzner, Delbaen, Eber & Heath (1999), "Coherent
  Measures of Risk", Mathematical Finance 9 (3), 203–228.
- <https://www.investopedia.com/terms/m/maximum-drawdown-mdd.asp> (accessed 2026-10-01; secondary reference)
