FROM python:3.11-slim

# Install Playwright system dependencies
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first for caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright Chromium
RUN playwright install chromium
RUN playwright install-deps chromium

# Copy app code
COPY . .

# Expose port
EXPOSE 8080

# Run the app
CMD ["python", "app.py"]
