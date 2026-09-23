ARG FFMPEG_VERSION=7.1.1
ARG NV_CODEC_HEADERS_VERSION=n12.2.72.0

FROM python:3.13-alpine AS ffmpeg-builder
ARG FFMPEG_VERSION
ARG NV_CODEC_HEADERS_VERSION

RUN apk add --no-cache \
        build-base \
        git \
        nasm \
        openssl-dev \
        pkgconf \
        x264-dev \
        zlib-dev

WORKDIR /build
RUN git clone --depth 1 --branch "${NV_CODEC_HEADERS_VERSION}" https://github.com/FFmpeg/nv-codec-headers.git \
    && make -C nv-codec-headers install PREFIX=/opt/ffmpeg \
    && git clone --depth 1 --branch "n${FFMPEG_VERSION}" https://github.com/FFmpeg/FFmpeg.git ffmpeg

WORKDIR /build/ffmpeg
RUN PKG_CONFIG_PATH=/opt/ffmpeg/lib/pkgconfig ./configure \
        --prefix=/opt/ffmpeg \
        --disable-debug \
        --disable-doc \
        --disable-ffplay \
        --disable-ffprobe \
        --disable-shared \
        --enable-static \
        --enable-gpl \
        --enable-libx264 \
        --enable-nonfree \
        --enable-nvenc \
        --enable-openssl \
    && make -j"$(getconf _NPROCESSORS_ONLN)" \
    && make install \
    && /opt/ffmpeg/bin/ffmpeg -hide_banner -encoders | grep -q h264_nvenc


FROM python:3.13-alpine AS version-builder
RUN apk add --no-cache git \
    && pip install --no-cache-dir GitPython
WORKDIR /build
COPY . /build/
RUN python src/version.py


FROM python:3.13-alpine

RUN apk add --no-cache deno openssl x264-libs
WORKDIR /app
COPY src/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY --from=ffmpeg-builder /opt/ffmpeg/bin/ffmpeg /app/ffmpeg
COPY --from=version-builder /build/version.txt /app/
COPY src/. /app
COPY extension/extension.js /app/static/extension.js
EXPOSE 5000
ENV FLASK_APP=main.py
CMD ["python3", "main.py"]
