<p align="center">
  <img src="src/static/favicon.svg" width="128px" />
</p>

# YT-DLP Web Player

### Internet video player powered by yt-dlp


<div align="center">

<br>

[![GitHub license](https://badgen.net/github/license/Matszwe02/ytdlp_web_player)](https://github.com/Matszwe02/ytdlp_web_player/blob/main/LICENSE)
[![GitHub commits](https://badgen.net/github/commits/Matszwe02/ytdlp_web_player)](https://GitHub.com/Matszwe02/ytdlp_web_player/commit/)

[![GitHub stars](https://badgen.net/github/stars/Matszwe02/ytdlp_web_player)](https://GitHub.com/Matszwe02/ytdlp_web_player/stargazers/)
[![Docker Pulls](https://badgen.net/docker/pulls/matszwe02/ytdlp_web_player?icon=docker&label=pulls)](https://hub.docker.com/r/matszwe02/ytdlp_web_player/)
[![GitHub issues](https://img.shields.io/github/issues/Matszwe02/ytdlp_web_player.svg)](https://GitHub.com/Matszwe02/ytdlp_web_player/issues/)

</div>


## Features
- **Daily auto update of yt-dlp to immediately support new yt-dlp codecs and sites**
- everything you would expect a modern player to have
- fast loading speed (most videos load in 3s)
- livestream support
- minimalistic UI, configurable theme color
- paste video URL / type search query / auto pasting from clipboard
- zoom to fill for all devices
- download, repeat videos
- optional music visualizer
- browser extension
- PWA


some of these features are off by default and need to be turned on in `.env`


<table align="center">
  <tr>
    <td align="center" valign="top" width="50%">
      <b>Main Page (PWA)</b><br>Paste URL, seach for a video or click enter - when input field is empty, it will auto-fill from clipboard
      <br><br><img src=".github/images/main.png" alt="Main Page" />
    </td>
    <td align="center" valign="top" width="50%">
      <b>Vertical Video Support</b><br>Player automatically adjusts its aspect ratio to each video, in fullscreen you can zoom to fill
      <br><br><img src=".github/images/vert.png" alt="Vertical Video Support" />
    </td>
  </tr>
  <tr>
    <td align="center" valign="top" width="50%">
      <b>Phone App</b><br>Installable as PWA app - native phone experience, opening links with "share with YT-DLP Player"
      <br><br><img src=".github/images/app.png" alt="Phone App" />
    </td>
    <td align="center" valign="top" width="50%">
      <b>Browser Extension</b><br>Replace all videos seamlessly - consistent UI across every website, no irritating autoplay
      <br><br><img src=".github/images/stream.png" alt="Browser Extension" />
    </td>
  </tr>
</table>


## Planned
- video quality changing without interrupts
- user-side player configuration


## Limitations
- only YT-DLP supported videos work
- video loading times and fallbacks:
    - most videos load in around 3 seconds
    - if it fails, transcoding starts and video loads in around 10s
    - if it also fails, the whole video is getting downloaded until it becomes available
- project is under heavy development - you may expect bugs and issues


## Technologies used
- yt-dlp as a video downloader
- videojs as a robust player
- HLS transcoding for the most reliable playback
- ffmpeg for better format support
- node / deno for solving YT-DLP's js challenges
- sponsorblock integration
- Media Session API integration for system playback controls
- Audio Context API for audio over-amplification and music visualizer


## How to run

App should be accessible at http://localhost:5000

### Docker
- `docker run -p 5000:5000 matszwe02/ytdlp_web_player:stable`
    - if you want stable version, ready for everyday use
- `docker run -p 5000:5000 matszwe02/ytdlp_web_player:latest`
    - if you want latest version - may have new and experimental features, it may also contain more bugs

OR

- Clone repo
- Copy `src/example.env` to `src/.env`, modify as needed
- Run `docker compose up`
- For automatic app updates, see `compose.yml`
- To enable HTTPS, see `compose.yml`
  - then you can access the HTTPS app with https://localhost:5001
  - your browser will warn you about not secure connection, you need to click on "allow"

### Run locally (Python)

- Copy `src/example.env` to `src/.env`, modify as needed
- Create and activate a virtual environment in `src/` and install `requirements.txt`
- optionally install `ffmpeg` and `node`/`deno`, otherwise they will be automatically installed to your venv
- run `main.py`


## Cookies

Some videos need cookies to work. With cookies you will be logged in to the video streaming's website while using the app.

- Create `src/cookies.txt` file and enable in `compose.yml` (if using docker)
- Paste relevant cookies into that file (I suggest using an extension for that, which exports cookies in netscape format)
    - yt-dlp created a nice [guide](https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp) about providing the cookies
- If using extension, you can enable automatic sending of browser cookies for individual videos in extension settings

**Keep in mind that cookies work the same way as your account credentails - anyone having them may [mess up your account](https://youtu.be/yGXaAWbzl5A).**
    
I do not guarantee that cookies file is completly secure from accessing it through the player. Additionally yt-dlp uses them when playing videos on behalf of the provided account. So I only recommend putting throwaway accounts here.


## Extension

YT-DLP Web Player provides an extension that replaces every video in allowed (in extension settings) domains with YT-DLP Player. That results with all of the default video players to be seamlessly replaced with YT-DLP Player

- This extension will disable all media playback on the website, disable native player and create YT-DLP Player's iframe in its place

There are 3 ways of running this extension:

### Browser Extension

Additionally adds `Open in YT-DLP Player` context menu for all links. So you can right-click any link and it is opened in YT-DLP Player directly

- Extension available in [Chrome Web Store](https://chromewebstore.google.com/detail/yt-dlp-web-player/gnpabpjkhecpnecnlljfjlbbcokccgbj) and [Firefox Add-ons](https://addons.mozilla.org/en-GB/firefox/addon/yt-dlp-web-player/)
    - alternatively, you can clone this repo and load it from `/extension` directory
- Put player's URL in extension settings
- In extension settings: enable/disable domains or start/stop temporarily

### Tampermonkey script

- Create a new script and copy extension js from player's dropdown menu (or `/extension/extension.js`)
- In script settings: enable/disable domains or start/stop temporarily
- For some websites you need to install one of `disable CSM` extensions

### Developer Tools script

It is a temporary solution, every page reload clears it
- copy extension js from player's dropdown menu (or `/extension/extension.js`) and paste into developer tools
- For some websites you need to install one of `disable CSM` extensions


## Demo, other use cases

### Demo server

Low performance and may be IP blacklisted due to this server's limitations

https://ytdlp-web-player.vercel.app

### Proof-of-Concept YT-DLP Web Player inside Invidious

https://hub.docker.com/r/matszwe02/invidious_ytdlp_web_player

### Sharing

This player fully supports `Open Graph` - sharing it through social media and messaging apps shows video's title, thumbnail, and allows for direct playback

### Embedding player

If you want to embed this player, use `/iframe?url=...` endpoint


## Troubleshooting

### I can't install PWA / embed it as an iframe / extension does not load

You need a working HTTPS for this, see in [How to run](#how-to-run). Some features will work when you run through HTTP from localhost, but it may not work properly.

### I can't play some videos

Please check if it's supported by yt-dlp [here](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md).

Also check [yt-dlp's issues](https://github.com/yt-dlp/yt-dlp/issues).

You can even try to download yt-dlp and download that video with it, to ensure there is a way to download it.

If it appears to be supported, fill in a bug report with app logs.

### Can this app do XYZ?

This readme does not mention every configuration option. See `example.env` and check if the feature you want is already settable. If not, I'm open for feature requests.

### Other issues

Please fill in a bug report. Attach browser and app logs if relevant, app version, browser name, etc.

## Star History

<a href="https://www.star-history.com/?repos=Matszwe02%2Fytdlp_web_player&type=date&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=Matszwe02/ytdlp_web_player&type=date&theme=dark&legend=top-left" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=Matszwe02/ytdlp_web_player&type=date&legend=top-left" />
   <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=Matszwe02/ytdlp_web_player&type=date&legend=top-left" />
 </picture>
</a>