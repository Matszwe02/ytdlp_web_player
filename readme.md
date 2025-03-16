# Arbitraty internet video player powered by yt-dlp

## Features
- videojs usage to support custom video elements
- yt-dlp used for video download
- ffmpeg for better format selection
- implemented sponsorblock for supported sites (currently YouTube)
- PWA support with "share with" target for Android
- nice animations while loading video

**Daily auto update of yt-dlp and ffmpeg to immediately support new yt-dlp codecs and sites**

## Planned
- HLS support for shorter load times and livestream support
- video download option
- closed captions support
- video format selection (currently forced 720p)

## Images

![image](.github/images/image.png)
![loading screen](.github/images/image2.png)
![main page](.github/images/image3.png)


# Installation

```yml
services:
    ytdlp_web_player:
        # build: .
        image: matszwe02/ytdlp_web_player
        restart: unless-stopped
        environment:
            - APP_TITLE=YT-DLP Player
        ports:
            - 5000:5000

```