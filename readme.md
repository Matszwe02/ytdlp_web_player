<p align="center">
  <img src="src/static/favicon.svg" width="128px" />
</p>

# YT-DLP Web Player

### Internet video player powered by yt-dlp

## Features
- everything you would expect a modern player to have
- fast loading speed (most videos load within 4s)
- paste video URL / type search query / auto pasting from clipboard
- zoom to fill for all devices
- download, repeat videos
- audio visualizer for music
- PWA support with "share with" target for Android and IOS
- clean UI, configurable theme color
- basic livestream support
- browser extension to allow including this player on every website, which also adds `Open link in YT-DLP Player` browser-wide context menu

some of these features are off by default and need to be turned on in `.env`


## Technologies used
- HLS for shorter load times and better performance
- videojs to support custom video elements
- yt-dlp for video download
- ffmpeg for better format support
- sponsorblock for supported sites (currently YouTube)
- Media Session API integration for system playback controls
- Audio Context API for audio over-amplification and audio visualizer


**Daily auto update of yt-dlp to immediately support new yt-dlp codecs and sites**

## Planned
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
- See `compose.yml` for additional configuration mentioned in [Docker section](#1-docker-preferred)

### Cookies (optional)
---

Some videos need cookies to work. With cookies you will be logged in to the video streaming's website while using the app.

- Create `src/cookies.txt` file and enable in `compose.yml` (if using docker)
- Paste relevant cookies into that file (I suggest using an extension for that, which exports cookies in netscape format)
    - yt-dlp created a nice [guide](https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp) about providing the cookies

**Keep in mind that cookies work the same way as your account credentails - anyone having them may [mess up your account](https://youtu.be/yGXaAWbzl5A).**
    
I do not guarantee that cookies file is completly secure from accessing it through the player. Additionally yt-dlp uses them when playing videos on behalf of the provided account. So I only recommend putting throwaway accounts here.


## Browser Extension

### Installation

- You can install the extension by downloading repo and selecting `/extension` path to import into browser's extensions
- Alternatively you can load `/extension/extension.js` with tampermonkey, or paste it into dev tool console
    - For some websites you need to have one of `disable CSM` extensions

### Working principle

- This extension will disable all media playback on selected websites
    - it's by design, so keep in mind that no playback will be possible while the extension is active
- It will spawn iframe directly in `<body>` and search for the best container to hover that iframe above it
    - it is designed like that so DOM won't be significantly altered
    - it sends your website's cookies to the server with each request, then tries to mark video as watched
- That container gets opacity:0 and pointer-events:none so it can't be interacted with
- It will watch for any change to update iframe's position or container


# Troubleshooting

## I can't install PWA / embed it as an iframe / extension does not load

You need HTTPS for this, see [Docker section](#1-docker-preferred)

## I can't play some videos

Please check if it's supported by yt-dlp [here](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md).

Also check [yt-dlp's issues](https://github.com/yt-dlp/yt-dlp/issues).

If it appears to be supported, fill in a bug report with app logs.

## Other issues

Please fill in a bug report. Attach browser and app logs if relevant, app version, browser name, etc.