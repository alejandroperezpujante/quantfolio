# Geometric Brownian Motion

**Geometric Brownian motion (GBM)**, also called exponential Brownian motion, is a continuous-time stochastic process in
which the logarithm of a randomly varying quantity (such as a stock price) follows a Brownian motion with drift. It is
the standard process used to model stock prices in the Black–Scholes framework. GBM is defined by the stochastic
differential equation $dS_t = \mu S_t \, dt + \sigma S_t \, dW_t$, where $W_t$ is a Wiener process (Brownian
motion), $\mu$ is the percentage drift, and $\sigma$ is the percentage volatility; both $\mu$ and $\sigma$ are constants
in the model. The parameters have distinct roles: $\mu$ models the deterministic trend, while $\sigma$ models the
unpredictable fluctuations. Because the log of the price is normally distributed, the price $S_t$ is log-normally
distributed and remains strictly positive. The model is analytically tractable but relies on simplifying assumptions
that are known to differ from observed markets.

## Why it matters for the B1-T1 toolkit

GBM is the canonical price-process model that links a drift and a volatility assumption to a distribution of future
prices. It is the reference model against which simulated price paths and their sensitivity to drift and volatility
assumptions are described.

## Key facts and formulas

- Stochastic differential equation:

  $$
  dS_t = \mu S_t \, dt + \sigma S_t \, dW_t.
  $$

- Closed-form solution:

  $$
  S_t = S_0 \exp\left (\left (\mu - \frac{\sigma^2}{2}\right)t + \sigma W_t\right).
  $$

- The exponent $\left (\mu - \frac{\sigma^2}{2}\right)t + \sigma W_t$ is normally distributed, so $S_t$ is log-normally
  distributed.
- Expected value:

  $$
  \mathbb{E}[S_t] = S_0 e^{\mu t}.
  $$

- Variance:

  $$
  \operatorname{Var} (S_t) = S_0^2 e^{2\mu t}\left (e^{\sigma^2 t} - 1\right).
  $$

- Expected log price:

  $$
  \mathbb{E}[\ln S_t] = \ln S_0 + \left (\mu - \frac{\sigma^2}{2}\right)t.
  $$

- The process assumes constant drift and constant volatility, continuous paths, and no jumps.
- Known limitations: real volatility changes over time (stochastic volatility) and prices can jump; the lognormal
  distribution understates the frequency of extreme moves (fat tails).
- Extensions relaxing these assumptions include local volatility, stochastic volatility (e.g. Heston), and
  jump-diffusion models.

## Sources

- <https://ocw.mit.edu/courses/18-642-topics-in-mathematics-with-applications-in-finance-fall-2024/pages/week-14>
  (accessed 2026-10-01)
- <https://en.wikipedia.org/wiki/Geometric_Brownian_motion> (accessed 2026-10-01)
