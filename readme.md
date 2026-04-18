<p align="center">
  <img src="src/static/favicon.svg" width="128px" />
</p>

# YT-DLP Web Player

### Internet video player powered by yt-dlp


<div align="center">

<br>

[![GitHub license](https://badgen.net/github/license/Matszwe02/ytdlp_web_player)](https://github.com/Matszwe02/ytdlp_web_player/blob/main/LICENSE)
[![GitHub commits](https://badgen.net/github/commits/Matszwe02/ytdlp_web_player)](https://GitHub.com/Matszwe02/ytdlp_web_player/commit/)
[![GitHub latest commit](https://badgen.net/github/last-commit/Matszwe02/ytdlp_web_player)](https://GitHub.com/Matszwe02/ytdlp_web_player/commit/)

[![GitHub stars](https://badgen.net/github/stars/Matszwe02/ytdlp_web_player)](https://GitHub.com/Matszwe02/ytdlp_web_player/stargazers/)
[![Docker Pulls](https://badgen.net/docker/pulls/matszwe02/ytdlp_web_player?icon=docker&label=pulls)](https://hub.docker.com/r/matszwe02/ytdlp_web_player/)
[![GitHub issues](https://img.shields.io/github/issues/Matszwe02/ytdlp_web_player.svg)](https://GitHub.com/Matszwe02/ytdlp_web_player/issues/)

</div>


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

**Daily auto update of yt-dlp to immediately support new yt-dlp codecs and sites**

## Technologies used
- HLS for shorter load times and better performance
- videojs to support custom video elements
- yt-dlp for video download
- ffmpeg for better format support
- sponsorblock for supported sites (currently YouTube)
- Media Session API integration for system playback controls
- Audio Context API for audio over-amplification and audio visualizer

## Planned
- more QoL features
- video quality changing without interrupts


## Limitations
- only YT-DLP supported videos work
- video loading times and fallbacks:
    - most videos load in less than 4 seconds, skipping transcoding until it starts ("Direct" in resolution seleciton)
    - if it fails, most of remaining videos load in ~10s, when transcoding starts
    - if it also fails, the whole video is getting downloaded until it becomes available
- all videos are being transcoded to HLS in realtime, so you need a machine that could handle that
    - transcoding works from start of the videos, so you need to wait for later parts to buffer. For now the only alternative is to switch to "Direct" in resolution selection
- project is under heavy development - you may expect bugs and issues



## Images

### Main Page
![image](.github/images/main.png)
### Vertical Video Support
![vertical](.github/images/vert.png)
### Obligatory Big Buck Bunny
![big buck bunny](.github/images/bbb.png)
### Browser Extension
![Extension](.github/images/ext.png)
### Phone App
![PWA](.github/images/app.png)


# How to run

### **There are no official public instances of this app due to anti-bot policies of popular video sharing platforms**

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

### Cookies

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
    - it sends your website's cookies to the server with each request, then tries to mark video as watched (if enabled)
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

## Star History

<a href="https://www.star-history.com/?repos=Matszwe02%2Fytdlp_web_player&type=date&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=Matszwe02/ytdlp_web_player&type=date&theme=dark&legend=top-left" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=Matszwe02/ytdlp_web_player&type=date&legend=top-left" />
   <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=Matszwe02/ytdlp_web_player&type=date&legend=top-left" />
 </picture>
</a>