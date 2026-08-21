FROM python:3.11-slim

# Install system dependencies (git for GitPython, curl, build essentials)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy source code and config
COPY . .

# Expose Streamlit port
EXPOSE 8501

# Default command runs Streamlit interface (can be overridden to CLI)
CMD ["streamlit", "run", "interface/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
