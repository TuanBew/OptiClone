FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY scraper/ scraper/
COPY delta/ delta/
COPY uploader/ uploader/

RUN mkdir -p state logs articles

RUN useradd -r -s /bin/false appuser && chown -R appuser:appuser /app
USER appuser

ENTRYPOINT ["python", "main.py"]
