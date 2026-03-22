FROM python:3.13-alpine AS builder
# RUN apt-get update && apt-get install -y git
RUN apk add --no-cache git
RUN pip install GitPython
WORKDIR /build
COPY . /build/
RUN python src/version.py


FROM python:3.13-alpine

RUN apk add --no-cache ffmpeg
WORKDIR /app
COPY src/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir gunicorn
COPY --from=builder /build/version.txt /app/
COPY src/. /app
EXPOSE 5000
ENV FLASK_APP=main.py
CMD ["python3", "main.py"]