# Market-data APIs: Yahoo Finance, Alpha Vantage, Finnhub and Polygon.io

Most market-data providers expose financial time series through HTTP APIs, and some also offer WebSocket streams.
Software can request prices and volumes directly instead of reading them from a web page.

**Yahoo Finance and yfinance.** Yahoo Finance is a consumer finance portal. `yfinance` is an unofficial open-source
Python library that retrieves data from Yahoo Finance's public APIs. It is not affiliated with, endorsed by or vetted
by Yahoo and is intended for research and education. Yahoo's terms describe the Finance API as a personal-use service
and prohibit redistribution of its data. The library provides historical OHLCV data (daily and intraday), splits,
dividends and other market and fundamental data.

**Alpha Vantage.** This API-key service offers JSON endpoints, with a standard free allowance of 25 requests per day.
It provides intraday, daily, weekly and monthly equity OHLCV in raw and split- or dividend-adjusted forms, as well as
index, options, fundamental, forex, crypto and technical-indicator data.

**Finnhub.** Finnhub exposes REST and WebSocket APIs that authenticate with an API key in a `token` parameter. The
free tier allows about 60 calls per minute, and every plan has a hard cap of 30 calls per second. Stock Candles
(OHLCV) is a premium endpoint; quotes, company profiles and fundamentals are available. Symbols use the
`EXCHANGE:TICKER` format.

**Polygon.io / Massive.** Polygon.io renamed itself Massive.com on 30 October 2025. Existing API keys and the
`api.polygon.io` base still work. The service offers REST, WebSocket and downloadable flat-file data. Its aggregates
endpoint returns open, high, low, close and volume, with an `adjusted` flag that defaults to `true` and adjusts for
splits. A free "Stocks Basic" plan is available alongside paid tiers. The service also covers indices, options,
forex and crypto.

The common standardized fields are timestamp, open, high, low, close, adjusted close and volume. **Adjusted close**
restates the price for stock splits and dividends, so corporate actions do not distort calculated returns. **Close**
is the raw, as-traded last price.

## Why it matters for the B1-T1 toolkit

The toolkit converts the market data it consumes into one internal representation. Field names, adjustment
conventions, symbol syntax and access limits differ between providers, so a common object keeps the analysis layer
independent of any one API.

## Facts and formulas

- OHLCV: open = first price of the period; high = highest price; low = lowest price; close = last price; volume = number
  of shares traded.
- Adjusted close is adjusted for splits and dividends; close is the unadjusted, as-traded price.
- Alpha Vantage standard free limit: 25 API requests per day.
- Finnhub free tier: about 60 API calls per minute; 30 API calls per second hard cap; OHLCV candles are premium.
- Massive/Polygon `adjusted` parameter defaults to `true` and adjusts for splits; an API key is required.
- yfinance is unaffiliated with Yahoo and intended for personal/research use; Yahoo prohibits redistribution.

## Sources

- <https://pypi.org/project/yfinance/> (accessed 2026-10-01)
- <https://ranaroussi.github.io/yfinance/> (accessed 2026-10-01)
- <https://help.yahoo.com/kb/finance-for-web/SLN2310.html> (accessed 2026-10-01)
- <https://www.alphavantage.co/documentation/> (accessed 2026-10-01)
- <https://www.alphavantage.co/premium/> (accessed 2026-10-01)
- <https://finnhub.io/docs/api> (accessed 2026-10-01)
- <https://finnhub.io/pricing> (accessed 2026-10-01)
- <https://massive.com/docs> (accessed 2026-10-01)
- <https://massive.com/blog/polygon-is-now-massive/> (accessed 2026-10-01)
