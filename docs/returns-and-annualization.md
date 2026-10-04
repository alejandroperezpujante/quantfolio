# Financial Returns and Annualization

A return measures the change in the value of an investment over a holding period, expressed as a fraction of the initial
value. The **simple (arithmetic) return** over one period is the percentage price change, while the **log (continuously
compounded) return** is the natural logarithm of the price ratio. The two are related exactly
by $r_{\text{log}} = \ln (1 + r)$. Log returns are additive over time: the log return of a multi-period holding is the
sum of the single-period log returns, whereas simple returns combine multiplicatively through their growth factors. The
**total return** includes both price changes and income (dividends, coupons, interest), while the **price return**
includes only the change in price. The **arithmetic average return** is the simple mean of period returns; the
**geometric average return** compounds the growth factors and equals the compound annual growth rate (CAGR) when periods
are annual. The geometric mean is generally below the arithmetic mean, and the gap widens with return volatility.

## Why it matters for the B1-T1 toolkit

The B1-T1 toolkit works with price series, and returns are the standard transformation used to compare assets and feed
statistical measures. The choice between simple and log returns affects which aggregation and averaging properties hold.

## Key facts and formulas

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
- AM–GM inequality:

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
