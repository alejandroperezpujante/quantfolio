# Monte Carlo Simulation in Finance

**Monte Carlo simulation** is a broad class of computational methods that use repeated random sampling to obtain
numerical results. A typical procedure defines a domain of possible inputs, draws inputs randomly from a probability
distribution over that domain, performs a deterministic computation on each draw, and aggregates the results to
approximate a distribution, an integral, or an expected value. The method rests on the **law of large numbers**: as the
number of independent samples grows, the sample mean converges to the population expected value. In practice, randomness
is supplied by **pseudo-random number generators**, deterministic algorithms that produce sequences approximating
independent uniform variates. In finance, Monte Carlo methods are used for option pricing (especially path-dependent and
high-dimensional contracts), simulating future portfolio values, and estimating risk measures such as Value at Risk
(VaR), which is read as a quantile of the simulated profit-and-loss distribution. Results depend on the assumed
parameters and on the number of simulated paths and the time horizon; longer horizons compound the assumptions.

## Why it matters for the B1-T1 toolkit

Monte Carlo simulation is the standard way to translate volatility and return assumptions into a distribution of
possible future portfolio or price outcomes. The number of paths and the horizon are the two parameters that govern the
precision and scope of the resulting distribution.

## Key facts and formulas

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
