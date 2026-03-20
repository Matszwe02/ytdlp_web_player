<p align="center">
  <img src="src/static/favicon.svg" width="128px" />
</p>

# YT-DLP Web Player

### Arbitraty internet video player powered by yt-dlp

## Features
- video resolution selection, closed captions selection, video aspect ratio adjustement
- video download option, video repeat option
- PWA support with "share with" target for Android
- video searching
- clean UI, configurable themes
- browser extension to allow including this player everywhere (experimental)
  - note that this extension in the current version is vibe-coded (I do not guarantee that no LLMs were harmed in the process)
  - uses player embedding using `/iframe` endpoint


## Technologies used
- HLS for shorter load times and better performance
- videojs to support custom video elements
- yt-dlp for video download
- ffmpeg for better format support
- sponsorblock for supported sites (currently YouTube)
- Media Session API integration for system playback controls


**Daily auto update of yt-dlp to immediately support new yt-dlp codecs and sites**

## Planned
- livestream support
- more QoL features
- video quality changing without interrupts

## Images

![image](.github/images/image.png)
![loading screen](.github/images/image2.png)
![main page - PWA](.github/images/image3.png)
![vertical](.github/images/image4.png)


# How to run

### **There are no official instances of this app due to anti-bot policies of popular video sharing platforms**

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