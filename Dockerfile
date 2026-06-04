FROM python:3.12-slim-bookworm

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    unzip \
    ca-certificates \
    libnss3 \
    libatk-bridge2.0-0 \
    libx11-xcb1 \
    libxcb-dri3-0 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install Bun natively (needed for GBrain CLI tools)
RUN curl -fsSL https://bun.sh/install | bash
ENV PATH="/root/.bun/bin:${PATH}"

# Install Terraform CLI
RUN curl -fsSL https://releases.hashicorp.com/terraform/1.8.5/terraform_1.8.5_linux_amd64.zip -o terraform.zip \
    && unzip terraform.zip \
    && mv terraform /usr/local/bin/ \
    && rm terraform.zip

# Configure working directory
WORKDIR /workspace

# Install python dependencies
RUN pip install --upgrade pip
RUN pip install --no-cache-dir \
    ollama \
    playwright \
    psutil \
    colorama \
    fastapi \
    uvicorn \
    websockets \
    python-dotenv \
    google-generativeai \
    anthropic \
    openai \
    pytest

# Install Playwright and Chromium browser binary (with dependencies)
RUN playwright install chromium
RUN playwright install-deps chromium

# Set startup command to bash by default
CMD ["bash"]
