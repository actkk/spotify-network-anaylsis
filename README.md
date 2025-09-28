# Spotify Network Analysis

Utilities and automation for exploring Spotify's social graph via the public web interface. Selenium is used for login and follower traversal, the harvested data is cached locally, and NetworkX powers downstream analytics (loop detection, GraphML export, etc.).

> **Repository URL**: https://github.com/actkk/Spotify-network-analysis.git

## Features
- Automated Selenium login with cookie reuse and configurable throttling
- Breadth-first crawl of follower relationships with caching (no profile is visited twice unless data is missing)
- Local JSON storage for profiles (`profiles.json`) and edges (`edges.json`) with UTF-8 names and avatars
- Analytics helpers: GraphML export keyed by display names, triangle (friend-of-friend) detection, loop summaries saved to `data/loops.txt`

## Prerequisites
- macOS or Linux with Python 3.10+
- Google Chrome and compatible ChromeDriver (installed via Homebrew in this setup)
- A Spotify account you are authorised to use (respect Spotify's ToS; scraping is at your own risk)

## Quick Start
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
# Populate .env with SPOTIFY_USERNAME and SPOTIFY_PASSWORD (never commit this file)
python -m spotify_graph.cli --help
```

## Environment Variables (`.env`)
```
SPOTIFY_USERNAME=your_username
SPOTIFY_PASSWORD=your_password
SPOTIFY_BASE_URL=https://open.spotify.com
SPOTIFY_LOGIN_URL=https://accounts.spotify.com/en/login?&allow_password=1
CRAWL_MAX_DEPTH=2
FOLLOWER_THRESHOLD=1000
SCROLL_PAUSE_SECONDS=0.3
MAX_SCROLL_ITERATIONS=30
MANUAL_LOGIN_TIMEOUT_SECONDS=300
```

## Cookie-Based Sessions
Authenticating once and reusing cookies speeds up future crawls:
```bash
python -m spotify_graph.cli login-test --no-headless --save-cookies --cookie-file data/cookies.json
python -m spotify_graph.cli scrape <profile> --use-cookies --cookie-file data/cookies.json --no-headless
```
Cookie files act like session tokens—store them securely and regenerate when they expire. `.gitignore` already excludes `.env`, `data/`, and other sensitive artefacts.

## Crawling
```bash
python -m spotify_graph.cli scrape https://open.spotify.com/user/<profile_id> \
  --depth 1 \
  --no-headless \
  --manual-login
```
- Followers are traversed breadth-first up to `depth` levels.
- Profiles already seen with complete follower data are read from cache; Selenium only visits new or incomplete nodes.
- High-degree accounts (>= `FOLLOWER_THRESHOLD`) are skipped to keep the graph manageable.

## Analytics
### Export GraphML
```bash
python -m spotify_graph.cli export-graph --output data/graph.graphml --exclude-private
```
Import the resulting GraphML into Gephi, Cytoscape, or NetworkX for custom analysis.

### Loop Detection
```bash
python -m spotify_graph.cli analyze-loops --exclude-private
cat data/loops.txt  # saved friend-of-friend triangles
```
Triangles are returned using display names to make inspection easier. The loader writes results to `data/loops.txt` for reuse.

## Development Notes
- All source lives under `src/spotify_graph`. Set `PYTHONPATH=src` when running modules directly.
- Formatting and linting are not enforced; follow your usual Python guidelines.
- Selenium selectors rely on Spotify's current DOM—if the site changes you may need to adjust `profile_page.py`.

## Security & Compliance
- Never commit `.env`, `data/`, or any credential files. `.gitignore` covers them by default.
- Use your personal Spotify account responsibly; scraping may violate Spotify's Terms of Service. Proceed only if you accept that risk.
- Rotate credentials if Selenium encounters repeated login failures or you suspect cookies were compromised.

## Repository Description (for GitHub)
"Automation and analytics toolkit for mapping Spotify follower networks with Selenium crawlers and NetworkX-based insights."
