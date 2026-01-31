from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

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
RECENT_GAMES = int(os.getenv("SPORTSDB_RECENT_GAMES", "5"))
H2H_GAMES = int(os.getenv("SPORTSDB_H2H_GAMES", "5"))
REST_DAYS_CAP = int(os.getenv("SPORTSDB_REST_CAP", "14"))
MAX_FEATURE_ADJUSTMENT = float(os.getenv("SPORTSDB_MAX_ADJUSTMENT", "400"))

WEIGHT_WIN_PCT = float(os.getenv("SPORTSDB_WEIGHT_WIN_PCT", "160"))
WEIGHT_RECENT = float(os.getenv("SPORTSDB_WEIGHT_RECENT", "120"))
WEIGHT_H2H = float(os.getenv("SPORTSDB_WEIGHT_H2H", "80"))
WEIGHT_REST = float(os.getenv("SPORTSDB_WEIGHT_REST", "5"))
POINT_DIFF_WEIGHT_MULTIPLIER = float(os.getenv("SPORTSDB_WEIGHT_POINT_DIFF", "1.0"))

POINT_DIFF_WEIGHTS = {
    "Basketball": 6.0 * POINT_DIFF_WEIGHT_MULTIPLIER,
    "Baseball": 25.0 * POINT_DIFF_WEIGHT_MULTIPLIER,
    "American Football": 10.0 * POINT_DIFF_WEIGHT_MULTIPLIER,
    "Ice Hockey": 20.0 * POINT_DIFF_WEIGHT_MULTIPLIER,
}
DEFAULT_POINT_DIFF_WEIGHT = 8.0 * POINT_DIFF_WEIGHT_MULTIPLIER

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
          Educational predictions for NFL, NBA, MLB, and NHL using an Elo-based
          model blended with recent form, record, head-to-head, point
          differential, and rest days from TheSportsDB data.
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


@dataclass
class CompletedEvent:
    date: datetime
    home_team: str
    away_team: str
    home_score: int
    away_score: int


@dataclass
class TeamStats:
    games: int = 0
    wins: int = 0
    losses: int = 0
    ties: int = 0
    points_for: int = 0
    points_against: int = 0
    last_game_date: Optional[datetime] = None
    results: List[float] = field(default_factory=list)
    point_diffs: List[int] = field(default_factory=list)


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


def is_completed_event(event: Dict[str, Any]) -> bool:
    status = normalize_status(event.get("strStatus"))
    home_score = parse_score(event.get("intHomeScore"))
    away_score = parse_score(event.get("intAwayScore"))
    if home_score is None or away_score is None:
        return False
    if status in FINISHED_STATUSES:
        return True
    if status in UPCOMING_STATUSES:
        return False
    if status:
        return False
    return True


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


def clamp_value(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def point_diff_weight(sport: str) -> float:
    return POINT_DIFF_WEIGHTS.get(sport, DEFAULT_POINT_DIFF_WEIGHT)


def extract_completed_event(event: Dict[str, Any]) -> Optional[CompletedEvent]:
    if not is_completed_event(event):
        return None
    home = event.get("strHomeTeam")
    away = event.get("strAwayTeam")
    if not home or not away:
        return None
    home_score = parse_score(event.get("intHomeScore"))
    away_score = parse_score(event.get("intAwayScore"))
    if home_score is None or away_score is None:
        return None
    event_dt = parse_event_datetime(event)
    if event_dt is None:
        event_dt = datetime.min.replace(tzinfo=timezone.utc)
    elif event_dt.tzinfo is None:
        event_dt = event_dt.replace(tzinfo=timezone.utc)
    return CompletedEvent(
        date=event_dt,
        home_team=home,
        away_team=away,
        home_score=home_score,
        away_score=away_score,
    )


def build_team_stats(events: List[CompletedEvent]) -> Dict[str, TeamStats]:
    stats: Dict[str, TeamStats] = {}

    def update_team(
        team: str, scored: int, allowed: int, event_date: datetime
    ) -> None:
        team_stats = stats.setdefault(team, TeamStats())
        team_stats.games += 1
        team_stats.points_for += scored
        team_stats.points_against += allowed
        if scored > allowed:
            team_stats.wins += 1
            result = 1.0
        elif scored < allowed:
            team_stats.losses += 1
            result = 0.0
        else:
            team_stats.ties += 1
            result = 0.5
        team_stats.results.append(result)
        team_stats.point_diffs.append(scored - allowed)
        if team_stats.last_game_date is None or event_date > team_stats.last_game_date:
            team_stats.last_game_date = event_date

    for event in sorted(events, key=lambda item: item.date):
        update_team(event.home_team, event.home_score, event.away_score, event.date)
        update_team(event.away_team, event.away_score, event.home_score, event.date)

    return stats


def build_matchup_history(
    events: List[CompletedEvent],
) -> Dict[Tuple[str, str], List[CompletedEvent]]:
    history: Dict[Tuple[str, str], List[CompletedEvent]] = {}
    for event in events:
        key = tuple(sorted((event.home_team, event.away_team)))
        history.setdefault(key, []).append(event)
    for matchups in history.values():
        matchups.sort(key=lambda item: item.date)
    return history


def compute_team_features(stats: Optional[TeamStats], now: datetime) -> Dict[str, Any]:
    if not stats or stats.games == 0:
        return {
            "win_pct": 0.5,
            "recent_win_pct": 0.5,
            "avg_point_diff": 0.0,
            "rest_days": None,
        }

    win_pct = (stats.wins + 0.5 * stats.ties) / stats.games
    recent_results = stats.results[-RECENT_GAMES:]
    if recent_results:
        recent_win_pct = sum(recent_results) / len(recent_results)
    else:
        recent_win_pct = win_pct
    avg_point_diff = (stats.points_for - stats.points_against) / stats.games
    rest_days: Optional[int] = None
    if stats.last_game_date:
        rest_days = (now - stats.last_game_date).days
        rest_days = max(0, min(rest_days, REST_DAYS_CAP))

    return {
        "win_pct": win_pct,
        "recent_win_pct": recent_win_pct,
        "avg_point_diff": avg_point_diff,
        "rest_days": rest_days,
    }


def head_to_head_diff(
    home_team: str,
    away_team: str,
    matchup_history: Dict[Tuple[str, str], List[CompletedEvent]],
) -> float:
    key = tuple(sorted((home_team, away_team)))
    events = matchup_history.get(key, [])
    if not events:
        return 0.0
    recent_events = events[-H2H_GAMES:]
    home_wins = 0
    away_wins = 0
    ties = 0
    for event in recent_events:
        if event.home_score == event.away_score:
            ties += 1
            continue
        winner = event.home_team if event.home_score > event.away_score else event.away_team
        if winner == home_team:
            home_wins += 1
        elif winner == away_team:
            away_wins += 1
    total = home_wins + away_wins + ties
    if total == 0:
        return 0.0
    home_pct = (home_wins + 0.5 * ties) / total
    return (2 * home_pct) - 1


def compute_feature_adjustment(
    home_team: str,
    away_team: str,
    team_stats: Dict[str, TeamStats],
    matchup_history: Dict[Tuple[str, str], List[CompletedEvent]],
    now: datetime,
    sport: str,
) -> float:
    home_features = compute_team_features(team_stats.get(home_team), now)
    away_features = compute_team_features(team_stats.get(away_team), now)

    win_pct_diff = home_features["win_pct"] - away_features["win_pct"]
    recent_diff = home_features["recent_win_pct"] - away_features["recent_win_pct"]
    point_diff_diff = home_features["avg_point_diff"] - away_features["avg_point_diff"]

    rest_diff = 0.0
    if home_features["rest_days"] is not None and away_features["rest_days"] is not None:
        rest_diff = float(home_features["rest_days"] - away_features["rest_days"])

    adjustment = (
        win_pct_diff * WEIGHT_WIN_PCT
        + recent_diff * WEIGHT_RECENT
        + head_to_head_diff(home_team, away_team, matchup_history) * WEIGHT_H2H
        + point_diff_diff * point_diff_weight(sport)
        + rest_diff * WEIGHT_REST
    )

    return clamp_value(adjustment, -MAX_FEATURE_ADJUSTMENT, MAX_FEATURE_ADJUSTMENT)


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
    event: Dict[str, Any],
    ratings: Dict[str, float],
    team_stats: Dict[str, TeamStats],
    matchup_history: Dict[Tuple[str, str], List[CompletedEvent]],
    now: datetime,
    sport: str,
) -> Optional[Dict[str, Any]]:
    home = event.get("strHomeTeam")
    away = event.get("strAwayTeam")
    if not home or not away:
        return None
    home_rating = ratings.get(home, BASE_ELO)
    away_rating = ratings.get(away, BASE_ELO)
    adjustment = compute_feature_adjustment(
        home, away, team_stats, matchup_history, now, sport
    )
    home_prob = expected_score(home_rating + HOME_ADVANTAGE + adjustment, away_rating)
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
    extra_rating_events: List[Dict[str, Any]] = []
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
    completed_events: List[CompletedEvent] = []
    seen_event_ids: set[str] = set()
    seen_composite: set[str] = set()
    for event in past_events + extra_rating_events:
        completed = extract_completed_event(event)
        if completed is None:
            continue
        event_id = event.get("idEvent")
        if event_id:
            if event_id in seen_event_ids:
                continue
            seen_event_ids.add(event_id)
        else:
            composite = (
                f"{completed.date.date()}|"
                f"{completed.home_team}|"
                f"{completed.away_team}|"
                f"{completed.home_score}|"
                f"{completed.away_score}"
            )
            if composite in seen_composite:
                continue
            seen_composite.add(composite)
        completed_events.append(completed)

    team_stats = build_team_stats(completed_events)
    matchup_history = build_matchup_history(completed_events)
    predictions: List[Dict[str, Any]] = []
    for event in sorted(filtered_upcoming, key=upcoming_sort_key):
        prediction = build_prediction(
            event, ratings, team_stats, matchup_history, now, league_sport
        )
        if prediction:
            predictions.append(prediction)

    predictions = predictions[:limit]
    if not predictions:
        raise HTTPException(
            status_code=404, detail="No upcoming events found for this league"
        )

    response: Dict[str, Any] = {
        "league": league_key,
        "model": "elo-plus",
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
