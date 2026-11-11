# Historical volatility

**Volatility** describes how widely a price series varies over time. In finance it is usually measured as the standard
deviation of returns, most often log returns. **Historical volatility**, also called realized or statistical
volatility, is calculated from a sample of past returns and therefore looks backward.

The **sample standard deviation** divides the sum of squared deviations from the mean by $n - 1$, the correction
proposed by Bessel. The **population standard deviation** divides by $N$. Under a random-walk assumption, volatility
scales with the square root of time. Periodic volatility can therefore be annualized by multiplying daily volatility
by $\sqrt{252}$ or monthly volatility by $\sqrt{12}$.

Volatility is not constant. It tends to arrive in **clusters** of high and low activity. **Unconditional
volatility** is the long-run average level; **conditional volatility** is the level at a particular time, and ARCH
or GARCH models describe it. **Implied volatility** comes from option prices and looks forward.
**Realized volatility** comes from observed returns and looks backward.

The Cboe Volatility Index (VIX) measures the market's expectation of 30-day volatility implied by S&P 500 index
options.

## Use in Quantfolio

Annualize the standard deviation of returns with the same period count as the return series. Use realized volatility
for historical estimates and implied volatility only when option prices are available.

## Facts and formulas

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
- Implied versus realized: implied volatility looks forward and comes from option prices. Realized volatility looks
  backward and comes from past returns.
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
