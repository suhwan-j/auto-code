FROM python:3.12-slim

# System dependencies for git, shell tools, and curses TUI
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    jq \
    && rm -rf /var/lib/apt/lists/*

# Set up working directory
WORKDIR /app

# Install Python dependencies first (cache layer)
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e . 2>/dev/null || true

# Copy source code
COPY . .
RUN pip install --no-cache-dir -e .

# Default working directory for user projects (mounted at runtime)
WORKDIR /workspace

# Start bash shell — user runs 'totoro' or 'totoro --setup' manually
CMD ["bash"]
