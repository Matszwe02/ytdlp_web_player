FROM python:3.13-alpine AS builder
# RUN apt-get update && apt-get install -y git
RUN apk add --no-cache git
RUN pip install GitPython
WORKDIR /build
COPY . /build/
RUN python version.py


FROM python:3.13-alpine

RUN apk add --no-cache ffmpeg
WORKDIR /app
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir gunicorn
COPY --from=builder /build/version.txt /app/
COPY . /app
EXPOSE 5000
ENV FLASK_APP=main.py
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--threads", "4", "--timeout", "900", "--graceful-timeout", "600", "main:app"]