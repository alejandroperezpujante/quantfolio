# Modern portfolio theory (Markowitz, 1952)

Modern Portfolio Theory (MPT), or mean-variance analysis, is a framework for choosing a portfolio of financial assets
under uncertainty. Harry Markowitz introduced it in "Portfolio Selection" (1952) and expanded it in a 1959 book. He
received the 1990 Sveriges Riksbank Prize in Economic Sciences "for having developed the theory of portfolio choice."

In MPT, an asset is judged by how it contributes to the risk and return of the whole portfolio. A portfolio has two
dimensions: expected return and variance, the square of the standard deviation, which is the risk measure.
Because asset returns are correlated, adding more securities cannot remove all risk.

## Use in Quantfolio

Read weights as fractions of wealth and compute portfolio variance from the full covariance matrix. Treat the
efficient frontier as a theoretical reference: the toolkit evaluates the weights it receives and does not optimize
them. Check the stability of the estimated inputs before relying on the result.

## Facts and formulas

- Portfolio weights are the proportions of wealth in each asset and sum to one: $\sum_i w_i = 1$.
- Expected portfolio return is the weighted average of asset expected returns:

  $$
  \mathbb{E} (R_p) = \sum_i w_i \mathbb{E} (R_i).
  $$

- Risk is measured by portfolio variance (or its square root, the standard deviation); portfolio risk depends on
  individual variances and on the pairwise covariances of all assets.
- The correlation coefficient

  $$
  \rho_{ij} = \frac{\sigma_{ij}}{\sigma_i \sigma_j}
  $$

  lies between $-1$ and $+1$. Imperfect correlation ($\rho_{ij} < 1$) is what makes diversification reduce risk.
- The efficient frontier is the upper boundary of the feasible risk-return region: portfolios offering the lowest risk
  for a given expected return (equivalently, the highest expected return for a given risk).
- The minimum-variance portfolio is the vertex of the frontier and has the smallest attainable variance.
- MPT assumes risk-averse investors, a single period, and that mean and variance adequately summarize risk and return.
- Standard criticisms concern the reliance on estimated inputs and the instability of correlations over time.

## Sources

- <https://www.nobelprize.org/prizes/economic-sciences/1990/press-release/> (accessed 2026-10-01)
- <https://www.nobelprize.org/prizes/economic-sciences/1990/markowitz/lecture/> (accessed 2026-10-01)
- <https://ocw.mit.edu/courses/15-401-finance-theory-i-fall-2008/pages/video-lectures-and-slides/portfolio-theory/>
  (accessed 2026-10-01)
- <https://oyc.yale.edu/economics/econ-252-11/lecture-4> (accessed 2026-10-01)
- <https://en.wikipedia.org/wiki/Modern_portfolio_theory> (accessed 2026-10-01)
