# Use official Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Disable writing .pyc files and enable unbuffered stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install common system dependencies for Python packages
# These are typical dependencies needed for:
# - build-essential: compiling Python packages with C extensions
# - libffi-dev: used by cryptography and other libraries
# - curl, git, unzip: common tools often needed in Python projects
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    curl \
    git \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency file first to leverage Docker cache
COPY requirements.txt .

# Upgrade pip and install Python dependencies
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . /app

# Default command to run the application (can be overridden in docker-compose)
CMD ["python", "runner.py"]
