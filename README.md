# Ottawa Public Health Agent

## Project Overview
- **Purpose**: An AI assistant that answers Ottawa Public Health questions and surfaces live outbreak data for people who don’t want to read raw charts. It can be embedded on a website (e.g., OPH) to give conversational answers, visitor guidance, and data lookups.
- **How it works**: Scrapes the official OPH PowerBI dashboards (MCP + Playwright), normalizes them to CSV, and routes user intents to specialist agents (research, advice, analysis, time, health data).
- **Data & memory**: Conversations and state persist in a database (SQLite locally, Cloud SQL in production) so sessions survive refreshes and can be resumed.
- **Impact**: Makes outbreak and public health info accessible to non-technical users, answering “what’s happening now?” and “what should I do?” in plain language.

## Architecture at a Glance
- **Scraper pipeline**: Playwright (via patchright) renders PowerBI dashboards → BeautifulSoup parses ARIA tables → data returned as CSV/structured text.
- **Agents (google-adk)**:
  - `RetrieveHealthDataAgent` for current OPH facility outbreaks (MCP tool).
  - `HealthAdviceAgent` for visitor guidance and public health Q&A.
  - `ResearchAgent` for web facts; `DataAnalystAgent` for code/analysis; `SummarizerAgent` for rollups; `TimeAgent` for accurate time.
  - Deterministic router and root agent orchestrate tools, keep guardrails.
- **Storage**: `DatabaseSessionService` for events/sessions (SQLite locally, Cloud SQL in Cloud Run). Optional file logging.
- **Sandboxes**: `microsandbox` for untrusted code execution; MCP for data retrieval separation.

## Environment Setup (local)
```bash
# 0) Clone
git clone https://github.com/leocheda/ottawa-public-health-agent.git
cd ottawa-public-health-agent

# 1) Install deps
uv sync

# 2) Install microsandbox CLI
curl -sSL https://get.microsandbox.dev | sh

# 3) First run only: install Playwright Chromium
uv run playwright install chromium

# 4) Set env vars: copy sample and add your Gemini key
cp .env.sample .env
# edit .env and set GEMINI_API_KEY=your_key_here (or GOOGLE_API_KEY if you use that)

# 5) Start microsandbox (new terminal)
msb server start --dev

# 6) Launch Web UI (local)
uv run adk web --session_service_uri sqlite+aiosqlite:///my_agent_data.db
# open http://127.0.0.1:8000/dev-ui/?app=ottawa_public_health_agent
```

## Cloud (Cloud Run + Cloud SQL)
- **Image**: build/push your Dockerfile image to Artifact Registry, then deploy to Cloud Run with:
  - `SESSION_SERVICE_URI` pointing to your Cloud SQL Postgres (async URI, e.g. `postgresql+asyncpg://USER:PASSWORD@/DB?host=/cloudsql/PROJECT:REGION:INSTANCE`).
  - `GEMINI_API_KEY` (or secret) injected via env/Secret Manager.
  - Cloud SQL connection bound; service account has Cloud SQL Client + Secret Accessor.
- **Access**: Use the deployed URL with dev UI params, e.g.  
  `https://<cloud-run-host>/dev-ui/?app=ottawa_public_health_agent&userId=user&session=b5d79ce9-bf35-40e9-85b2-bb12d2a1b3a1`  
  (No local API key needed if the service has the key configured.)

## Running Modes (local)
- **Web UI (persistent)**: `uv run adk web --session_service_uri sqlite+aiosqlite:///my_agent_data.db`
- **Web UI (quick debug)**: `uv run adk web --log_level DEBUG .`
- **Resume CLI session**: `USER_ID=my_user SESSION_ID=my_session uv run python resume_cli.py`
- **Optional logging**: prepend `OPH_AGENT_FILE_LOGS=true OPH_AGENT_LOG_PATH=logger.log ...`

## Environment Variables
- `GEMINI_API_KEY` (required for Gemini API) – set in `.env`
- `SESSION_SERVICE_URI` (optional; defaults to local SQLite)
- `USER_ID`, `SESSION_ID` (optional; pin a session)
- `OPH_AGENT_FILE_LOGS`, `OPH_AGENT_LOG_PATH` (optional; file logging)

See `.env.sample` for the full list.

## Data & Database
- **Local**: SQLite `my_agent_data.db` via `DatabaseSessionService`.
- **Cloud**: Cloud SQL Postgres URI via `SESSION_SERVICE_URI`.
- Sessions/events keep conversation history; agents use it to resume context and compress older events.

## Quick Commands
- Start microsandbox: `msb server start --dev`
- Run Web UI locally: `uv run adk web --session_service_uri sqlite+aiosqlite:///my_agent_data.db`
- Install Chromium (first run): `uv run playwright install chromium`

## Future Ideas
- Trend detection and weekly briefings
- Public-facing embed on OPH site
- Long-term memory bank (Vertex AI) for cross-session recall
- Social publishing (X/Reddit/Telegram) once APIs are wired


### MCP Server

The MCP server (`mcp_server.py`) is automatically launched by the agent when needed for health data retrieval. It runs as a subprocess using stdio transport.

## Docker

**Build Image**
```bash
docker build -t ottawa-health-agent .
```

**Run Container**
```bash
docker run -p 8000:8000 ottawa-health-agent
```

## Environment Variables

Create a `.env` file for configuration:

```bash
# Optional: Enable file logging
OPH_AGENT_FILE_LOGS=true
OPH_AGENT_LOG_PATH=logger.log

# For persistent sessions
USER_ID=your_user_id
SESSION_ID=your_session_id
```

## Common Tasks

### View Scraped Data
```bash
# List recent HTML dumps
ls -lth last-retrieval-*.html

# Check datasets directory
ls -lh datasets/
```

### Database Operations
```bash
# View sessions in database
sqlite3 my_agent_data.db "SELECT * FROM sessions;"

# Export database to SQL
sqlite3 my_agent_data.db .dump > my_agent_data_dump.sql
```

### Testing the Scraper
```bash
# Test direct scraping (bypasses agent)
uv run python tools/ottawa_health_scraper.py
```

## Troubleshooting

### Microsandbox Issues
```bash
# Restart the microsandbox server
msb server stop
msb server start --dev
```

### Playwright Issues
```bash
# Reinstall browser binaries
uv run playwright install chromium
```

### Clear Session Data
```bash
# Remove database (loses all conversation history)
rm my_agent_data.db
```

## Project Structure

```
ottawa-public-health-agent/
├── ottawa_public_health_agent/  # Main agent code
│   ├── agent.py                 # Multi-agent orchestration
│   └── ...
├── tools/                       # Utilities
│   └── ottawa_health_scraper.py # PowerBI scraping
├── mcp_server.py                # MCP server for data retrieval
├── resume_cli.py                # Persistent CLI interface
├── Sandboxfile                  # Microsandbox configuration
└── .warp/workflows/             # Warp workflow definitions
```

## Warp Workflows

Access pre-configured workflows by typing `#` in Warp terminal, then search:
- `Ottawa Health Agent` - View all project workflows
- `#setup` - Installation commands
- `#dev` - Development commands
- `#web` - Web UI commands
- `#cli` - CLI commands

## Resources

- [Google ADK Documentation](https://google.github.io/adk/)
- [Microsandbox Documentation](https://docs.microsandbox.dev/)
- [Patchright (Playwright fork)](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright)
- [MCP Protocol](https://modelcontextprotocol.io/)
