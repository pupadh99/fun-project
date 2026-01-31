# Sports Outcome Prediction App (Educational)

This project is a lightweight API that produces sports outcome predictions for
the four major US leagues (NFL, NBA, MLB, NHL). It uses public data from the
TheSportsDB API and blends Elo ratings with recent form, record, head-to-head,
point differential, and rest days.

**Note:** This is for educational and analytics purposes only. It is not intended
for gambling or wagering decisions.

## Features
- Fetches recent and upcoming events via TheSportsDB API
- Builds Elo ratings from recent results
- Blends record, recent form, head-to-head, point differential, and rest days
- Predicts win probabilities for upcoming games
- FastAPI endpoints for easy integration

## Requirements
- Python 3.10+
- TheSportsDB API key (free tier supported)

## Quick Start (New User Guide)

Follow these steps from a clean machine to get the API running and make your
first prediction request.

### 1) Install Python
Make sure Python 3.10+ is installed:
```bash
python3 --version
```

### 2) (Recommended) Create a virtual environment
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3) Install dependencies
From the repository root:
```bash
pip install -r requirements.txt
```

### 4) Get an API key (optional but recommended)
This app uses TheSportsDB. The free tier works for testing.
1. Create an account at https://www.thesportsdb.com/
2. Copy your API key.
3. Set it in your shell:
   ```bash
   export SPORTSDB_API_KEY="YOUR_KEY_HERE"
   ```
If you do not set this, the app will use the public test key `123` (rate limited).

### 5) Run the API server
```bash
uvicorn app.main:app --reload
```
You should see a message like:
```
Uvicorn running on http://127.0.0.1:8000
```

### 6) Open the interactive docs
Visit:
```
http://127.0.0.1:8000/docs
```
You can try requests directly from the Swagger UI.

### 7) Use the web UI
Open:
```
http://127.0.0.1:8000/
```
Select a league, choose a number of games, and click **Get predictions**.

### 8) Make a prediction request
In a new terminal:
```bash
curl "http://127.0.0.1:8000/predict?league=NFL&limit=5"
```

### 9) Try a different league
```bash
curl "http://127.0.0.1:8000/predict?league=NBA&limit=3"
```

## Using Anaconda Navigator

If you prefer Anaconda Navigator, follow these steps to run the app:

### 1) Create a new conda environment
1. Open **Anaconda Navigator**.
2. Click **Environments** (left sidebar).
3. Click **Create**.
4. Name it `sports-predict` and choose **Python 3.10** (or newer).
5. Click **Create**.

### 2) Open a terminal in the new environment
1. Select the `sports-predict` environment in Navigator.
2. Click the **▶** (play) button.
3. Choose **Open Terminal** (macOS/Linux) or **Open Command Prompt / PowerShell** (Windows).

### 3) Install dependencies
In the terminal, move to the repo and install requirements:
```bash
cd /path/to/your/repo
pip install -r requirements.txt
```

### 4) Set your API key (optional but recommended)
You can set the variable in the terminal session:

- macOS/Linux:
  ```bash
  export SPORTSDB_API_KEY="YOUR_KEY_HERE"
  ```
- Windows PowerShell:
  ```powershell
  $env:SPORTSDB_API_KEY="YOUR_KEY_HERE"
  ```
- Windows Command Prompt:
  ```cmd
  set SPORTSDB_API_KEY=YOUR_KEY_HERE
  ```

If you want it to persist for this environment:
```bash
conda env config vars set SPORTSDB_API_KEY=YOUR_KEY_HERE
```
Then close and reopen the terminal so the variable loads.

### 5) Run the API server
```bash
uvicorn app.main:app --reload
```

### 6) Open the interactive docs
Open your browser to:
```
http://127.0.0.1:8000/docs
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

The API filters out completed games and only returns future events. If there
aren't enough games scheduled in the next few days, it will return fewer results
with a helpful note.

### Optional configuration
You can tune the prediction behavior with environment variables:
- `SPORTSDB_LOOKAHEAD_DAYS` (default: 10) how far ahead to search for games
- `SPORTSDB_HOME_ADVANTAGE` (default: 60) Elo points added to home team
- `SPORTSDB_TEAM_LOOKUPS` (default: 12) max team lookups for extra ratings
- `SPORTSDB_RECENT_GAMES` (default: 5) games used for recent form
- `SPORTSDB_H2H_GAMES` (default: 5) games used for head-to-head form
- `SPORTSDB_REST_CAP` (default: 14) max rest days counted
- `SPORTSDB_MAX_ADJUSTMENT` (default: 400) clamp for feature adjustment
- `SPORTSDB_WEIGHT_WIN_PCT` (default: 160) record weight
- `SPORTSDB_WEIGHT_RECENT` (default: 120) recent form weight
- `SPORTSDB_WEIGHT_H2H` (default: 80) head-to-head weight
- `SPORTSDB_WEIGHT_REST` (default: 5) rest-day weight
- `SPORTSDB_WEIGHT_POINT_DIFF` (default: 1.0) point diff multiplier

## Example Response
```json
{
  "league": "NFL",
  "model": "elo-plus",
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
- Predictions are based on Elo plus recent results-derived factors.
- If a team has no recent results, its rating falls back to 1500 (near 50/50).
- Injuries and lineup changes are not available in the free data source.
- Accuracy will vary; the app is a demonstration of workflow and API usage.

## Troubleshooting
- **No upcoming events**: Some leagues may be out of season; try a different league.
- **Rate limited**: Use a personal API key instead of the public test key `123`.
- **Cannot import module**: Ensure your virtual environment is activated.
