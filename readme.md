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
- For automatic app updates, see `compose.yml`
- To enable HTTPS, see `compose.yml`
  - then you can access the app with `https://localhost:5001`
  - your browser will warn you about not secure connection, you need to click on allow

## 2. Run locally

- Create and activate a virtual environment in `src/` and install `requirements.txt`
- Install and ensure you have `ffmpeg` in PATH (typing `ffmpeg` in console should display ffmpeg info)
  - Install and ensure you have `deno` or `node` in PATH (optional)
- run with `python3 main.py`


## Configure

- Copy `src/example.env` to `src/.env`, modify as needed
- If you want to add your own cookies, create `src/cookies.txt` file and enable in `compose.yml` if using docker
    - Keep in mind that cookies work the same way as your account credentails - anyone having them may [mess up your account](https://youtu.be/yGXaAWbzl5A).\
    So I only recommend putting throwaway accounts here.\
    Extension in current version also sends your cookies to the server, but they are deleted when video is cleaned up.


# Troubleshooting

## I can't install PWA / embed it as an iframe / extension does not load

You need HTTPS for this, see [Docker section](#1-docker-preferred)

## I can't play some videos

Please check if it's supported by yt-dlp [here](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md).

Also check [yt-dlp's issues](https://github.com/yt-dlp/yt-dlp/issues).

If it appears to be supported, fill in a bug report with app logs.

## Other issues

Please fill in a bug report. Attach browser and app logs if relevant.