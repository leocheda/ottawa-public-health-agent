FROM python:3.12-slim-bookworm

# Set working directory
WORKDIR /app

# Copy project files
COPY . .

# Install dependencies
# We use pip to install the package and its dependencies from pyproject.toml
RUN pip install --no-cache-dir .

# Install Playwright browsers and dependencies
# We install chromium and its dependencies. 
# Note: We are using the 'playwright' CLI which is installed as a dependency.
RUN playwright install --with-deps chromium

# Expose port if needed (Cloud Run typically uses 8080, but this agent might be a background worker)
# ENV PORT=8080

# Command to run the application
# Using unbuffered output for logging
ENV PYTHONUNBUFFERED=1
CMD ["python", "main.py"]
