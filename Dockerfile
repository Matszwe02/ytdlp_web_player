FROM python:3.13-slim AS builder
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir GitPython
WORKDIR /build
COPY . /build/
RUN python src/version.py


FROM python:3.13-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg nodejs \
    && ffmpeg -hide_banner -encoders | grep -q 'h264_nvenc' \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY src/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY --from=builder /build/version.txt /app/
COPY src/. /app
COPY extension/extension.js /app/static/extension.js
EXPOSE 5000
ENV FLASK_APP=main.py
CMD ["python3", "main.py"]
