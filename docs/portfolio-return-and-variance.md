# Portfolio Return and Variance

Portfolio-level return and risk are statistical quantities that combine the properties of the individual assets in a
portfolio. The expected return of a portfolio is the weighted average of the assets' expected returns, where the weights
are the fractions of wealth invested and sum to one. The risk of the portfolio, measured by the variance (or standard
deviation) of its return, is not the weighted average of the asset variances: it also depends on the covariances between
every pair of assets. These relationships are the algebraic content of mean-variance portfolio analysis.

## Why it matters for the B1-T1 toolkit

A multi-asset toolkit reports and summarises portfolio expected return and risk, and the covariance matrix is the object
that couples the individual assets. The formulas below state the standard definitions these quantities follow.

## Key facts and formulas

- A portfolio is defined by weights $w_i$ with $\sum_i w_i = 1$ (negative weights indicate short positions in the
  general case).
- Portfolio expected return:

  $$
  \mathbb{E} (R_p) = \sum_i w_i \mathbb{E} (R_i) = w^{T} \mu,
  $$

  where $\mu$ is the vector of asset expected returns.
- Portfolio variance:

  $$
  \sigma_p^2 = \sum_i \sum_j w_i w_j \sigma_{ij} = w^{T} \Sigma w,
  $$

  where $\sigma_{ij} = \operatorname{cov} (R_i, R_j)$ and $\Sigma$ is the covariance
  matrix; $\sigma_p = \sqrt{\sigma_p^2}$ is the standard deviation.
- The covariance matrix $\Sigma$ is $N \times N$ and symmetric, its diagonal entries are the variances
  ($\sigma_{ii} = \sigma_i^2$) and its off-diagonal entries are the covariances; it is positive semi-definite.
- Covariance and correlation are related by

  $$
  \sigma_{ij} = \rho_{ij} \sigma_i \sigma_j.
  $$

- Two-asset variance:

  $$
  \sigma_p^2 = w_1^2 \sigma_1^2 + w_2^2 \sigma_2^2 + 2 w_1 w_2 \sigma_{12} = w_1^2 \sigma_1^2 + w_2^2 \sigma_2^2 + 2 w_1 w_2 \rho_{12} \sigma_1 \sigma_2.
  $$

- Because the covariance terms can be negative and are generally smaller than the product of standard deviations,
  portfolio variance can be below the weighted average of asset variances.

## Sources

- <https://ocw.mit.edu/courses/15-401-finance-theory-i-fall-2008/pages/video-lectures-and-slides/portfolio-theory/>
  (accessed 2026-10-01)
- <https://oyc.yale.edu/economics/econ-252-11/lecture-4> (accessed 2026-10-01)
- <https://en.wikipedia.org/wiki/Modern_portfolio_theory> (accessed 2026-10-01)
- <https://en.wikipedia.org/wiki/Covariance_matrix> (accessed 2026-10-01)
- <https://www.itl.nist.gov/div898/handbook/pmc/section5/pmc542.htm> (accessed 2026-10-01)
