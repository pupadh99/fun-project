# Sports Outcome Prediction App (Educational)

This project is a lightweight API that produces simple sports outcome predictions
for the four major US leagues (NFL, NBA, MLB, NHL). It uses public data from the
TheSportsDB API and a basic Elo-style rating model.

**Note:** This is for educational and analytics purposes only. It is not intended
for gambling or wagering decisions.

## Features
- Fetches recent and upcoming events via TheSportsDB API
- Builds Elo ratings from recent results
- Predicts win probabilities for upcoming games
- FastAPI endpoints for easy integration

## Requirements
- Python 3.10+
- TheSportsDB API key (free tier supported)

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Set your API key (optional for testing):
   ```bash
   export SPORTSDB_API_KEY="YOUR_KEY_HERE"
   ```
   If you do not set this, the app will use the public test key `1`.

3. Run the API:
   ```bash
   uvicorn app.main:app --reload
   ```

## Endpoints

### `GET /health`
Simple health check.

### `GET /leagues`
Returns supported leagues and IDs.

### `GET /predict?league=NFL&limit=5`
Returns predictions for upcoming games in the selected league.

**Parameters**
- `league` (required): `NFL`, `NBA`, `MLB`, or `NHL`
- `limit` (optional): number of upcoming events to return (1-20)

## Example Response
```json
{
  "league": "NFL",
  "model": "elo",
  "predictions": [
    {
      "event_id": "123456",
      "event": "Team A vs Team B",
      "start_time": "2026-02-01T18:00:00+00:00",
      "home_team": "Team A",
      "away_team": "Team B",
      "home_win_prob": 0.58,
      "away_win_prob": 0.42,
      "predicted_winner": "Team A"
    }
  ]
}
```

## Notes
- Predictions are based on a simple Elo model and limited recent game data.
- Accuracy will vary; the app is a demonstration of workflow and API usage.
