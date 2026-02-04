FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt
RUN playwright install chromium && playwright install-deps

COPY . .

EXPOSE 8080

CMD ["streamlit", "run", "app.py", "--server.port", "8080", "--server.headless", "true", "--server.address", "0.0.0.0"]
