from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse

LEAGUES: Dict[str, Dict[str, str]] = {
    "NFL": {
        "id": "4391",
        "name": "National Football League",
        "sport": "American Football",
    },
    "NBA": {
        "id": "4387",
        "name": "National Basketball Association",
        "sport": "Basketball",
    },
    "MLB": {
        "id": "4424",
        "name": "Major League Baseball",
        "sport": "Baseball",
    },
    "NHL": {
        "id": "4380",
        "name": "National Hockey League",
        "sport": "Ice Hockey",
    },
}

DEFAULT_API_KEY = "123"
BASE_ELO = 1500.0
K_FACTOR = 20.0
CACHE_TTL_SECONDS = int(os.getenv("SPORTSDB_CACHE_TTL_SECONDS", "300"))
LOOKAHEAD_DAYS = int(os.getenv("SPORTSDB_LOOKAHEAD_DAYS", "10"))
HOME_ADVANTAGE = float(os.getenv("SPORTSDB_HOME_ADVANTAGE", "60"))
MAX_TEAM_LOOKUPS = int(os.getenv("SPORTSDB_TEAM_LOOKUPS", "12"))

FINISHED_STATUSES = {
    "FT",
    "FULL TIME",
    "FINAL",
    "AET",
    "PEN",
    "CANCELLED",
    "CANCELED",
    "ABANDONED",
    "SUSPENDED",
    "AWARDED",
    "POSTPONED",
}
UPCOMING_STATUSES = {
    "NS",
    "NOT STARTED",
    "SCHEDULED",
    "TBD",
    "TIME TBD",
}

INDEX_HTML = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Sports Outcome Predictions</title>
    <style>
      :root {
        color-scheme: light dark;
      }
      body {
        font-family: Arial, sans-serif;
        margin: 0;
        padding: 0;
        background: #0f172a;
        color: #e2e8f0;
      }
      main {
        max-width: 960px;
        margin: 0 auto;
        padding: 32px 20px 48px;
      }
      header {
        margin-bottom: 24px;
      }
      h1 {
        margin: 0 0 8px;
        font-size: 28px;
      }
      p {
        margin: 0 0 12px;
        color: #cbd5f5;
      }
      .card {
        background: #1e293b;
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 16px;
        box-shadow: 0 10px 18px rgba(15, 23, 42, 0.2);
      }
      label {
        display: block;
        font-weight: 600;
        margin-bottom: 8px;
      }
      select,
      input,
      button {
        font-size: 16px;
        padding: 10px 12px;
        border-radius: 8px;
        border: 1px solid #334155;
        background: #0f172a;
        color: inherit;
      }
      button {
        background: #38bdf8;
        color: #0f172a;
        font-weight: 700;
        cursor: pointer;
      }
      button:disabled {
        opacity: 0.6;
        cursor: not-allowed;
      }
      .grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        gap: 16px;
      }
      .results {
        margin-top: 24px;
      }
      .prediction {
        border-left: 3px solid #38bdf8;
        padding-left: 12px;
      }
      .error {
        color: #fecaca;
        background: #7f1d1d;
        border-radius: 8px;
        padding: 10px 12px;
        margin-top: 12px;
      }
      .muted {
        color: #94a3b8;
        font-size: 14px;
      }
    </style>
  </head>
  <body>
    <main>
      <header>
        <h1>Sports Outcome Predictions</h1>
        <p>
          Educational predictions for NFL, NBA, MLB, and NHL using a simple Elo
          model and TheSportsDB data.
        </p>
        <p class="muted">
          Not intended for gambling or wagering decisions.
        </p>
      </header>

      <section class="card">
        <form id="predict-form">
          <div class="grid">
            <div>
              <label for="league">League</label>
              <select id="league" name="league" required>
                <option value="NFL">NFL</option>
                <option value="NBA" selected>NBA</option>
                <option value="MLB">MLB</option>
                <option value="NHL">NHL</option>
              </select>
            </div>
            <div>
              <label for="limit">Number of games</label>
              <input id="limit" name="limit" type="number" value="5" min="1" max="20" />
            </div>
            <div>
              <label>&nbsp;</label>
              <button type="submit" id="submit">Get predictions</button>
            </div>
          </div>
        </form>
        <div id="error" class="error" style="display: none;"></div>
      </section>

      <section class="results" id="results"></section>
    </main>

    <script>
      const form = document.getElementById("predict-form");
      const resultsEl = document.getElementById("results");
      const errorEl = document.getElementById("error");
      const submitBtn = document.getElementById("submit");

      const renderPredictions = (payload) => {
        resultsEl.innerHTML = "";
        const predictions = payload.predictions || [];
        if (predictions.length === 0) {
          resultsEl.innerHTML = "<p class=\\"muted\\">No predictions found.</p>";
          return;
        }
        const summary = document.createElement("p");
        summary.className = "muted";
        const requested = payload.requested || predictions.length;
        summary.textContent = `Showing ${predictions.length} of ${requested} requested games.`;
        resultsEl.appendChild(summary);
        if (payload.note) {
          const note = document.createElement("p");
          note.className = "muted";
          note.textContent = payload.note;
          resultsEl.appendChild(note);
        }
        const container = document.createElement("div");
        container.className = "grid";
        predictions.forEach((item) => {
          const card = document.createElement("div");
          card.className = "card prediction";
          card.innerHTML = `
            <h3>${item.event || "Matchup"}</h3>
            <p class="muted">${item.start_time || "Start time TBD"}</p>
            <p><strong>Home:</strong> ${item.home_team}</p>
            <p><strong>Away:</strong> ${item.away_team}</p>
            <p><strong>Predicted winner:</strong> ${item.predicted_winner}</p>
            <p><strong>Home win prob:</strong> ${item.home_win_prob}</p>
            <p><strong>Away win prob:</strong> ${item.away_win_prob}</p>
          `;
          container.appendChild(card);
        });
        resultsEl.appendChild(container);
      };

      const showError = (message) => {
        errorEl.style.display = "block";
        errorEl.textContent = message;
      };

      const clearError = () => {
        errorEl.style.display = "none";
        errorEl.textContent = "";
      };

      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        clearError();
        submitBtn.disabled = true;
        resultsEl.innerHTML = "<p class=\\"muted\\">Loading...</p>";

        const league = document.getElementById("league").value;
        const limit = document.getElementById("limit").value || 5;
        const url = `/predict?league=${encodeURIComponent(league)}&limit=${encodeURIComponent(limit)}`;

        try {
          const response = await fetch(url);
          const data = await response.json();
          if (!response.ok) {
            throw new Error(data.detail || "Request failed");
          }
          renderPredictions(data);
        } catch (err) {
          resultsEl.innerHTML = "";
          showError(err.message || "Unable to load predictions.");
        } finally {
          submitBtn.disabled = false;
        }
      });
    </script>
  </body>
</html>
"""


@dataclass
class CacheEntry:
    timestamp: float
    payload: Dict[str, Any]


class SportsDBClient:
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self.base_url = f"https://www.thesportsdb.com/api/v1/json/{api_key}"
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(10.0))
        self._cache: Dict[str, CacheEntry] = {}

    def _cache_key(self, endpoint: str, params: Dict[str, Any]) -> str:
        parts = [f"{key}={params[key]}" for key in sorted(params)]
        return f"{endpoint}?{'&'.join(parts)}"

    def _get_cached(self, key: str) -> Optional[Dict[str, Any]]:
        entry = self._cache.get(key)
        if not entry:
            return None
        if time.time() - entry.timestamp > CACHE_TTL_SECONDS:
            self._cache.pop(key, None)
            return None
        return entry.payload

    async def fetch_json(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        key = self._cache_key(endpoint, params)
        cached = self._get_cached(key)
        if cached is not None:
            return cached
        url = f"{self.base_url}/{endpoint}"
        response = await self._client.get(url, params=params)
        response.raise_for_status()
        payload = response.json()
        self._cache[key] = CacheEntry(timestamp=time.time(), payload=payload)
        return payload

    async def get_past_events(self, league_id: str) -> List[Dict[str, Any]]:
        data = await self.fetch_json("eventspastleague.php", {"id": league_id})
        return data.get("events") or []

    async def get_next_events(self, league_id: str) -> List[Dict[str, Any]]:
        data = await self.fetch_json("eventsnextleague.php", {"id": league_id})
        return data.get("events") or []

    async def get_team_last_events(self, team_id: str) -> List[Dict[str, Any]]:
        data = await self.fetch_json("eventslast.php", {"id": team_id})
        return data.get("results") or data.get("events") or []

    async def get_events_by_day(
        self, date_str: str, league: str, sport: str
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"d": date_str, "l": league, "s": sport}
        data = await self.fetch_json("eventsday.php", params)
        return data.get("events") or []

    async def close(self) -> None:
        await self._client.aclose()


def parse_score(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_event_datetime(event: Dict[str, Any]) -> Optional[datetime]:
    date_str = event.get("dateEvent")
    if not date_str:
        return None
    time_str = event.get("strTime") or ""
    candidate = date_str
    if time_str:
        candidate = f"{date_str}T{time_str}"
    candidate = candidate.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(candidate)
    except ValueError:
        try:
            return datetime.fromisoformat(date_str)
        except ValueError:
            return None


def format_event_datetime(event: Dict[str, Any]) -> Optional[str]:
    dt = parse_event_datetime(event)
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def normalize_status(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().upper()


def is_upcoming_event(event: Dict[str, Any], now: datetime) -> bool:
    status = normalize_status(event.get("strStatus"))
    home_score = parse_score(event.get("intHomeScore"))
    away_score = parse_score(event.get("intAwayScore"))

    if status in FINISHED_STATUSES:
        return False

    if (home_score is not None or away_score is not None) and status not in UPCOMING_STATUSES:
        return False

    event_dt = parse_event_datetime(event)
    if event_dt:
        if event_dt.tzinfo is None:
            event_dt = event_dt.replace(tzinfo=timezone.utc)
        if event_dt < now:
            return False

    return True


def upcoming_sort_key(event: Dict[str, Any]) -> datetime:
    dt = parse_event_datetime(event)
    if dt is None:
        return datetime.max.replace(tzinfo=timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def expected_score(rating_a: float, rating_b: float) -> float:
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400.0))


def update_elo_ratings(
    ratings: Dict[str, float], events: List[Dict[str, Any]]
) -> None:
    def sort_key(event: Dict[str, Any]) -> datetime:
        return parse_event_datetime(event) or datetime.min

    for event in sorted(events, key=sort_key):
        home = event.get("strHomeTeam")
        away = event.get("strAwayTeam")
        if not home or not away:
            continue
        home_score = parse_score(event.get("intHomeScore"))
        away_score = parse_score(event.get("intAwayScore"))
        if home_score is None or away_score is None:
            continue
        ratings.setdefault(home, BASE_ELO)
        ratings.setdefault(away, BASE_ELO)
        if home_score > away_score:
            outcome = 1.0
        elif home_score < away_score:
            outcome = 0.0
        else:
            outcome = 0.5
        expected_home = expected_score(ratings[home], ratings[away])
        expected_away = 1.0 - expected_home
        ratings[home] += K_FACTOR * (outcome - expected_home)
        ratings[away] += K_FACTOR * ((1.0 - outcome) - expected_away)


def compute_elo_ratings(events: List[Dict[str, Any]]) -> Dict[str, float]:
    ratings: Dict[str, float] = {}
    update_elo_ratings(ratings, events)
    return ratings


def build_prediction(
    event: Dict[str, Any], ratings: Dict[str, float]
) -> Optional[Dict[str, Any]]:
    home = event.get("strHomeTeam")
    away = event.get("strAwayTeam")
    if not home or not away:
        return None
    home_rating = ratings.get(home, BASE_ELO)
    away_rating = ratings.get(away, BASE_ELO)
    home_prob = expected_score(home_rating + HOME_ADVANTAGE, away_rating)
    away_prob = 1.0 - home_prob
    predicted = home if home_prob >= 0.5 else away
    return {
        "event_id": event.get("idEvent"),
        "event": event.get("strEvent"),
        "start_time": format_event_datetime(event),
        "home_team": home,
        "away_team": away,
        "home_win_prob": round(home_prob, 3),
        "away_win_prob": round(away_prob, 3),
        "predicted_winner": predicted,
    }


app = FastAPI(
    title="Sports Outcome Prediction API",
    description="Educational sports prediction API using public data.",
    version="0.1.0",
)

_client: Optional[SportsDBClient] = None


@app.on_event("startup")
async def startup() -> None:
    global _client
    api_key = os.getenv("SPORTSDB_API_KEY", DEFAULT_API_KEY)
    _client = SportsDBClient(api_key=api_key)


@app.on_event("shutdown")
async def shutdown() -> None:
    if _client:
        await _client.close()


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}

@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return INDEX_HTML


@app.get("/leagues")
async def leagues() -> Dict[str, Any]:
    return {"leagues": LEAGUES}


@app.get("/predict")
async def predict(
    league: str = Query(..., description="NFL, NBA, MLB, or NHL"),
    limit: int = Query(5, ge=1, le=20),
) -> Dict[str, Any]:
    league_key = league.strip().upper()
    if league_key not in LEAGUES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported league '{league}'. Use one of: {', '.join(LEAGUES)}",
        )
    if _client is None:
        raise HTTPException(status_code=500, detail="Data client unavailable")

    league_id = LEAGUES[league_key]["id"]
    league_sport = LEAGUES[league_key]["sport"]
    try:
        past_events = await _client.get_past_events(league_id)
        upcoming_events = await _client.get_next_events(league_id)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail="Data provider request failed"
        ) from exc

    now = datetime.now(timezone.utc)
    filtered_upcoming = [e for e in upcoming_events if is_upcoming_event(e, now)]

    if len(filtered_upcoming) < limit:
        existing_ids = {e.get("idEvent") for e in filtered_upcoming if e.get("idEvent")}
        extra_events: List[Dict[str, Any]] = []
        for offset in range(LOOKAHEAD_DAYS):
            date_str = (now + timedelta(days=offset)).date().isoformat()
            try:
                day_events = await _client.get_events_by_day(
                    date_str, league_key, league_sport
                )
            except httpx.HTTPError:
                continue
            for event in day_events:
                event_id = event.get("idEvent")
                if event_id and event_id in existing_ids:
                    continue
                if not is_upcoming_event(event, now):
                    continue
                extra_events.append(event)
                if event_id:
                    existing_ids.add(event_id)
            if len(filtered_upcoming) + len(extra_events) >= limit:
                break
        filtered_upcoming.extend(extra_events)

    if not filtered_upcoming:
        raise HTTPException(
            status_code=404, detail="No upcoming events found for this league"
        )

    ratings = compute_elo_ratings(past_events)
    missing_team_ids: List[str] = []
    for event in filtered_upcoming:
        home = event.get("strHomeTeam")
        away = event.get("strAwayTeam")
        home_id = event.get("idHomeTeam")
        away_id = event.get("idAwayTeam")
        if home_id and home and home not in ratings:
            missing_team_ids.append(home_id)
        if away_id and away and away not in ratings:
            missing_team_ids.append(away_id)

    if missing_team_ids:
        seen_event_ids = {e.get("idEvent") for e in past_events if e.get("idEvent")}
        seen_composite: set[str] = set()
        extra_rating_events: List[Dict[str, Any]] = []
        unique_team_ids = list(dict.fromkeys(missing_team_ids))
        for team_id in unique_team_ids[:MAX_TEAM_LOOKUPS]:
            try:
                team_events = await _client.get_team_last_events(team_id)
            except httpx.HTTPError:
                continue
            for event in team_events:
                event_id = event.get("idEvent")
                if event_id:
                    if event_id in seen_event_ids:
                        continue
                    seen_event_ids.add(event_id)
                else:
                    composite = (
                        f"{event.get('dateEvent')}|"
                        f"{event.get('strHomeTeam')}|"
                        f"{event.get('strAwayTeam')}"
                    )
                    if composite in seen_composite:
                        continue
                    seen_composite.add(composite)
                extra_rating_events.append(event)
        if extra_rating_events:
            update_elo_ratings(ratings, extra_rating_events)
    predictions: List[Dict[str, Any]] = []
    for event in sorted(filtered_upcoming, key=upcoming_sort_key):
        prediction = build_prediction(event, ratings)
        if prediction:
            predictions.append(prediction)

    predictions = predictions[:limit]
    if not predictions:
        raise HTTPException(
            status_code=404, detail="No upcoming events found for this league"
        )

    response: Dict[str, Any] = {
        "league": league_key,
        "model": "elo",
        "data_source": "TheSportsDB",
        "requested": limit,
        "returned": len(predictions),
        "predictions": predictions,
    }
    if len(predictions) < limit:
        response["note"] = (
            "Only a limited number of upcoming games were found in the next "
            f"{LOOKAHEAD_DAYS} days."
        )

    return response
