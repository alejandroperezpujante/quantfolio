# Trading calendars and time alignment

An exchange trading calendar defines the days and sessions on which a market operates. **Trading days** are the days
the market is open and form a subset of **calendar days**. Holidays and half-days remove or shorten sessions. In
financial contracts, a **business day** is a day when commercial banks and foreign-exchange markets settle payments
and are open for general business (ISDA).

Exchanges publish session times in their local time zone. The NYSE core session, for example, runs from 09:30 to
16:00 Eastern Time, while BME's open market runs from 09:00 to 17:30 CET. Different holidays and time zones give
price series different timestamps and different sets of dates. When the series are combined, those differences create
gaps and misaligned observations. Temporal alignment places them on a common date or time axis.

Dates sometimes need a business-day convention. If a nominal date falls on a non-business day, Following, Modified
Following or Preceding moves it to another date. Timestamps are usually stored in UTC or in exchange local time. The
IANA time-zone database supplies the rules for time zones and daylight saving. Open-source libraries such as
`exchange_calendars` encode each exchange's sessions, holidays and half-days.

## Why it matters for the B1-T1 toolkit

The toolkit combines series from several venues on one time axis. Exchange calendars explain why dates are missing and
why timestamps differ. They also show why a simple merge on date is not enough when the source series are unaligned.

## Facts and formulas

- NYSE core trading session: 09:30 to 16:00 ET; certain dates close early at 13:00 ET (for example, the day after
  Thanksgiving and 24 December).
- BME 2026 non-trading days: 1 January, 3 April, 6 April, 1 May, 25 December; 24 and 31 December trade until 14:00 CET.
- ISDA business-day conventions: *Following* means the first following business day. *Modified Following* means the
  first following business day unless it falls in the next calendar month, in which case it means the first preceding
  business day. *Preceding* means the first preceding business day.
- The IANA time-zone database maintains the world's time-zone and daylight-saving-time rules.
- Exchange-calendar libraries encode each exchange's holidays, sessions and half-days so that trading days can be
  enumerated.

## Sources

- <https://www.nyse.com/markets/hours-calendars> (accessed 2026-10-01)
- <https://www.bolsasymercados.es/en/bme-exchange/trading/trading-calendar.html> (accessed 2026-10-01)
- <https://www.isda.org/a/smMDE/Blackline-2000-v-2006-ISDA-Definitions.pdf> (accessed 2026-10-01)
- <https://www.iana.org/time-zones> (accessed 2026-10-01)
- <https://github.com/gerrymanoim/exchange_calendars> (accessed 2026-10-01)
