from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, HTTPException, Query

LEAGUES: Dict[str, Dict[str, str]] = {
    "NFL": {"id": "4391", "name": "National Football League"},
    "NBA": {"id": "4387", "name": "National Basketball Association"},
    "MLB": {"id": "4424", "name": "Major League Baseball"},
    "NHL": {"id": "4380", "name": "National Hockey League"},
}

DEFAULT_API_KEY = "123"
BASE_ELO = 1500.0
K_FACTOR = 20.0
CACHE_TTL_SECONDS = int(os.getenv("SPORTSDB_CACHE_TTL_SECONDS", "300"))


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


def expected_score(rating_a: float, rating_b: float) -> float:
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400.0))


def compute_elo_ratings(events: List[Dict[str, Any]]) -> Dict[str, float]:
    ratings: Dict[str, float] = {}

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
    home_prob = expected_score(home_rating, away_rating)
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
    try:
        past_events = await _client.get_past_events(league_id)
        upcoming_events = await _client.get_next_events(league_id)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail="Data provider request failed"
        ) from exc

    if not upcoming_events:
        raise HTTPException(
            status_code=404, detail="No upcoming events found for this league"
        )

    ratings = compute_elo_ratings(past_events)
    predictions: List[Dict[str, Any]] = []
    for event in upcoming_events:
        prediction = build_prediction(event, ratings)
        if prediction:
            predictions.append(prediction)

    return {
        "league": league_key,
        "model": "elo",
        "data_source": "TheSportsDB",
        "predictions": predictions[:limit],
    }
