FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
  fft popeye && \
  git && \
  python3-pip && \
  curl && \
  wget && \
  dos2unix && \
  && apt-get clean && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy application code
COPY . .

# Expose necessary ports (adjust based on app requirements)
EXPOSE 8080 4200 7860

# Default command (modify as needed)
CMD ["python", "agent_loop.py"]