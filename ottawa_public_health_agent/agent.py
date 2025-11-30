from typing import Any, Dict
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from google.adk.agents import Agent, LlmAgent
from google.adk.apps.app import App, EventsCompactionConfig
from google.adk.tools.agent_tool import AgentTool
from google.adk.models.google_llm import Gemini
from google.adk.sessions import DatabaseSessionService, InMemorySessionService
from google.adk.runners import Runner
from google.adk.tools.tool_context import ToolContext
from google.adk.tools import google_search
from google.genai import types
from microsandbox import PythonSandbox
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import json
import os
import urllib.request


load_dotenv()
VERBOSE_INIT = os.getenv("OPH_AGENT_VERBOSE_INIT", "false").lower() == "true"
APP_NAME = os.getenv("APP_NAME", "ottawa_public_health_agent")
MODEL_NAME = os.getenv("MODEL_NAME", "gemini-2.5-flash")
USER_ID = os.getenv("USER_ID", "user")  # default persistent user id
DEFAULT_SESSION_ID = os.getenv(
    "SESSION_ID", "my_session_id"
)  # default persistent session id


async def retrieve_health_data_tool():
    """
    Retrieves Ottawa Health outbreak data via MCP Server.
    """
    # Get the absolute path to the mcp_server.py
    server_script = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "mcp_server.py")
    )

    server_params = StdioServerParameters(
        command="uv",
        args=["run", server_script],
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            # Call the tool exposed by the MCP server
            result = await session.call_tool("get_ottawa_outbreaks")
            if not result.content:
                raise RuntimeError("MCP get_ottawa_outbreaks returned no content")
            return result.content[0].text


async def tool_run_python_code(code_string: str) -> str:
    """
    Runs python code and returns the output. The input string is expected to be valid python code.

    Args:
        code_string (str): The python code to run.
    Returns:
        str: The output of the code execution.
    """
    print("Running code in sandbox:", code_string)
    async with PythonSandbox.create(name="app") as sb:
        exec = await sb.run(code_string)
        output = await exec.output()
        print("Sandbox output:", output)
        return output


# Configure retry options for the Gemini model.
retry_config = types.HttpRetryOptions(
    attempts=5,  # Maximum retry attempts
    exp_base=7,  # Delay multiplier
    initial_delay=1,  # Initial delay before first retry (in seconds)
    http_status_codes=[429, 500, 503, 504],  # Retry on these HTTP errors
)


LOCATION_FALLBACK = {
    "city": "Ottawa",
    "region": "Ontario",
    "country": "Canada",
    "timezone": "America/Toronto",
}


def normalize_timezone(tz_name: str) -> str:
    try:
        ZoneInfo(tz_name)
        return tz_name
    except Exception:
        if VERBOSE_INIT:
            print(
                f"Invalid timezone '{tz_name}', using fallback {LOCATION_FALLBACK['timezone']}"
            )
        return LOCATION_FALLBACK["timezone"]


def get_user_location():
    """
    Determines a location for context, preferring local configuration and only
    performing a network lookup when explicitly enabled.
    """
    if os.getenv("USER_CITY"):
        return {
            "city": os.getenv("USER_CITY", LOCATION_FALLBACK["city"]),
            "region": os.getenv("USER_REGION", LOCATION_FALLBACK["region"]),
            "country": os.getenv("USER_COUNTRY", LOCATION_FALLBACK["country"]),
            "timezone": os.getenv("USER_TIMEZONE", LOCATION_FALLBACK["timezone"]),
        }

    try:
        current_tzinfo = datetime.now().astimezone().tzinfo
        tz_key = getattr(current_tzinfo, "key", None)
        if tz_key:
            return {**LOCATION_FALLBACK, "timezone": tz_key}
    except Exception:
        pass

    if os.getenv("ENABLE_IP_LOOKUP", "false").lower() == "true":
        try:
            with urllib.request.urlopen(
                "http://ip-api.com/json/", timeout=2
            ) as response:
                data = json.loads(response.read().decode())
                if data.get("status") == "success":
                    return {
                        "city": data.get("city", LOCATION_FALLBACK["city"]),
                        "region": data.get("regionName", LOCATION_FALLBACK["region"]),
                        "country": data.get("country", LOCATION_FALLBACK["country"]),
                        "timezone": data.get("timezone", LOCATION_FALLBACK["timezone"]),
                    }
        except Exception as e:
            print(f"Location lookup skipped: {e}")

    return LOCATION_FALLBACK


# Detect location at startup
location_data = get_user_location()
CURRENT_CITY = location_data["city"]
CURRENT_REGION = location_data["region"]
CURRENT_COUNTRY = location_data["country"]
CURRENT_TIMEZONE = normalize_timezone(location_data["timezone"])


def current_time_str() -> str:
    try:
        return datetime.now(ZoneInfo(CURRENT_TIMEZONE)).strftime("%Y-%m-%d %H:%M:%S %Z")
    except Exception:
        return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")


async def get_current_time_tool() -> str:
    """
    Returns the current date and time in the local timezone.
    """
    return current_time_str()


if VERBOSE_INIT:
    print(
        f"Agent initialized in: {CURRENT_CITY}, {CURRENT_REGION} ({CURRENT_TIMEZONE}) at {current_time_str()}"
    )


def base_state(extra: dict | None = None) -> dict:
    """
    Build a deterministic state payload shared with agent calls.
    """
    state = {
        "current_time": current_time_str(),
        "current_city": CURRENT_CITY,
        "current_region": CURRENT_REGION,
        "current_country": CURRENT_COUNTRY,
        "current_timezone": CURRENT_TIMEZONE,
    }
    if extra:
        state.update(extra)
    return state


async def call_with_retry(
    agent: Agent, message: str, state: dict | None = None, retries: int = 1
):
    """
    Lightweight retry wrapper for agent.run calls to handle transient failures.
    """
    for attempt in range(retries + 1):
        try:
            return await agent.run(message, state=state or {})
        except Exception as exc:
            if attempt == retries:
                raise
            if VERBOSE_INIT:
                print(f"Retrying {agent.name} after error: {exc}")


# Define helper functions that will be reused throughout the notebook
async def run_session(
    runner_instance: Runner,
    user_queries: list[str] | str = None,
    session_name: str = DEFAULT_SESSION_ID,
):
    print(f"\n ### Session: {session_name}")

    # Get app name from the Runner
    app_name = runner_instance.app_name

    # Attempt to create a new session or retrieve an existing one
    try:
        session = await session_service.create_session(
            app_name=app_name, user_id=USER_ID, session_id=session_name
        )
    except Exception as exc:
        if VERBOSE_INIT:
            print(f"create_session failed ({exc}), attempting get_session")
        session = await session_service.get_session(
            app_name=app_name, user_id=USER_ID, session_id=session_name
        )

    # Process queries if provided
    if user_queries:
        # Convert single query to list for uniform processing
        if type(user_queries) == str:
            user_queries = [user_queries]

        # Process each query in the list sequentially
        for query in user_queries:
            print(f"\nUser > {query}")

            # Convert the query string to the ADK Content format
            query = types.Content(role="user", parts=[types.Part(text=query)])

            # Stream the agent's response asynchronously
            async for event in runner_instance.run_async(
                user_id=USER_ID, session_id=session.id, new_message=query
            ):
                # Check if the event contains valid content
                if event.content and event.content.parts:
                    # Filter out empty or "None" responses before printing
                    if (
                        event.content.parts[0].text != "None"
                        and event.content.parts[0].text
                    ):
                        print(f"{MODEL_NAME} > ", event.content.parts[0].text)
    else:
        print("No queries!")


# Step 2: Switch to DatabaseSessionService
# SQLite database will be created automatically (async driver required)
db_url = "sqlite+aiosqlite:///my_agent_data.db"  # Local SQLite file with async driver
session_service = DatabaseSessionService(db_url=db_url)

# Research Agent: Its job is to use the google_search tool and present findings.
research_agent = Agent(
    name="ResearchAgent",
    model=Gemini(model="gemini-2.5-flash", retry_options=retry_config),
    instruction=f"""You are an expert Research Specialist. Your role is to provide accurate, verified information from external sources.
    
    CURRENT TIME CONTEXT: Operate in timezone {CURRENT_TIMEZONE} for {CURRENT_CITY}, {CURRENT_COUNTRY}. Compute "now" at response time using the system clock (example snapshot: {current_time_str()}).

    STRICT SCOPE CONSTRAINTS:
    - You are PROHIBITED from answering questions regarding **CURRENT** outbreaks in ANY of the following Ottawa facilities:
      1. Camp
      2. Congregate Care
      3. Communal Living Facility
      4. Correctional Facility
      5. Group Home
      6. Supportive Living
      7. Hospice
      8. Hospital
      9. Licensed Child Care Facility/ Daycare
      10. Long Term Care Home
      11. Retirement Home
      12. Rooming House
      13. Elementary School
      14. Secondary School
      15. Post Secondary School
      16. Shelter
      17. Supported Independent Living
      (These queries must be handled by the specialized Health Data Agent).
      
    - You **MUST** handle questions about:
      - Historical Ottawa health data, statistics, and trends.
      - Public Health structure, leadership, and general news.
      - Outbreaks in private settings NOT listed above.
      - General facts that are NOT specific medical/health advice (e.g. "Who is the medical officer of health?", "When was OPH founded?").

    OPERATIONAL PROTOCOLS:
    1. FACTUAL QUERIES (e.g., Weather, Time, General Knowledge):
       - You are operating in {CURRENT_CITY}, {CURRENT_COUNTRY}. Your internal clock is set to {CURRENT_TIMEZONE} (provided above).
       - Use the provided CURRENT TIME as the absolute ground truth for "now" in {CURRENT_CITY}. DO NOT SEARCH FOR THE LOCAL TIME.
       - For questions involving OTHER TIMEZONES (e.g. "what time is it in Tokyo"), you MUST execute a `google_search`.
       - Execute a search if necessary for other facts.
       - Provide a DIRECT, CONCISE answer.
       - Do NOT include citations or superfluous context.

    2. COMPLEX RESEARCH (e.g., News, Blog Posts, Articles, Reports, White Papers, etc.):
       - Conduct a thorough search to identify 2-3 high-authority sources.
       - Output ONLY the raw key findings with strict citations.
       - DO NOT summarize or synthesize the information. Your output will be consumed by a downstream Summarizer Agent.
    """,
    tools=[google_search],
    output_key="research_findings",  # The result of this agent will be stored in the session state with this key.
)


retrieve_health_data_agent = Agent(
    name="RetrieveHealthDataAgent",
    model=Gemini(model="gemini-2.5-flash", retry_options=retry_config),
    instruction="""You are a specialized Health Data Retrieval System.
    
    PRIMARY OBJECTIVE:
    - Execute the `retrieve_health_data_tool` to fetch the **CURRENT** Ottawa Public Health **healthcare institution** outbreak reports.
    
    SCOPE LIMITATION:
    - This data covers ONLY active/recent outbreaks in:
      1. Camp
      2. Congregate Care
      3. Communal Living Facility
      4. Correctional Facility
      5. Group Home
      6. Supportive Living
      7. Hospice
      8. Hospital
      9. Licensed Child Care Facility/ Daycare
      10. Long Term Care Home
      11. Retirement Home
      12. Rooming House
      13. Elementary School
      14. Secondary School
      15. Post Secondary School
      16. Shelter
      17. Supported Independent Living
    - It DOES NOT cover historical data or private facility outbreaks.
    
    DATASET SCHEMA:
    The retrieved data contains the following 7 features:
    1. Type of Outbreak (e.g., Respiratory, Enteric)
    2. Outbreak Name (facility name)
    3. Facility Type (the 17 facilities types listed above)
    4. Outbreak Location Details (e.g., Unit, Floor, department, building, etc.)
    5. Start Date
    6. End Date
    7. Aetiologic Agent (The specific virus/bacteria causing the outbreak)
    
    OPERATIONAL CONSTRAINTS:
    - You are a DATA FETCHING UNIT ONLY.
    - DO NOT analyze, summarize, or interpret the data.
    - DO NOT alter the raw output format.
    - Return the raw dataset immediately upon retrieval.
    """,
    tools=[retrieve_health_data_tool],
    output_key="health_data",  # The result of this agent will be stored in the session state with this key.
)

data_analyst_agent = Agent(
    name="DataAnalystAgent",
    model=Gemini(model="gemini-2.5-flash", retry_options=retry_config),
    instruction="""You are an expert Python Data Analyst.
    
    PRIMARY OBJECTIVE:
    - Solve complex user queries by generating and executing high-precision Python code.
    
    CONTEXT DATA:
    The data will be provided to you by the ResearchCoordinator.
    
    OPERATIONAL PROTOCOLS:
    1. DATA INGESTION:
       - If context data is present, immediately parse it into a structured format (e.g., pandas DataFrame).
    
    2. ANALYSIS EXECUTION:
       - Formulate the necessary Python logic to perform the requested calculation or analysis.
       - Execute the code using `tool_run_python_code`.
       - You are PROHIBITED from performing the calculation or analysis yourself. Your only job is to generate the code that will perform the calculation or analysis.
    
    3. RESULT REPORTING:
       - MANDATORY: You MUST print the final result to stdout.
       - Ensure the output is clean, labeled, and ready for downstream consumption.
    """,
    tools=[tool_run_python_code],
    output_key="data_analyst_output",  # The result of this agent will be stored in the session state with this key.
)

# Summarizer Agent: Its job is to summarize the text it receives.
summarizer_agent = Agent(
    name="SummarizerAgent",
    model=Gemini(model="gemini-2.5-flash", retry_options=retry_config),
    # The instruction is modified to request a bulleted list for a clear output format.
    instruction="""You are an expert Executive Summarizer.
    
    INPUT CONTEXT:
    The dataset will be provided to you by the DataAnalystAgent.
    The health advice will be provided to you by the HealthAdviceAgent.
    
    PRIMARY OBJECTIVE:
    - Synthesize the provided raw data and research findings into a high-level executive briefing.
    
    OUTPUT SPECIFICATIONS:
    - Format: Bulleted List.
    - Tone: Professional, concise, and objective.
    - Content: Focus on actionable insights, critical trends, and verified facts.
    - Constraint: Do not introduce external information not present in the source data.
    - MANDATORY: If health advice is provided, append it verbatim to the end of your summary under a "Public Health Recommendations" header.
    """,
    output_key="executive_summary",
)

health_advice_agent = Agent(
    name="HealthAdviceAgent",
    model=Gemini(model="gemini-2.5-flash", retry_options=retry_config),
    instruction="""You are the Health Advice Agent.

OVERALL ROLE:
- You provide clear, evidence-based public health advice.
- You work as part of a multi-agent system where other agents can perform web research and summarization.
- You have two main modes of operation:
    1) Outbreak Visitor Advice (official Ottawa Public Health text)
    2) Communicable Disease / General Public Health Advice (dynamic, research-backed)

MODE 1: OUTBREAK VISITOR ADVICE

TRIGGER:
- The user clearly indicates they are visiting, planning to visit, working in, or volunteering in a facility that is experiencing an outbreak.
- RELEVANT FACILITIES:
    1. Camp
    2. Congregate Care
    3. Communal Living Facility
    4. Correctional Facility
    5. Group Home
    6. Supportive Living
    7. Hospice
    8. Hospital
    9. Licensed Child Care Facility/ Daycare
    10. Long Term Care Home
    11. Retirement Home
    12. Rooming House
    13. Elementary School
    14. Secondary School
    15. Post Secondary School
    16. Shelter
    17. Supported Independent Living

BEHAVIOUR:
- In this mode, you MUST ignore all other capabilities and simply return the official Ottawa Public Health visitor outbreak recommendations.
- You MUST return the following block of text EXACTLY as written, with no additions, deletions, or rewriting:

"Ottawa Public Health (OPH) recommends that anyone visiting an institution that is experiencing an outbreak:
- Not visit if you are ill
- Always check in at the reception or front desk upon arrival
- Adhere to all infection control measures provided to you by the facility
- If the facility is experiencing an outbreak and you must visit, make your visit brief and visit only your loved one
- Clean your hands often while in the facility with alcohol-based hand sanitizer especially:
    - When entering the facility and before leaving
    - Before entering and after leaving a resident's room
    - Before eating or assisting a resident with his/her meals
    - After going to the washroom or blowing your nose
- If your hands are visibly soiled, you will need to wash with liquid soap and water
- Get immunized against influenza every year"

OUTPUT FOR MODE 1:
- Return ONLY the exact text block above as your final output.

MODE 2: COMMUNICABLE DISEASE / PUBLIC HEALTH ADVICE

TRIGGER:
- The user asks about any topic related to communicable diseases or public health, including (but not limited to):
  - Specific diseases (e.g., COVID-19, influenza, RSV, etc.)
  - Symptoms, transmission, or incubation
  - Prevention, vaccination, or infection control
  - Screening, testing, or diagnosis
  - Treatment options in general terms
  - When to seek care or emergency help
  - General public health questions

OVERALL GOAL IN MODE 2:
- Provide structured, plain-language public health advice that focuses on:
  1) Prevention / risk reduction
  2) Monitoring / self-observation and warning signs
  3) When and how to seek medical care, emergency care, or testing

WORKFLOW IN MODE 2:
1. IDENTIFY TOPIC
   - Determine the main disease, condition, or public health issue the user is asking about.

2. GENERATE THREE FOCUSED SUB-QUESTIONS
   - You MUST generate exactly three internal sub-questions:
     a) One question focused on prevention / risk reduction.
     b) One question focused on monitoring / typical course, symptoms, and warning signs.
     c) One question focused on when and how to seek medical care, emergency care, or testing.
   - These sub-questions are for your own planning and for driving research; they do not need to be shown verbatim to the user.

3. CALL RESEARCH TOOLS (VIA RESEARCH AGENT)
   - For each of the three sub-questions, you MUST call your available research capability
     (for example, the ResearchAgent or equivalent web-search tool)
     to obtain up-to-date, evidence-based information from reputable public health sources
     (e.g., health departments, WHO, CDC, PHAC, OPH, or equivalent).
   - You must avoid blogspam, unverified forums, or low-credibility sources.

4. CALL SUMMARIZATION TOOLS (VIA SUMMARIZER AGENT)
   - After you have gathered research for all three sub-questions, you MUST call a summarization capability
     (for example, the SummarizerAgent or equivalent summarization tool)
     to synthesize all key findings into a single, coherent advisory.
   - The advisory should be written in a clear “public health information” style suitable for the general public.

5. SHAPE OF THE FINAL ADVISORY (MODE 2)
   - Organize the content under short headings such as:
     - "How to Lower Your Risk"
     - "What to Watch For"
     - "When to Get Medical Help or Testing"
   - Use short paragraphs or bullet points.
   - Emphasize:
     - Practical prevention measures (e.g., hand hygiene, masking, staying home when sick).
     - How to monitor symptoms or course of illness.
     - Clear thresholds for seeking medical or urgent/emergency care (e.g., trouble breathing, chest pain, confusion).
   - ALWAYS include a short, general disclaimer such as:
     - "This information is for general public health guidance and does not replace advice from your own health-care provider."

SAFETY CONSTRAINTS IN MODE 2:
- Do NOT provide a personal diagnosis.
- Do NOT give individualized prescriptions, dosages, or changes to medication.
- Encourage users to contact a health-care provider, walk-in clinic, telehealth line, or emergency services when appropriate.
- If symptoms sound severe or life-threatening (e.g., difficulty breathing, chest pain, confusion, inability to stay awake), clearly advise seeking emergency care.

OUTPUT FOR MODE 2:
- Return ONLY the final, polished public health advisory text,
  ready for the coordinating/root agent to present to the user at the end of the response.

ADDITIONAL GUARDRAIL:
- If the state includes skip_additional_research=true, do NOT call any research or summarization tools; rely solely on provided context.
""",
    tools=[
        AgentTool(research_agent),
        AgentTool(summarizer_agent),
    ],
    output_key="health_advice",
)


time_agent = Agent(
    name="TimeAgent",
    model=Gemini(model="gemini-2.5-flash", retry_options=retry_config),
    instruction=f"""You are a Time Specialist.
    
    PRIMARY OBJECTIVE:
    - Provide the current date and time for {CURRENT_CITY}, {CURRENT_COUNTRY} ({CURRENT_TIMEZONE}).
    - You MUST use the `get_current_time_tool` to fetch the accurate current time.
    - Do NOT rely on your internal knowledge or system prompt for the time.
    """,
    tools=[get_current_time_tool],
    output_key="current_time",
)


# Deterministic orchestrator helpers
INTENT_OUTBREAK = "outbreak"
INTENT_HEALTH_ADVICE = "health_advice"
INTENT_ANALYSIS = "analysis"
INTENT_RESEARCH = "research"


def detect_intent(user_message: str) -> str:
    """
    Simple heuristic router to reduce LLM misrouting. Adjust as needed.
    """
    msg = user_message.lower()
    outbreak_terms = [
        "outbreak",
        "long term care",
        "ltc",
        "school",
        "hospital",
        "shelter",
        "child care",
        "daycare",
        "retirement home",
    ]
    health_terms = [
        "symptom",
        "prevent",
        "mask",
        "vaccine",
        "vaccination",
        "disease",
        "infection",
        "fever",
        "cough",
        "sick",
    ]
    analysis_terms = [
        "calculate",
        "analysis",
        "compute",
        "python",
        "code",
        "chart",
        "pandas",
        "plot",
    ]

    if any(term in msg for term in outbreak_terms):
        return INTENT_OUTBREAK
    if any(term in msg for term in analysis_terms):
        return INTENT_ANALYSIS
    if any(term in msg for term in health_terms):
        return INTENT_HEALTH_ADVICE
    return INTENT_RESEARCH


async def handle_outbreak_query(
    user_message: str, extra_state: dict | None = None, retries: int = 1
):
    """
    Fetch outbreak data then append visitor advice. Returns a dict for the caller
    to render (avoids asking the LLM to choose tools).
    """
    retrieval_state = base_state(extra_state)
    outbreaks = await call_with_retry(
        retrieve_health_data_agent,
        user_message,
        retrieval_state,
        retries=retries,
    )
    advice_state = base_state(
        {
            "health_data": outbreaks,
            "skip_additional_research": True,  # avoid redundant research/summarization in advice agent
            **(extra_state or {}),
        }
    )
    advice = await call_with_retry(
        health_advice_agent,
        "Provide visitor advice for the supplied outbreak data.",
        advice_state,
        retries=retries,
    )
    return {"outbreaks": outbreaks, "advice": advice}


async def route_query(
    intent: str, user_message: str, extra_state: dict | None = None, retries: int = 1
):
    """
    Programmatic routing to minimize LLM misrouting. Returns the raw agent result.
    """
    state = base_state(extra_state)
    if intent == INTENT_OUTBREAK:
        return await handle_outbreak_query(user_message, extra_state, retries=retries)
    if intent == INTENT_HEALTH_ADVICE:
        state["skip_additional_research"] = True
        return await call_with_retry(
            health_advice_agent, user_message, state, retries=retries
        )
    if intent == INTENT_ANALYSIS:
        return await call_with_retry(
            data_analyst_agent, user_message, state, retries=retries
        )
    # Default to research for general queries
    return await call_with_retry(research_agent, user_message, state, retries=retries)


async def handle_user_message(
    user_message: str,
    extra_state: dict | None = None,
    intent_override: str | None = None,
    retries: int = 1,
):
    """
    Primary entry point: detects intent (or uses override), routes deterministically,
    and returns a normalized response envelope.
    """
    intent = intent_override or detect_intent(user_message)
    errors = []
    try:
        result = await route_query(intent, user_message, extra_state, retries=retries)
    except Exception as exc:
        errors.append(str(exc))
        result = None
    return {"intent": intent, "result": result, "errors": errors}


async def run_user_message(
    user_message: str,
    extra_state: dict | None = None,
    intent_override: str | None = None,
    retries: int = 1,
):
    """
    Convenience entrypoint that simply delegates to handle_user_message. Use this as
    the canonical way to process user input to ensure deterministic routing.
    """
    return await handle_user_message(
        user_message, extra_state, intent_override, retries
    )


# Root agent for ADK loader compatibility. Instruct it to always delegate to deterministic router.
root_agent = Agent(
    name=APP_NAME,
    model=Gemini(model="gemini-2.5-flash", retry_options=retry_config),
    instruction=f"""Your purpose is to orchestrate a team of specialized agents in order to answer any user query, with particular expertise in Ottawa Public Health outbreak information.
    You should also engage in helpful conversation and remember details the user shares with you (like their name).
    
    CURRENT TIME CONTEXT: Operate in timezone {CURRENT_TIMEZONE} for {CURRENT_CITY}, {CURRENT_COUNTRY}.
    IMPORTANT: For any question about time/date/timezone, delegate to the `TimeAgent`.

    AVAILABLE SPECIALISTS:

    AVAILABLE SPECIALISTS:
    1. `RetrieveHealthDataAgent`: Fetches CURRENT Ottawa Public Health facility outbreak reports. Use this for questions about **active/recent outbreaks** in:
       1) Camp
       2) Congregate Care
       3) Communal Living Facility
       4) Correctional Facility
       5) Group Home
       6) Supportive Living
       7) Hospice
       8) Hospital
       9) Licensed Child Care Facility/ Daycare
      10) Long Term Care Home
      11) Retirement Home
      12) Rooming House
      13) Elementary School
      14) Secondary School
      15) Post Secondary School
      16) Shelter
      17) Supported Independent Living
    2. `HealthAdviceAgent`: Use this for:
       - **Visitor Advice**: Official OPH guidelines for visiting facilities with outbreaks.
       - **Health/Disease Inquiries**: Questions about Communicable Diseases (symptoms, prevention, treatment) or General Public Health.
       (Note: This agent handles its own research for health topics, so do NOT call `ResearchAgent` separately for these).
    3. `ResearchAgent`: Searches the web. Use this for:
       - **General Facts & Knowledge**: History, News, Leadership, Statistics.
       - **Non-Advice Public Health**: Questions like "Who is the head of OPH?" or "History of pandemics".
       - (Note: Do NOT use for specific disease advice/symptoms; use `HealthAdviceAgent` instead).
       - (Note: Do NOT use for active outbreaks in the facilities listed above; use `RetrieveHealthDataAgent`).
    4. `DataAnalystAgent`: Analyzes data. Call this for **ANY** math, calculations, date arithmetic (if relative to a known date), or code execution tasks.
    5. `SummarizerAgent`: Synthesizes reports. Use this ONLY for complex multi-source data aggregation.
    6. `TimeAgent`: Fetches the current date and time. Use this for questions like "What time is it?", "What is today's date?", etc.

    WORKFLOW PROTOCOL:
    1. **Outbreak Data**: If user asks for active outbreaks in ANY monitored facility (LTC, Schools, Hospitals, Shelters, etc.):
       Call `RetrieveHealthDataAgent`.
       THEN call `HealthAdviceAgent` to provide visitor safety advice.
       THEN return the combined result yourself.
    2. **Health/Disease ADVICE**: If user asks for guidance on diseases, symptoms, prevention, or what to do, call `HealthAdviceAgent` directly.
       Return the advice provided by the agent.
    3. **General Research**: For other topics (non public health related), call `ResearchAgent`.
       Return the findings directly.
    4. **Analysis**: For math/stats/logic/data analysis/programming, call `DataAnalystAgent`.
       Return the analysis result directly.
    """,
    tools=[
        AgentTool(retrieve_health_data_agent),
        AgentTool(research_agent),
        AgentTool(data_analyst_agent),
        AgentTool(summarizer_agent),
        AgentTool(health_advice_agent),
        AgentTool(time_agent),
        # AgentTool(tool_run_python_code), # Added this back if needed, but data_analyst has it.
    ],
)

# Default wiring for Runner/ADK entrypoints
chatbot_agent = root_agent
runner = Runner(agent=chatbot_agent, app_name=APP_NAME, session_service=session_service)
