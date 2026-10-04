# Programmatic Market-Data Providers (Yahoo Finance/yfinance, Alpha Vantage, Finnhub, Polygon.io)

Programmatic market-data providers expose financial time series over HTTP (and often WebSocket) interfaces, so that
software can request prices and volumes instead of reading web pages.

**Yahoo Finance / yfinance.** Yahoo Finance is a consumer finance portal. `yfinance` is an unofficial, open-source
Python library that retrieves data from Yahoo Finance's publicly available APIs; it is not affiliated with, endorsed by,
or vetted by Yahoo, and is intended for research and educational purposes. Yahoo's terms describe the Finance API as
intended for personal use only and state that the data must not be redistributed. The library exposes historical OHLCV
(daily and intraday), splits and dividends, and other market and fundamental data.

**Alpha Vantage.** An API-key service offering free JSON endpoints, with a standard free allowance of 25 API requests
per day. It provides intraday, daily, weekly and monthly equity OHLCV, in both raw (as-traded) and
split/dividend-adjusted forms, plus index, options, fundamental, forex, crypto and technical-indicator data.

**Finnhub.** A REST and WebSocket API authenticated with an API key (`token`). Its free tier allows about 60 API calls
per minute, with a hard cap of 30 API calls per second across plans; the Stock Candles (OHLCV) endpoint is a premium
feature, while quotes, company profiles and fundamentals are available. Symbols use an `EXCHANGE:TICKER` format.

**Polygon.io.** Polygon.io renamed itself Massive.com on 30 October 2025; existing API keys and the `api.polygon.io`
base continue to work. It provides REST, WebSocket and downloadable flat-file data. Its aggregates endpoint returns
open, high, low, close and volume, with an `adjusted` flag that defaults to `true` and adjusts results for splits. A
free "Stocks Basic" plan exists alongside paid tiers, and it also covers indices, options, forex and crypto.

Common standardized price fields are: timestamp, open, high, low, close, adjusted close and volume. **Adjusted close**
differs from **close** because it is restated for corporate actions — stock splits and dividends — so that computed
returns are not distorted by mechanical price changes; `close` is the raw, as-traded last price.

## Why it matters for the B1-T1 toolkit

The toolkit is expected to ingest series from these providers and standardize them into one internal representation.
Providers differ in field names, adjustment conventions, symbol syntax and access limits, which is why a homogeneous
internal object is needed.

## Key facts and formulas

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
