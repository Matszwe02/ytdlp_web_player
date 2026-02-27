<p align="center">
  <img src="static/favicon.png" />
</p>

# YT-DLP Web Player

### Arbitraty internet video player powered by yt-dlp

## Features
- videojs usage to support custom video elements
- yt-dlp used for video download
- ffmpeg for better format support
- implemented sponsorblock for supported sites (currently YouTube)
- PWA support with "share with" target for Android
- Media Session API integration for system playback controls
- video download option
- video format selection
- closed captions support
- HLS support for shorter load times and better performance (experimental)
- Player embedding using `/iframe` endpoint (experimental)
- video searching functionality
- nice animations while loading video
- configurable themes

**Daily auto update of yt-dlp to immediately support new yt-dlp codecs and sites**

## Planned
- livestream support
- more QoL features
- video quality changing without interrupts

## Images

![image](.github/images/image.png)
![loading screen](.github/images/image2.png)
![main page](.github/images/image3.png)
![vertical](.github/images/image4.png)


# How to run

App should be accessible at [http://localhost:5000](http://localhost:5000)

## 1. Docker (preferred)

- Run
  ```sh
  docker compose up
  ```
- Modify `compose.yml`'s environment variables as needed
- For automatic app updates, see `compose.yml`

## 2. Run locally

- Create and activate a virtual environment and install `requirements.txt`
- Copy `example.env` to `.env`, modify as needed
- Ensure you have `ffmpeg` in PATH (typing `ffmpeg` in console should display ffmpeg info)
- run with `python3 main.py`


# Troubleshooting

## I can't install PWA / application

You need HTTPS for this. You'll need to set up a proxy for that. A good temporary solution is to set up a vscode dev tunnel for port `5000`, which generates a temporary HTTPS link for your app.

## I can't embed it as an iframe

You also need HTTPS for this.

## I can't play some videos

Please check if it's supported by yt-dlp [here](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md).

Also check [yt-dlp's issues](https://github.com/yt-dlp/yt-dlp/issues).

If it appears to be supported, fill in a bug report with app logs.

## Other issues

Please fill in a bug report. Attach browser and app logs if relevant.