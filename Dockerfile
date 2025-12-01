FROM python:3.12-slim-bookworm

# Set working directory
WORKDIR /app

# Copy project files
COPY . .

# Install dependencies
# We use pip to install the package and its dependencies from pyproject.toml
RUN pip install --no-cache-dir .
# Clean up build artifacts that clutter ADK agent discovery
RUN rm -rf build *.egg-info

# Install Playwright browsers and dependencies
# We install chromium and its dependencies. 
# Note: We are using the 'playwright' CLI which is installed as a dependency.
RUN playwright install --with-deps chromium

RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# Cloud Run expects the app to listen on $PORT (default 8080)
ENV PORT=8080
ENV PYTHONUNBUFFERED=1

# Start ADK web server for the agent, binding to 0.0.0.0:$PORT
CMD ["sh", "-c", "adk web --host 0.0.0.0 --port ${PORT:-8080} /app"]
