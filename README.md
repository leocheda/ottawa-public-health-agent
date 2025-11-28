# README.md

This file provides guidance to the Weekly Health Briefing Agent when working with code in this repository.

## Project Overview

Weekly Health Briefing system that collects real-time outbreak data from Ottawa Public Health PowerBI dashboards, analyzes trends, generates human-friendly briefings, and (planned) publishes to social media platforms.

## Development Setup

### Environment Setup
```sh
# Install dependencies using uv
uv sync

# Install microsandbox CLI (for sandboxed code execution)
curl -sSL https://get.microsandbox.dev | sh
```

### Start Development Environment
```sh
# Start microsandbox server in dev mode (required for agent execution)
msb server start --dev

# Run the agent in a separate process
uv run adk run ./ottawa_public_health_agent

# OR Run the ADK Web Interface
uv run adk web
# Then access at http://127.0.0.1:8000
```

### Run Standalone Scripts
```sh
# Run sync version of data retrieval
uv run python main.py

# Run async version
uv run python main_async.py
```

## Architecture Overview

### Core Components

**Data Pipeline**
- **Web scraping layer**: Uses Playwright (via patchright) to retrieve PowerBI dashboard content from Ottawa Public Health
- **HTML parsing layer**: BeautifulSoup extracts tabular data from PowerBI embedded reports based on ARIA role attributes (columnheader, rowheader, gridcell)
- **Data extraction**: Custom logic handles PowerBI's multi-table HTML structure, tracking table boundaries via column headers

**Agent System (health_agent/)**
- Built on Google ADK (Agent Development Kit)
- Exposes two tools to the LLM:
  - `retrieve_health_data_tool()`: Fetches and parses Ottawa health outbreak data
  - `tool_run_python_code()`: Executes Python code in isolated microsandbox for data analysis
- Agent uses gemini-2.5-flash model
- Microsandbox environment pre-configured with numpy and pandas (see Sandboxfile)

**Two Data Sources**
1. Outbreaks report - tracks active outbreak cases
2. Diseases of public health significance - requires UI interaction (clicking dataTablesButton) before scraping

### Key Technical Patterns

**PowerBI Scraping Strategy**
- Uses frame navigation events and DOM content loaded signals to detect when PowerBI content is ready
- Implements custom waiting logic (frame_navigated_handler) because PowerBI dashboards load asynchronously
- Saves raw HTML to disk (last-retrieval-*.html) for debugging and reprocessing

**Sandboxed Execution**
- Microsandbox provides isolated Python 3 environment with 2GB memory, 1 CPU
- Volumes mounted: `./datasets` available at `/datasets` in sandbox
- Security: Prevents LLM-generated code from accessing host system

**Async vs Sync**
- `main.py`: Synchronous Playwright API
- `main_async.py` and `agent.py`: Async Playwright API for concurrent operations
- Agent system uses async throughout for tool execution

## Future Development Notes

**Planned Features** (see design-sketch.md)
- Weekly trend identification via LLM analysis
- Human-friendly briefing generation
- Social media publishing (Twitter/X, Reddit, Telegram)
  - OAuth2 setup required for X, LinkedIn, Reddit
  - Telegram is simplest (bot token only)
  - Substack has no developer API

**Data Analysis Approach**
- LLM should use tool_run_python_code for numerical analysis (leverages pandas/numpy in sandbox)
- Can copy CSV data into sandbox filesystem for shell command inspection (head, wc, awk, etc.)

## Dependencies

Key packages:
- `google-adk` - Agent framework
- `patchright` - Playwright fork with anti-detection features
- `microsandbox` - Sandboxed code execution environment
- `beautifulsoup4` + `html5lib` - HTML parsing
- `pbipy` - PowerBI utilities (installed but not actively used in current code)

## Environment Variables

Uses `python-dotenv` - create `.env` file for configuration (agent.py loads via `load_dotenv()`)
