# Monte Carlo simulation in finance

**Monte Carlo simulation** uses repeated random sampling to produce numerical results. A typical run defines a domain
of inputs, draws inputs from a probability distribution over that domain and computes a deterministic result for each
draw. Aggregating the results approximates a distribution, an integral or an expected value.

The method relies on the **law of large numbers**: as the number of independent samples grows, the sample mean
converges to the population expected value. Software supplies the random inputs through **pseudo-random number
generators**, deterministic algorithms whose sequences approximate independent uniform draws.

In finance, Monte Carlo methods support option pricing, especially for path-dependent or high-dimensional contracts.
They also simulate future portfolio values and estimate risk measures such as Value at Risk (VaR), a quantile of the
simulated profit-and-loss distribution. Results depend on the assumed parameters, the number of paths and the time
horizon. A longer horizon gives the assumptions more time to compound.

## Why it matters for the B1-T1 toolkit

Monte Carlo simulation turns return and volatility assumptions into a distribution of possible future prices or
portfolio values. The number of paths controls the precision of that distribution, and the horizon controls its
scope.

## Facts and formulas

- Monte Carlo error (standard error of the sample mean):

  $$
  \operatorname{SE} = \frac{\sigma}{\sqrt{N}},
  $$

  so accuracy improves like $1/\sqrt{N}$: halving the error requires roughly four times the number of simulations.
- Required sample size for a target precision $\epsilon$ at confidence level $z$:

  $$
  n \ge \frac{s^2 z^2}{\epsilon^2}.
  $$

- Common uses: option pricing, portfolio value simulation, and risk/VaR estimation.
- VaR at confidence level $\alpha$ is a quantile of the simulated loss (or return) distribution.
- Estimation accuracy improves with more paths $N$; the horizon $t$ determines the length of the simulated paths and the
  degree to which assumptions compound.
- Pseudo-random generators approximate independent uniform draws; they are deterministic sequences rather than true
  randomness.

## Sources

- <https://ocw.mit.edu/courses/6-0002-introduction-to-computational-thinking-and-data-science-fall-2016/resources/lecture-6-monte-carlo-simulation>
  (accessed 2026-10-01)
- <https://www.elibrary.imf.org/display/book/9781484368589/ch009.xml> (accessed 2026-10-01)
- <https://en.wikipedia.org/wiki/Monte_Carlo_method> (accessed 2026-10-01)
