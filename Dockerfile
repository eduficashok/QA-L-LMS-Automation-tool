FROM mcr.microsoft.com/playwright/python:v1.49.0-noble

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Use PORT from environment (Render sets this automatically)
CMD ["python", "web_dashboard_server.py", "--no-browser"]
