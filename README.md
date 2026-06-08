# clan-wars-payouts

WoT clan wars attendance and weekly gold/bonds payout tracker.

## Setup

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```sh
make install
```

Create a `.env` file in the project root:

```sh
WG_APPLICATION_ID=your_wargaming_application_id
SECRET_KEY=a_random_string_for_signing_session_cookies
BASE_URL=http://localhost:8000
# optional
BRAND_NAME=clantools.fyi
DATABASE_URL=sqlite:///clan_wars.db
```

`WG_APPLICATION_ID` comes from <https://developers.wargaming.net/applications/>.
`DATABASE_URL` defaults to a local SQLite file; Postgres URLs (`postgres://`,
`postgresql://`) are also supported.

## Run

```sh
make dev    # local development with auto-reload
make prod   # production-style server, honors $PORT
```

The app serves at <http://localhost:8000>.
