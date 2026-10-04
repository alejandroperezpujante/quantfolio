# Historical Volatility

In finance, **volatility** is the degree of variation of a price series over time, usually measured as the standard
deviation of returns (typically log returns). **Historical volatility** (also called realized or statistical volatility)
is computed from a sample of past returns; it is a backward-looking measure. The **sample standard deviation** divides
the sum of squared deviations from the mean by $n - 1$ (Bessel's correction), while the **population standard
deviation** divides by $N$. Because volatility scales with the square root of time under a random-walk assumption,
periodic volatility is converted to an annual figure using an annualization factor: $\sqrt{252}$ for daily data
and $\sqrt{12}$ for monthly data. Volatility is not constant: it appears in **clusters** of high and low activity, so a
distinction is drawn between **unconditional volatility** (a long-run average level) and **conditional volatility** (the
level prevailing at a given time), which ARCH/GARCH models describe. **Implied volatility** is derived from option
prices and looks forward; **realized volatility** is computed from observed returns and looks backward. The Cboe
Volatility Index (VIX) is a widely followed measure of the market's expectation of near-term (30-day) volatility implied
by S&P 500 index options.

## Why it matters for the B1-T1 toolkit

Volatility is the standard summary of dispersion used to characterize a price series and to calibrate assumptions about
risk. Realized and implied volatility are the two reference quantities when a rate of fluctuation is needed as a model
input.

## Key facts and formulas

- Historical volatility is the (usually annualized) standard deviation of returns.
- Sample variance:

  $$
  s^2 = \frac{1}{n-1} \sum_i (r_i - \bar{r})^2,
  $$

  population variance:

  $$
  \sigma^2 = \frac{1}{N} \sum_i (r_i - \mu)^2.
  $$

- Annualization:

  $$
  \sigma_{\text{annual}} = \sigma_{\text{daily}} \times \sqrt{252}, \qquad \sigma_{\text{annual}} = \sigma_{\text{monthly}} \times \sqrt{12}.
  $$

- Root-time scaling:

  $$
  \sigma_T = \sigma_{\text{annual}} \times \sqrt{T},
  $$

  for horizon $T$ in years.
- Realized volatility is the square root of realized variance (sum of squared returns divided by the number of
  observations).
- Implied vs realized: implied volatility is forward-looking and extracted from option prices; realized volatility is
  backward-looking and computed from past returns.
- VIX is a measure of 30-day expected volatility conveyed by S&P 500 Index option prices.
- The compound annual growth rate is approximately

  $$
  \text{CAGR} \approx \text{arithmetic return} - \tfrac{1}{2}\sigma^2,
  $$

  so volatility acts as a drag on compounded growth.

## Sources

- <https://www.cboe.com/en/tradable-products/vix> (accessed 2026-10-01)
- <https://www.federalreserve.gov/econres/notes/ifdp-notes/understanding-global-volatility-20180119.htm> (accessed
  2026-10-01)
- <https://bookdown.org/compfinezbook/introFinRbook/Descriptive-Statistics-for-Financial-Data.html> (accessed
  2026-10-01)
- <https://en.wikipedia.org/wiki/Volatility_(finance)> (accessed 2026-10-01)
