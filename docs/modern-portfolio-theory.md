# Modern Portfolio Theory (Markowitz, 1952)

Modern Portfolio Theory (MPT), also called mean-variance analysis, is a framework for choosing portfolios of financial
assets under uncertainty. Harry Markowitz introduced it in the essay "Portfolio Selection" (1952) and developed it
further in his 1959 book; he received the 1990 Sveriges Riksbank Prize in Economic Sciences "for having developed the
theory of portfolio choice." The central idea is that an asset should be judged by how it contributes to the risk and
return of the whole portfolio, not in isolation. Under the model, a portfolio is described by two dimensions: its
expected return and its variance (the square of the standard deviation), used as the measure of risk. Because returns on
different assets are correlated, risk cannot be eliminated entirely, no matter how many securities are held.

## Why it matters for the B1-T1 toolkit

The B1-T1 toolkit works with multiple assets, portfolio weights and risk statistics, all of which use the mean-variance
vocabulary Markowitz established. The theory defines what concepts such as expected return, variance, covariance and
diversification mean in a portfolio context.

## Key facts and formulas

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
- The efficient frontier is the upper boundary of the feasible risk–return region: portfolios offering the lowest risk
  for a given expected return (equivalently, the highest expected return for a given risk).
- The minimum-variance portfolio is the vertex of the frontier and has the smallest attainable variance.
- MPT assumes risk-averse investors, a single period, and that risk and return are adequately summarised by mean and
  variance; reliance on estimated inputs and changing correlations are standard criticisms.

## Sources

- <https://www.nobelprize.org/prizes/economic-sciences/1990/press-release/> (accessed 2026-10-01)
- <https://www.nobelprize.org/prizes/economic-sciences/1990/markowitz/lecture/> (accessed 2026-10-01)
- <https://ocw.mit.edu/courses/15-401-finance-theory-i-fall-2008/pages/video-lectures-and-slides/portfolio-theory/>
  (accessed 2026-10-01)
- <https://oyc.yale.edu/economics/econ-252-11/lecture-4> (accessed 2026-10-01)
- <https://en.wikipedia.org/wiki/Modern_portfolio_theory> (accessed 2026-10-01)
