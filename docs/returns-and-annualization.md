# Financial returns and annualization

A return measures the change in an investment's value over a holding period as a fraction of its initial value. The
**simple return**, also called the arithmetic return, is the percentage price change. The **log return**, or
continuously compounded return, is the natural logarithm of the price ratio. The two are related exactly by
$r_{\text{log}} = \ln (1 + r)$.

Log returns add across time: the log return of a multi-period holding equals the sum of its single-period log
returns. Simple returns instead combine multiplicatively through their growth factors. **Total return** includes
price changes and income from dividends, coupons or interest. **Price return** includes only the price change.

The **arithmetic average return** is the simple mean of period returns. The **geometric average return** compounds
the growth factors and equals the compound annual growth rate (CAGR) when periods are annual. The geometric mean is
usually below the arithmetic mean, and the gap widens as return volatility rises.

## Use in Quantfolio

Compute simple returns for portfolio aggregation and log returns for time aggregation. State the annualization
convention, because 252 and 365 periods per year produce different annual figures.

## Facts and formulas

- Simple return:

  $$
  R_t = \frac{P_t - P_{t-1}}{P_{t-1}} = \frac{P_t}{P_{t-1}} - 1.
  $$

- Log return:

  $$
  r_t = \ln\left (\frac{P_t}{P_{t-1}}\right) = \ln (1 + R_t).
  $$

- Log returns aggregate additively:

  $$
  R_{\text{log},\text{total}} = \sum_t r_t,
  $$

  and simple returns aggregate multiplicatively:

  $$
  1 + R_{\text{total}} = \prod_i (1 + R_i).
  $$

- Total return vs price return: total return includes dividends and other income; price return excludes them.
- Arithmetic average:

  $$
  \bar{r} = \frac{1}{n} \sum_i r_i.
  $$

  Geometric average:

  $$
  \bar{r}_{\text{geo}} = \left (\prod_i (1 + r_i)\right)^{1/n} - 1,
  $$

  equal to CAGR for annual periods.
- AM-GM inequality:

  $$
  \bar{r}_{\text{geo}} \le \bar{r},
  $$

  with equality only when all period returns are equal.
- Annualization (compounding):

  $$
  r = (1 + R)^{1/t} - 1,
  $$

  where $t$ is the holding period in years.
- Annualized log return:

  $$
  r_{\text{log}} = \frac{R_{\text{log}}}{t}.
  $$

- Annualization convention: a year is commonly assumed to contain 252 trading days (12 months, 52 weeks); some
  references use 250 trading days.

## Sources

- <https://bookdown.org/compfinezbook/introFinRbook/Return-Calculations.html> (accessed 2026-10-01)
- <https://en.wikipedia.org/wiki/Rate_of_return> (accessed 2026-10-01)
