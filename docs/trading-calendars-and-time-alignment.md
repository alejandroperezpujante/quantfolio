# Trading Calendars and Time Alignment

An exchange trading calendar defines the days and trading sessions on which a market operates. **Trading days** are the
days a market is open, which are a subset of **calendar days**; market holidays and half-days remove or shorten
sessions. A **business day**, in the financial-contracts sense, is a day on which commercial banks and foreign-exchange
markets settle payments and are open for general business (ISDA).

Each exchange also has session times expressed in a local time zone — for example, the NYSE core trading session runs
from 09:30 to 16:00 Eastern Time, and BME's open market runs from 09:00 to 17:30 CET. Because exchanges observe
different holidays and operate in different time zones, price series from different markets carry different timestamps
and different sets of dates. Combining them produces gaps and misaligned observations, so the series must be placed on a
common date/time axis (temporal alignment).

Dates may also require adjustment conventions. Where a nominal date would fall on a non-business day, business-day
conventions such as Following, Modified Following and Preceding move it to a different date. Timestamps are commonly
stored in UTC or in exchange local time. The IANA time-zone database is the reference for time-zone and daylight-saving
rules, and open-source exchange-calendar libraries (for example, `exchange_calendars`) encode per-exchange sessions,
holidays and half-days.

## Why it matters for the B1-T1 toolkit

Series drawn from several venues must be combined into one time axis. Exchange calendars explain why missing dates and
differing timestamps occur, and why simple date-based merging of unaligned series is insufficient.

## Key facts and formulas

- NYSE core trading session: 09:30–16:00 ET; certain dates close early at 13:00 ET (for example, the day after
  Thanksgiving and 24 December).
- BME 2026 non-trading days: 1 January, 3 April, 6 April, 1 May, 25 December; 24 and 31 December trade until 14:00 CET.
- ISDA business-day conventions: *Following* = first following business day; *Modified Following* = first following
  business day unless it falls in the next calendar month, in which case the first preceding business day; *Preceding* =
  first preceding business day.
- The IANA time-zone database maintains the world's time-zone and daylight-saving-time rules.
- Exchange-calendar libraries encode each exchange's holidays, sessions and half-days so that trading days can be
  enumerated.

## Sources

- <https://www.nyse.com/markets/hours-calendars> (accessed 2026-10-01)
- <https://www.bolsasymercados.es/en/bme-exchange/trading/trading-calendar.html> (accessed 2026-10-01)
- <https://www.isda.org/a/smMDE/Blackline-2000-v-2006-ISDA-Definitions.pdf> (accessed 2026-10-01)
- <https://www.iana.org/time-zones> (accessed 2026-10-01)
- <https://github.com/gerrymanoim/exchange_calendars> (accessed 2026-10-01)
