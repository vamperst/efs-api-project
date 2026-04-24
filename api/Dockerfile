FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

# User uid/gid 1000 - bate com o posix_user do EFS access point
RUN groupadd -g 1000 apiuser && useradd -u 1000 -g 1000 -m -s /bin/bash apiuser

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app

USER apiuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
