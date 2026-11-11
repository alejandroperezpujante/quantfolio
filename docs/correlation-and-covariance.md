# Correlation and covariance

Covariance and correlation measure how two variables move together. For random variables $X$ and $Y$ with means
$\mu_X$ and $\mu_Y$, covariance is the expected product of their deviations from those means:
$\operatorname{cov} (X, Y) = \mathbb{E}[(X - \mu_X)(Y - \mu_Y)]$. Its sign gives the direction of the linear
relationship. It is positive when the variables tend to be above or below their means together. Its magnitude depends
on the units and scale of the variables.

The Pearson correlation coefficient divides covariance by the product of the two standard deviations. The result has
no units and lies between $-1$ and $+1$.

## Use in Quantfolio

Use the covariance matrix to measure how returns move together. Treat correlation as a linear measure and re-estimate
it over the window that matches the analysis, because correlations change over time.

## Facts and formulas

- Covariance:

  $$
  \sigma_{XY} = \operatorname{cov} (X, Y) = \mathbb{E}[(X - \mu_X)(Y - \mu_Y)] = \mathbb{E}[XY] - \mathbb{E}[X]\mathbb{E}[Y].
  $$

- Sample covariance:

  $$
  \frac{1}{n-1} \sum_i (x_i - \bar{x})(y_i - \bar{y}).
  $$

- Pearson correlation:

  $$
  \rho_{XY} = \frac{\operatorname{cov} (X, Y)}{\sigma_X \sigma_Y}, \qquad \rho_{XY} \in [-1, +1].
  $$

- A covariance matrix is symmetric and positive semi-definite; its diagonal holds variances and its off-diagonal entries
  hold covariances. A correlation matrix has ones on the diagonal and off-diagonal entries in $[-1, +1]$.
- $\rho = +1$ means perfect positive linear association (no diversification benefit from combining the two
  assets); $\rho < 1$ allows portfolio risk reduction; $\rho = -1$ means perfect negative linear association.
- The correlation coefficient captures only linear association; a strong nonlinear relationship can have a correlation
  near zero.
- Correlation does not imply causation, and correlation estimates from historical returns are not necessarily stable
  over time (correlations can change, and generally tend to rise during market stress).

## Sources

- <https://www.stat.berkeley.edu/~stark/SticiGui/Text/correlation.htm> (accessed 2026-10-01)
- <https://www.itl.nist.gov/div898/handbook/pmc/section5/pmc542.htm> (accessed 2026-10-01)
- <https://www.itl.nist.gov/div898/handbook/eda/section3/eda35c.htm> (accessed 2026-10-01)
- <https://en.wikipedia.org/wiki/Pearson_correlation_coefficient> (accessed 2026-10-01)
- <https://en.wikipedia.org/wiki/Covariance_matrix> (accessed 2026-10-01)
- <https://openstax.org/books/introductory-statistics/pages/12-introduction> (accessed 2026-10-01)
