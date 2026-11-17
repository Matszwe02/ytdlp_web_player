let player;
let audioPlayer;
let playerEl;
let container;
let skipSegment;
let skipTime = 0;
let info = null;
let activeFetches = 0; // Counter for active retryFetch calls
let repeatMode = false;
let repeatRange = [null, null];
let minBufferAheadTime = 0;
let audioContext = null;
let audioSource = null;
let gainNode = null;
let currentVideoSourceIndex = 0;
let currentAudioSourceIndex = 0;
let logHistory = [];
let holdAudio = false;
let sprite = null;
let segments = [];
let freezeFrame = () => {};


const sbColorMap = {
    'selfpromo': '#ffff00',
    'outro': '#0000ff',
    'sponsor': '#00ff00',
    'preview': '#0077ff',
    'interaction': '#ff00ff',
    'intro': '#00ffff',
    'poi_highlight': '#ef4c9b',
    'music_offtopic': '#ff9900',
};


const PlayerModes = {
    /** Only `player` active, playing video */
    VIDEO: 0,
    /** Both `player` and `audioPlayer` active */
    VIDEO_AUDIO: 1,
    /** Only `player` active, playing audio */
    AUDIO: 2,
}

let playerMode = PlayerModes.VIDEO;


class PlayerState
{
    constructor()
    {
        this.ongoing = false;
        this.switchTime = 0;
        this.isPlaying = false;
        this.speed = 1;
    }
    save()
    {
        if (this.ongoing && player.currentTime == 0)
        {
            warn('Preventing saving unknown player state');
            return;
        }
        this.ongoing = false;
        this.linked = playerMode == PlayerModes.VIDEO_AUDIO && parseFloat(info.duration) != 0;
        this.switchTime = player.currentTime;
        this.isPlaying = !player.paused;
        this.speed = player.playbackRate;
    }
    apply()
    {
        player.addEventListener('loadedmetadata', () => {
            if (!this.linked || playerMode != PlayerModes.VIDEO_AUDIO)
            {
                if (this.switchTime > 0) player.currentTime = this.switchTime;
                if (this.isPlaying) player.play();
            }
            player.playbackRate = this.speed;
        }, { once: true });
        this.ongoing = true;
    }
}

let ps = new PlayerState();


function log(text)
{
    console.log(text);
    logHistory.push(`LOG  | ${text}`);
    if (logHistory.length > 100) logHistory.splice(0, logHistory.length - 100);
}

function warn(text)
{
    console.warn(text);
    logHistory.push(`WARN | ${text}`);
    if (logHistory.length > 100) logHistory.splice(0, logHistory.length - 100);
}

function err(text)
{
    console.error(text);
    logHistory.push(`ERR  | ${text}`);
    if (logHistory.length > 100) logHistory.splice(0, logHistory.length - 100);
}


function releaseAudio()
{
    if (!holdAudio) return;
    holdAudio = false;
    audioPlayer.play();
}


function videoHidden()
{
    return document.hidden && 'pictureInPictureEnabled' in document && !document.pictureInPictureElement;
}


function bufferedEnd(media)
{
    return media.buffered.length ? media.buffered.end(media.buffered.length - 1) : 0;
}


function syncVideo(jump = false)
{
    if (playerMode != PlayerModes.VIDEO_AUDIO) return;
    if (videoHidden()) return releaseAudio();

    const video = player.target;
    const playing = !audioPlayer.paused || holdAudio;
    const offset = video.currentTime - audioPlayer.currentTime;

    if (video.readyState >= HTMLMediaElement.HAVE_METADATA)
    {
        if (Math.abs(offset) > (jump || !playing ? 0.02 : 5))
        {
            if (!jump && playing && offset < 0 && (video.seeking || video.readyState < HTMLMediaElement.HAVE_FUTURE_DATA))
            {
                warn(`Audio paused: video player can't keep up`);
                holdAudio = true;
                audioPlayer.pause();
            }
            video.currentTime = audioPlayer.currentTime;
            log(`Video synced to audio. Offset: ${offset.toFixed(3)}s`);
        }
        else if (Math.abs(offset) > 0.02)
        {
            const buffer = Math.max(1.1, (bufferedEnd(video) - video.currentTime));
            video.playbackRate = Math.min(buffer, 4, Math.max(0.1, audioPlayer.playbackRate * 2 ** (-offset)));
        }
        else video.playbackRate = audioPlayer.playbackRate;
    }

    if (playing && video.paused && !video.ended) video.play().catch(() => {});
    if (!playing && !video.paused) video.pause();
}


function setupPlayerSync()
{
    const linked = {
        play: { value: () => audioPlayer.play() },
        pause: { value: () => { holdAudio = false; audioPlayer.pause(); syncVideo(); } },
        paused: { get: () => audioPlayer.paused && !holdAudio },
        currentTime: { get: () => audioPlayer.currentTime, set: (time) => { audioPlayer.currentTime = time; } },
        playbackRate: { get: () => audioPlayer.playbackRate, set: (rate) => { audioPlayer.playbackRate = rate; } },
    };
    for (const name in linked)
    {
        let own;
        for (let proto = player; proto && !own; proto = Object.getPrototypeOf(proto)) own = Object.getOwnPropertyDescriptor(proto, name);
        const route = (key) => [key, (...args) => (playerMode == PlayerModes.VIDEO_AUDIO ? linked[name] : own)[key].apply(player, args)];
        Object.defineProperty(player, name, { configurable: true, enumerable: true, ...Object.fromEntries(Object.keys(linked[name]).map(route)) });
    }

    ['play', 'pause', 'ratechange', 'timeupdate'].forEach(type => audioPlayer.addEventListener(type, () => syncVideo()));
    audioPlayer.addEventListener('seeking', () => syncVideo(true));
    player.addEventListener('loadedmetadata', () => syncVideo(true));
    ['seeked', 'playing'].forEach(type => player.addEventListener(type, () => {
        if (player.target.readyState >= HTMLMediaElement.HAVE_FUTURE_DATA) releaseAudio();
    }));

    let suspended = false;
    let pipTime = 0;
    ['play', 'pause'].forEach(type => player.addEventListener(type, () => {
        if (playerMode != PlayerModes.VIDEO_AUDIO) return;
        const video = player.target;
        const wasSuspended = suspended;
        const inPip = !!document.pictureInPictureElement;
        suspended = videoHidden() && video.paused;
        if (video.paused == player.paused || videoHidden()) return;
        if (wasSuspended || video.ended || (!inPip && Date.now() - pipTime < 200)) return syncVideo();
        if (inPip && video.paused) pipTime = Date.now();
        video.paused ? player.pause() : player.play();
    }));

    player.addEventListener('leavepictureinpicture', () => {
        if (Date.now() - pipTime < 200) player.play();
        pipTime = Date.now();
    });

    player.addEventListener('volumechange', () => {
        audioPlayer.muted = player.muted;
        audioPlayer.volume = player.volume;
    });
}


function setupSeekPreview()
{
    const video = player.target;
    const c = Object.assign(document.createElement('canvas'), { className: 'seek-preview', hidden: true });
    player.after(c);
    let shownAt = 0;
    const show = (time, image, width, height, ...crop) => {
        if (playerMode == PlayerModes.AUDIO) return;
        [c.width, c.height, c.hidden, shownAt] = [width, height, false, time];
        c.getContext('2d').drawImage(image, ...crop, 0, 0, width, height);
    };
    const ready = () => !video.seeking && video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA;
    const hide = () => ready() && (c.hidden = true);
    freezeFrame = () => c.hidden && show(video.currentTime, (video.videoWidth ? video : container.querySelector('.media-poster-image')), info.width, info.height);
    player.addEventListener('timeupdate', () => c.hidden && ready() && (shownAt = video.currentTime));
    ['seeked', 'canplay'].forEach(type => player.addEventListener(type, () => setTimeout(hide, video.requestVideoFrameCallback?.(hide) ? 1000 : 0)));
    player.addEventListener('seeking', () => {
        const time = video.currentTime, [width, height, columns, interval] = info.sprite, i = Math.floor(time / interval);
        if (sprite && Math.abs(time - shownAt) >= interval) show(time, sprite, width, height, i % columns * width, Math.floor(i / columns) * height, width, height);
    });
}


function setUpAudioContext()
{
    if (audioContext == null)
    {
        log(`Setting up AudioContext`);
        audioContext = new (window.AudioContext || window.webkitAudioContext)();
        if (playerMode == PlayerModes.VIDEO_AUDIO)
            audioSource = audioContext.createMediaElementSource(audioPlayer.target);
        else
            audioSource = audioContext.createMediaElementSource(player.target);
        audioSource.connect(audioContext.destination);
    }
}


function setOverAmplification(enabled)
{
    if (gainNode === null)
    {
        setUpAudioContext();
        gainNode = new GainNode(audioContext);
        audioSource.disconnect(audioContext.destination);
        audioSource.connect(gainNode).connect(audioContext.destination);
    }
    gainNode.gain.value = enabled ? 2 : 1;
}


function addFetch()
{
    activeFetches += 1;
    log(activeFetches);
    document.getElementById('settings-trigger')?.classList.toggle('fetching', activeFetches > 0);
}


function removeFetch()
{
    activeFetches -= 1;
    log(activeFetches);
    document.getElementById('settings-trigger')?.classList.toggle('fetching', activeFetches > 0);
}


async function retryFetch(url, options = {}, retries = 5, delay = 5000, visible = true, head = false)
{
    if (visible) addFetch();
    try
    {
        const fetchOptions = { method: (head ? 'HEAD' : 'GET'), ...options };
        if (player != null)
        {
            const response = await fetch(url, fetchOptions);
            if (response.status == 500) throw new Error(`Server error: ${await response.text()}`);
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            return response;
        }
    }
    catch (error)
    {
        if (error.name === 'AbortError')
        {
            log(`Fetch for "${url}" aborted.`);
            throw error;
        }
        if (error.message.startsWith('Server error:'))
        {
            throw error;
        }
        err(`Fetch failed, retrying in ${delay / 1000} seconds... ${error}`);
        if (retries > 0)
        {
            await new Promise(resolve => setTimeout(resolve, delay));
            return retryFetch(url, options, retries - 1, delay, visible, head);
        }
        else
        {
            err(`Max retries reached for "${url}". Fetch failed.`);
            throw error;
        }
    }
    finally
    {
        if (visible) removeFetch();
    }
}


function getUrlInfo()
{
    const urlParams = new URLSearchParams(window.location.search);
    const originalUrl = urlParams.get('v') || urlParams.get('url');
    const encodedUrl = encodeURIComponent(originalUrl);
    let startTime = null;
    try {startTime = parseFloat((urlParams.get('t') || (new URL(originalUrl)).searchParams.get('t')).replaceAll('s', ''))}
    catch {}
    var quality = urlParams.get('quality');
    if (quality == '') quality = null;
    if (quality == 'null') quality = null;
    if (info)
    {
        if (quality == null) quality = `${info.default_quality}`;;
        if (info['height'] == null && info['width'] == null) quality = 'audio';
    }
    if (quality && quality !== 'audio') quality = quality.replace('audio', '');
    return { quality: quality, originalUrl: originalUrl, encodedUrl:encodedUrl, urlParams:urlParams, startTime: startTime };
}


function getVideoSource()
{
    var url = getUrlInfo();
    playerMode = url.quality === 'audio' ? PlayerModes.AUDIO : PlayerModes.VIDEO_AUDIO;
    let sources = info.sources[url.quality];
    if (!sources)
    {
        sources = info.sources[url.quality + 'audio'];
        if (url.quality !== 'audio') playerMode = PlayerModes.VIDEO;
    }
    if (!sources)
    {
        sources = [];
    }
    let best = sources[currentVideoSourceIndex];
    if (best) return best;
    if (url.quality !== 'audio') playerMode = PlayerModes.VIDEO;
    return [`/hls?url=${url.encodedUrl}&quality=${url.quality}`, 'h264', 'application/x-mpegURL', false];
}


function getAudioSource()
{
    var url = getUrlInfo();
    let a = (info.sources['audio'] || [])[currentAudioSourceIndex];
    if (a) return a;
    return [`/hls?url=${url.encodedUrl}&quality=audio`, 'aac', 'application/x-mpegURL', false];
}


function formatTime(timeInSeconds, decimals = 0, short = false)
{
    if (timeInSeconds === null || isNaN(timeInSeconds)) return '-';
    const out = new Date(timeInSeconds * 1000).toISOString().substring(11, decimals ? 20 + decimals : 19);
    return short ? out.replace(/^00:/, '').replace(/^0/, '') : out;
}


function updatePlaybackTime(newTime = null)
{
    const url = new URL(window.location.href);
    if (newTime === null) newTime = player.currentTime;
    if (newTime > 2 && newTime < info.duration - 2)
    {
        url.searchParams.set('t', Math.floor(newTime));
        window.history.replaceState({}, '', url);
    }
}


var prevRotation = 0;
function fullscreenOnRotate()
{
    const screenAspect = (screen.height / screen.width);
    const videoAspect = ((player.videoHeight || 480) / (player.videoWidth || 720));
    const aspectDiff = Math.abs(videoAspect - screenAspect) - Math.abs((1/videoAspect) - screenAspect);
    if (aspectDiff < -0.3 && !playerEl.store.isFullscreen)
    {
        playerEl.store.requestFullscreen().catch(() => {});
    }
    else if (aspectDiff > 0.3 && playerEl.store.isFullscreen)
    {
        playerEl.store.exitFullscreen().catch(() => {});
    }
}
screen.orientation?.addEventListener("change", (event) => {
    fullscreenOnRotate();
});


function displayPlayerError(message)
{
    err(message);
    if (audioPlayer) try { audioPlayer.pause(); } catch (error) {}
    if (!player) return;
    const errorDisplay = container.querySelector('.app-message');
    errorDisplay.innerHTML = '<i class="fa-solid fa-circle-exclamation error-icon"></i><div></div>';
    errorDisplay.lastChild.textContent = message;
    errorDisplay.hidden = false;
    container.classList.remove('loading');
    player.source = null;
    player = null;
}


function addCues(kind, label, cues)
{
    playerEl.store.addTextTrack({ kind, label, cues });
}


function addTrack(attributes)
{
    const track = document.createElement('track');
    Object.assign(track, attributes);
    player.appendChild(track);
}


function setUpSubtitleDisplay()
{
    const hideNative = new CSSStyleSheet();
    hideNative.replaceSync('video::-webkit-media-text-track-container { display: none !important; } video::cue { visibility: hidden; }');
    player.shadowRoot.adoptedStyleSheets.push(hideNative);

    const overlay = Object.assign(document.createElement('div'), { className: 'subtitle-overlay' });
    container.append(overlay);
    let lines = new Map();
    const render = () => {
        const track = [...player.textTracks].find(track => track.kind == 'subtitles' && track.mode == 'showing');
        if (track) track.oncuechange = render;
        const bottoms = new Map([...lines].map(([cue, line]) => [cue, line.getBoundingClientRect().bottom]));
        lines = new Map([...(track?.activeCues || [])].map(cue => [cue, document.createElement('div')]));
        overlay.replaceChildren(...lines.values());
        lines.forEach((line, cue) => line.append(cue.getCueAsHTML()));
        lines.forEach((line, cue) => {
            line.animate(bottoms.has(cue) ? { transform: [`translateY(${bottoms.get(cue) - line.getBoundingClientRect().bottom}px)`, 'none'] } : { opacity: [0, 1] }, 200);
        });
    };
    player.textTracks.addEventListener('change', render);
}


function loadSubtitles(subtitleList)
{
    if (!subtitleList || subtitleList.length === 0) return;
    var url = getUrlInfo();
    setUpSubtitleDisplay();
    [...subtitleList].sort().forEach(lang => addTrack({ kind: 'subtitles', srclang: lang, label: lang, id: lang }));
    player.textTracks.addEventListener('change', () => {
        const enabled = [...player.target.querySelectorAll('track[kind="subtitles"]:not([src])')].filter(el => el.track.mode != 'disabled');
        const showing = enabled.filter(el => el.track.mode == 'showing');
        (showing.length ? showing : enabled.length == 1 ? enabled : []).forEach(el => {
            el.src = `/subtitle?url=${url.encodedUrl}&lang=${encodeURIComponent(el.srclang)}`;
        });
    });
}


function setAudioSource(reload = false)
{
    let audioSource = getAudioSource();
    if (!audioPlayer || !audioSource) return;
    if (reload || audioPlayer.source?.src !== audioSource[0])
    {
        audioPlayer.source = { src: audioSource[0], type: audioSource[2] };
    }
    audioPlayer.muted = player.muted;
    audioPlayer.volume = player.volume;
}


function stopAudioPlayer()
{
    if (!audioPlayer) return;
    holdAudio = false;
    try
    {
        if (!audioPlayer.paused) audioPlayer.pause();
    }
    catch (error) {}
}


function setVideoSource(videoSource, reload = false)
{
    if (!reload && player.source?.src === videoSource[0])
    {
        log('Preventing switching to the same source');
        return;
    }
    freezeFrame();
    player.source = { src: videoSource[0], type: videoSource[2] };
    ps.apply();

    const audio = playerMode == PlayerModes.AUDIO;
    container.classList.toggle('audio-mode', audio);
    if (info.audio_visualizer) audio ? enableVisualizer(player) : disableVisualizer(player);
}


function qualityValue(quality)
{
    const bare = (value) => value === 'audio' ? value : value.replace('audio', '');
    const values = [...document.querySelectorAll('#quality-group > [value]')].map(item => item.getAttribute('value'));
    return values.find(value => bare(value) === bare(quality)) ?? quality;
}


function setVideoQuality(height = null)
{
    var url = getUrlInfo();
    if (height === null) height = `${url.quality}`;
    log(`Setting video quality to ${height}`);
    url.urlParams.set('quality', (height && height !== 'audio') ? height.replace('audio', '') : height);
    history.replaceState(null, '', `${window.location.pathname}?${url.urlParams.toString()}`);
    document.getElementById('quality-group').value = qualityValue(height);

    currentVideoSourceIndex = 0;
    applyVideoQuality();
}


function applyVideoQuality(reload = false)
{
    ps.save();

    const videoSource = getVideoSource();
    const reloadLive = parseFloat(info.duration) == 0 && (reload || player.source?.src != videoSource[0]);
    if (playerMode == PlayerModes.VIDEO_AUDIO) setAudioSource(reloadLive);
    else stopAudioPlayer();

    log(`Applying video source ${currentVideoSourceIndex}, separate audio player: ${playerMode == PlayerModes.VIDEO_AUDIO}`);

    setVideoSource(videoSource, reloadLive);
}


function advanceVideoSource()
{
    var url = getUrlInfo();
    const currentQuality = url.quality || info.default_quality;
    const sources = info.sources[url.quality] || [];
    currentVideoSourceIndex ++;
    const availableSources = sources.length + (info.disable_transcoding ? 0 : 1);
    if (currentVideoSourceIndex >= availableSources)
    {
        currentVideoSourceIndex = 0;
    }
    log(`Changing to video source ${currentVideoSourceIndex} / ${availableSources} of quality ${currentQuality}`);
    applyVideoQuality();
}


function advanceAudioSource()
{
    const sources = info.sources['audio'] || [];
    currentAudioSourceIndex ++;
    const availableSources = sources.length + (info.disable_transcoding ? 0 : 1);
    if (currentAudioSourceIndex >= availableSources)
    {
        currentAudioSourceIndex = 0;
    }
    log(`Changing to audio source ${currentAudioSourceIndex} / ${availableSources}`);
    if (parseFloat(info.duration) == 0) applyVideoQuality(true);
    else setAudioSource();
}


function setUpResolutionMenu()
{
    let resolutions = Object.keys(info.sources);
    if (resolutions.length < 1) return;
    const resolutionSet = new Set(resolutions);

    resolutions = resolutions.filter((resolution) => {
        if (resolution === 'audio') return false;
        const isAudio = resolution.endsWith('audio');
        const res = resolution.replace(/audio$/, '');
        return !isAudio || !resolutionSet.has(res);
    });
    resolutions.sort((a, b) => (parseInt(b.replace(/\D/g, ''), 10) || 0) - (parseInt(a.replace(/\D/g, ''), 10) || 0));
    resolutions.push('audio');

    const group = document.getElementById('quality-group');
    group.replaceChildren(...resolutions.map(height => {
        const item = document.getElementById('radio-item').content.firstElementChild.cloneNode(true);
        item.setAttribute('value', height);
        item.querySelector('[data-part="label"]').textContent = height === 'audio' ? 'Audio' : `${height.replace(/\D/g, "")}p`;
        return item;
    }));
    group.addEventListener('value-change', () => {
        if (group.value && qualityValue(group.value) != qualityValue(getUrlInfo().quality)) setVideoQuality(group.value);
    });
}


// TODO: Universal time range selection: Share between RepeatButton and DownloadButton, draggable markers on seekbar
function setUpRangeItems(range, ...ids)
{
    const items = ids.map(id => document.getElementById(id));
    const updateTimeLabels = () => items.forEach((item, i) => item.querySelector('.time_disp').textContent = formatTime(range[i], 1));
    items.forEach((item, i) => item.addEventListener('select', (event) => {
        event.preventDefault();
        range[i] = player.currentTime;
        updateTimeLabels();
    }));
    updateTimeLabels();
    return updateTimeLabels;
}


function setUpRepeatMenu()
{
    const repeatToggle = document.getElementById('loop-toggle');
    const updateTimeLabels = setUpRangeItems(repeatRange, 'range-start', 'range-end');

    repeatToggle.addEventListener('checked-change', () => {
        repeatMode = repeatToggle.checked;
        if (repeatMode)
        {
            repeatRange[0] = repeatRange[1] = null;
            updateTimeLabels();
        }
    });
}


function downloadFile(href, filetype)
{
    const link = document.createElement('a');
    link.href = href;
    link.download = 'file';
    retryFetch(href, {}, 100, undefined, true, true).then(response => {
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    }).catch(error => { err(`Could not download ${filetype}: ${error.message || error}`); });
}


function setUpDownloadMenu()
{
    const trim = document.getElementById('download-trim');
    const range = [null, null];
    const updateTimeLabels = setUpRangeItems(range, 'download-start', 'download-end');

    trim.addEventListener('checked-change', () => {
        document.querySelectorAll('#download-start, #download-end').forEach(item => item.hidden = !trim.checked);
        if (trim.checked)
        {
            range[0] = range[1] = null;
            updateTimeLabels();
        }
    });

    document.querySelectorAll('[data-download]').forEach(item => item.addEventListener('select', () => {
        var url = getUrlInfo();
        const currentQuality = url.quality || info.default_quality;
        const option = item.dataset.download;
        if (option == 'picture')
        {
            downloadFile(`/picture?url=${url.encodedUrl}&quality=${currentQuality}&start=${player.currentTime}`, 'picture');
            return;
        }
        let href = `/download?url=${url.encodedUrl}&quality=${option == 'current' ? currentQuality : option}`;
        if (range[0] != null || range[1] != null)
            href += `&start=${range[0] ? range[0].toFixed(1) : ''}&end=${range[1] ? range[1].toFixed(1) : ''}`;
        downloadFile(href, 'video');
    }));
}


let indicatorTimer = null;
const indicatorObserver = new MutationObserver(records => records.some(record => record.target.hasAttribute('data-open')) && hideIndicator());

function showIndicator(icon, label, persistent = false)
{
    const indicator = document.getElementById('app-indicator');
    container.querySelectorAll('.media-indicator:not(#app-indicator)').forEach(other => {
        other.core?.close();
        indicatorObserver.observe(other, { attributeFilter: ['data-open'] });
    });
    indicator.querySelector('.app-indicator-icon').innerHTML = `<i class="fa-solid ${icon}"></i>`;
    indicator.querySelector('.app-indicator-value').textContent = label;
    clearTimeout(indicatorTimer);
    if (indicator.hidden || indicator.hasAttribute('data-ending-style'))
    {
        indicator.hidden = false;
        indicator.removeAttribute('data-ending-style');
        indicator.setAttribute('data-starting-style', '');
        requestAnimationFrame(() => requestAnimationFrame(() => indicator.removeAttribute('data-starting-style')));
    }
    if (!persistent) indicatorTimer = setTimeout(hideIndicator, 800);
}
        
function hideIndicator()
{
    const indicator = document.getElementById('app-indicator');
    clearTimeout(indicatorTimer);
    if (indicator.hidden || indicator.hasAttribute('data-ending-style')) return;
    indicator.setAttribute('data-ending-style', '');
    indicatorTimer = setTimeout(() => { indicator.hidden = true; indicator.removeAttribute('data-ending-style'); }, 300);
}


function setUpVideoGestures()
{
    const DOUBLETAP_WINDOW = 200;
    let down = null;
    let holdTimer = null;
    let tapTimer = null;
    let lastTap = 0;
    let restoreRate = null;

    container.addEventListener('pointerdown', (event) => {
        clearTimeout(holdTimer);
        down = null;
        if (!event.isPrimary || event.button != 0 || event.target.closest('media-controls-content, media-menu, media-popover, button, a, #skipsegment, [data-interactive]'))
        {
            clearTimeout(tapTimer);
            return;
        }
        down = { time: Date.now(), x: event.clientX, y: event.clientY, controlsVisible: container.hasAttribute('data-controls-visible') };
        if (!player.paused) holdTimer = setTimeout(() => {
            restoreRate = player.playbackRate;
            player.playbackRate = restoreRate * 2;
            showIndicator('fa-gauge-high', `${restoreRate * 2}×`, true);
        }, 500);
    });
    container.addEventListener('pointermove', (event) => {
        if (down && Math.hypot(event.clientX - down.x, event.clientY - down.y) > 10)
        {
            clearTimeout(holdTimer);
            down.moved = true;
        }
    });
    const release = (event) => {
        clearTimeout(holdTimer);
        const press = down;
        down = null;
        if (restoreRate !== null)
        {
            player.playbackRate = restoreRate;
            restoreRate = null;
            hideIndicator();
            return;
        }
        if (event.type != 'pointerup' || event.pointerType != 'touch' || !press || press.moved || Date.now() - press.time > 250) return;
        const rect = container.getBoundingClientRect();
        const x = (press.x - rect.left) / rect.width, y = (press.y - rect.top) / rect.height;
        const center = x > 0.33 && x < 0.67 && y > 0.2 && y < 0.8;
        if (!center && press.time - lastTap < DOUBLETAP_WINDOW)
        {
            clearTimeout(tapTimer);
            lastTap = 0;
            return;
        }
        lastTap = press.time;
        if (press.controlsVisible) tapTimer = setTimeout(() => player.paused ? player.play() : player.pause(), center ? 0 : DOUBLETAP_WINDOW);
    };
    ['pointerup', 'pointercancel', 'pointerleave'].forEach(type => container.addEventListener(type, release));
    container.addEventListener('contextmenu', (event) => { if (restoreRate !== null) event.preventDefault(); });
}


function setUpPinchToZoom(setZoom)
{
    const video = player.target;
    let startDistance = null;
    video.style.transition = 'scale .1s ease-out';

    container.addEventListener('touchmove', (event) => {
        if (event.touches.length != 2 || !playerEl.store.isFullscreen) return;
        event.preventDefault();
        const distance = Math.hypot(event.touches[0].clientX - event.touches[1].clientX, event.touches[0].clientY - event.touches[1].clientY);
        startDistance ??= distance;
        const change = distance - startDistance;
        if (Math.abs(change) > 20)
        {
            setZoom(change > 0);
            startDistance = distance - Math.sign(change) * 20;
        }
        video.style.scale = 1 + (distance - startDistance) / 100;
    }, { passive: false });
    ['touchstart', 'touchend', 'touchcancel'].forEach(type => container.addEventListener(type, () => {
        startDistance = null;
        video.style.scale = 1;
    }));
}


function setUpControls()
{
    setUpResolutionMenu();
    setUpRepeatMenu();
    setUpDownloadMenu();
    setUpVideoGestures();

    const setZoom = (zoomed) => {
        if (zoomed == container.classList.contains('zoom-fill')) return;
        container.classList.toggle('zoom-fill', zoomed);
        if (playerEl.store.isFullscreen)
            showIndicator(zoomed ? 'fa-up-right-and-down-left-from-center' : 'fa-down-left-and-up-right-to-center', zoomed ? 'Zoom to fill' : 'Fit to screen');
    };
    const toggleZoom = () => setZoom(!container.classList.contains('zoom-fill'));
    document.getElementById('zoom-trigger').addEventListener('click', toggleZoom);
    setUpPinchToZoom(setZoom);

    const boost = document.getElementById('boost-toggle');
    boost.addEventListener('click', () => {
        const enabled = boost.getAttribute('aria-pressed') !== 'true';
        boost.setAttribute('aria-pressed', enabled);
        setOverAmplification(enabled);
    });

    document.addEventListener('keydown', (event) => {
        if (event.ctrlKey || event.metaKey || event.altKey || event.target.closest('input, textarea, select, [contenteditable]')) return;
        if (/^Arrow(Left|Right)$/.test(event.key) && !event.shiftKey && event.target.closest('media-time-slider'))
        {
            event.preventDefault();
            event.stopImmediatePropagation();
            return document.body.dispatchEvent(new KeyboardEvent(event.type, event));
        }
        const onControl = event.target.closest('button, a, [role^="menuitem"], [role="button"]');
        if (event.code == 'KeyS' && (!onControl || event.target.closest('#settings-menu, #settings-trigger')))
        {
            event.preventDefault();
            event.stopImmediatePropagation();
            document.getElementById('settings-trigger').click();
        }
        else if (onControl) return;
        else if (event.code == 'Enter') skipclick();
        else if (event.code == 'KeyG') toggleZoom();
    }, true);

    document.addEventListener('click', (event) => {
        if (!container.contains(event.target))
            container.focus({ preventScroll: true });
    });

    container.addEventListener('wheel', (event) => {
        if (!event.target.closest('.volume-group')) return;
        event.preventDefault();
        player.volume = Math.max(0, Math.min(1, player.volume + (event.deltaX - event.deltaY) / 2000));
    }, { passive: false });
}


function loadPlaylist(playlistData)
{
    const currentVideoUrl = getUrlInfo().originalUrl;
    const popup = document.getElementById('playlist-popup');
    const list = popup.querySelector('.playlist-items');
    list.replaceChildren(...playlistData.map(item => {
        const listItem = document.createElement('li');
        const link = document.createElement('a');
        link.href = `${window.location.pathname}?url=${encodeURIComponent(item.url)}`;
        if (item.url === currentVideoUrl)
        {
            listItem.classList.add('current');
            link.setAttribute('aria-current', 'page');
        }
        link.innerHTML = `<span class="playlist-thumb">
                <img src="/thumb?url=${encodeURIComponent(item.url)}" alt="">
                <span class="playlist-duration"></span>
            </span>
            <span class="playlist-info">
                <span class="playlist-title"></span>
                <span class="playlist-uploader"></span>
            </span>`;
        link.querySelector('.playlist-duration').textContent = formatTime(item.duration, 0, true);
        link.querySelector('.playlist-title').textContent = item.title;
        link.querySelector('.playlist-uploader').textContent = item.uploader || '';
        listItem.append(link);
        return listItem;
    }));
    document.getElementById('playlist-trigger').hidden = false;
}


function skipclick()
{
    if (player.currentTime < skipTime) player.currentTime = skipTime;
};


function adjustVideoSize()
{
    const width = player.target.videoWidth || parseInt(info['width']) || 720;
    const height = player.target.videoHeight || parseInt(info['height']) || 480;
    const innerWidth = window.innerWidth * 0.95;
    const innerHeight = window.innerHeight * 0.9;
    const scaling = Math.min(innerWidth / width, innerHeight / height);

    container.style.width = width * scaling + 'px';
    container.style.height = height * scaling + 'px';

    const vidAspect = (parseInt(info['width']) || 0) / (parseInt(info['height']) || 1);
    const playerAspect = container.clientWidth / container.clientHeight;

    if (Math.abs(vidAspect - playerAspect) > 0.01) container.classList.add('fit-contain');
    else container.classList.remove('fit-contain');
}


function checkSponsorTime()
{
    var segmentShown = null;
    const time = player.currentTime;
    
    segments.forEach(segment => {
        if (time > segment.start && time < segment.end)
        {
            segmentShown = segment;
        }
        if (time > segment.start - 1 && time < segment.start)
        {
            setTimeout(() => {
                if (!player.paused) checkSponsorTime();
            }, (segment.start - time + .01) * 1000 / player.playbackRate);
        }
    });
    
    if (segmentShown == null)
    {
        skipSegment.style.opacity = 0;
        skipSegment.style.transform = 'translate(120%, 0)';

        if ( "mediaSession" in navigator)
        {
            navigator.mediaSession.metadata.artist = info.uploader;
            navigator.mediaSession.setActionHandler("nexttrack", null);
            navigator.mediaSession.setActionHandler("skipad", null);
        }
    }
    else
    {
        skipSegment.style.opacity = 1;
        skipSegment.style.transform = 'translate(0, 0)';
        skipSegment.title = "skip " + segmentShown.category.replaceAll('_', ' ') + ' [Enter]';
        skipSegment.innerHTML = "skip <b>" + segmentShown.category.replaceAll('_', ' ') + '</b> <i class="fa-solid fa-angles-right"></i>';
        skipTime = segmentShown.end;

        if (info?.autoskip_sb_segments?.indexOf(segmentShown.category) >= 0)
        {
            if (time < segmentShown.start + 1) skipclick();
        }

        if ("mediaSession" in navigator)
        {
            navigator.mediaSession.metadata.artist = info.uploader + `    [${segmentShown.category.replaceAll('_', ' ')}]`;
            navigator.mediaSession.setActionHandler("nexttrack", () => {
                skipclick();
            });
            navigator.mediaSession.setActionHandler("skipad", () => {
                skipclick();
            });
        }
    }
}

function addSponsorblock(data)
{
    Object.entries(Object.groupBy(data, entry => entry.category)).forEach(([category, entries]) => {
        addCues('metadata', `sb-${category}`, entries.map(entry => ({ startTime: entry.start, endTime: entry.end })));
    });
}


function showSponsorblockTitles()
{
    const slider = container.querySelector('media-time-slider');
    const title = container.querySelector('.sb-segment-title');

    slider.addEventListener('pointermove', (event) => {
        const rect = slider.getBoundingClientRect();
        const duration = player.duration;
        if (!rect.width || !(duration > 0)) return;
        const time = Math.min(Math.max((event.clientX - rect.left) / rect.width, 0), 1) * duration;
        const segment = segments.findLast(entry => entry.category == 'poi_highlight' ? 
            Math.abs(time - entry.start) <= (4 / rect.width * duration) : time >= entry.start && time < entry.end);
        title.textContent = segment ? segment.category.replaceAll('_', ' ') : '';
        if (segment) title.style.setProperty('--sb-color', sbColorMap[segment.category] || '#ffffff');
    });
    slider.addEventListener('pointerleave', () => title.textContent = '');
}


function playerMarkup()
{
    const tooltip = 'media-popup media-popup-safe-area media-popup-transition media-tooltip-popup';
    const appTitle = document.querySelector('meta[property="og:site_name"]').getAttribute('content');
    const themeColor = document.querySelector('meta[name="theme-color"]').content;
    const appButton = window.location.pathname == '/iframe' ? `
                                <a class="media-button app-button" id="app-trigger" href="${window.location.href.replace('iframe', 'watch')}" target="_blank" aria-label="Watch in ${appTitle}"><img src="/favicon.svg" alt=""></a>
                                <media-tooltip trigger="app-trigger" side="top" class="${tooltip}">Watch in ${appTitle}</media-tooltip>` : '';
    const submenu = (id, icon, label, content, cls = '') => `
        <media-menu-item commandfor="${id}" class="media-menu-item ${cls}">
            <i class="fa-solid ${icon} media-menu-trigger-icon"></i>${label}
            <span class="media-menu-hint"><i class="fa-solid fa-chevron-right media-menu-forward-chevron"></i></span>
        </media-menu-item>
        <media-menu-content class="media-menu-content" id="${id}">
            <media-menu-item class="media-menu-back-item"><i class="fa-solid fa-chevron-right media-menu-back-chevron"></i>${label}</media-menu-item>
            <media-menu-separator class="media-menu-separator"></media-menu-separator>
            ${content}
        </media-menu-content>`;
    return `
<video-player id="player" style="--media-accent-color: ${themeColor}">
    <media-container id="player-container" class="media-skin media-container media-video loading" data-theme="compat" data-preset="video">
        <hlsjs-video id="videoPlayer" preload="auto" playsinline></hlsjs-video>
        <media-poster class="media-poster"><img alt="" decoding="async" class="media-poster-image"></media-poster>
        <div class="audio-overlay"></div>
        <media-buffering-indicator class="media-buffering-indicator"><div class="spinner"></div></media-buffering-indicator>
        <!-- App messages; the skin's error dialog is left out, as playback errors move on to the next source -->
        <div class="app-message" hidden></div>
        <media-controls>
            <media-buffering-indicator class="video-controls-buffering">
            <media-controls-backdrop class="video-controls-backdrop"></media-controls-backdrop>
            <media-controls-content class="video-controls-content">
                <media-tooltip-group>
                    <media-controls-group class="video-controls-top">
                        <div class="title-bar"><media-title class="media-title"></media-title><div class="media-uploader"></div></div>
                        <button type="button" commandfor="playlist-popup" class="media-button" id="playlist-trigger" aria-label="Playlist" hidden><i class="fa-solid fa-list-ul media-button-icon"></i></button>
                        <media-tooltip trigger="playlist-trigger" side="bottom" class="${tooltip}">Playlist</media-tooltip>
                        <media-popover side="bottom" align="end" class="media-popup media-popup-safe-area media-popup-transition playlist-popup" id="playlist-popup"><ol class="playlist-items"></ol></media-popover>
                    </media-controls-group>
                    <div class="video-controls-bottom">
                        <div class="video-controls-slider-row">
                            <media-time-slider class="media-time-slider" thumb-alignment="edge">
                                <media-time-slider-chapters class="media-time-slider-chapters">
                                    <template>
                                        <div class="media-time-slider-chapter">
                                            <media-slider-track class="media-time-slider-track">
                                                <media-slider-buffer class="media-time-slider-buffer"></media-slider-buffer>
                                                <media-slider-fill class="media-time-slider-fill"></media-slider-fill>
                                            </media-slider-track>
                                        </div>
                                    </template>
                                </media-time-slider-chapters>
                                ${Object.entries(sbColorMap).map(([category, color]) => `<media-time-slider-markers class="sb-markers" label="sb-${category}" style="--sb-color: ${color}"></media-time-slider-markers>`).join('')}
                                <media-slider-thumb class="media-time-slider-thumb"></media-slider-thumb>
                                <media-slider-preview class="media-time-slider-preview">
                                    <media-slider-thumbnail class="media-slider-thumbnail"><img alt="" aria-hidden="true" decoding="async" class="media-slider-thumbnail-image"></media-slider-thumbnail>
                                    <span class="sb-segment-title"></span>
                                    <div class="media-time-slider-preview-label">
                                        <media-slider-value class="media-time-slider-value" type="pointer"></media-slider-value>
                                        <media-time-slider-chapter-title class="media-time-slider-chapter-title"></media-time-slider-chapter-title>
                                    </div>
                                </media-slider-preview>
                            </media-time-slider>
                        </div>
                        <media-controls-group class="video-controls-row">
                            <media-controls-group class="video-controls-group video-controls-start">
                                <media-play-button class="media-button media-play-button" id="play-trigger">
                                    <i class="fa-solid fa-rotate-right media-button-icon-base media-play-button-restart-icon"></i>
                                    <i class="fa-solid fa-play media-button-icon-base media-play-button-play-icon"></i>
                                    <i class="fa-solid fa-pause media-button-icon-base media-play-button-pause-icon"></i>
                                </media-play-button>
                                <media-tooltip trigger="play-trigger" side="top" class="${tooltip}"></media-tooltip>
                                <div class="volume-group">
                                    <media-mute-button class="media-button media-mute-button" id="mute-trigger">
                                        ${[['off', 'fa-volume-xmark'], ['low', 'fa-volume-off'], ['medium', 'fa-volume-low'], ['high', 'fa-volume']].map(([level, icon]) => `<i class="fa-solid ${icon} media-button-icon vol-${level}"></i>`).join('')}
                                    </media-mute-button>
                                    <media-tooltip trigger="mute-trigger" side="top" class="${tooltip}"></media-tooltip>
                                    <div class="volume-slider-wrap">
                                        <media-volume-slider class="media-volume-slider" thumb-alignment="edge" orientation="horizontal">
                                            <media-slider-track class="media-volume-slider-track"><media-slider-fill class="media-volume-slider-fill"></media-slider-fill></media-slider-track>
                                            <media-slider-thumb class="media-volume-slider-thumb"></media-slider-thumb>
                                        </media-volume-slider>
                                        <button type="button" class="media-button boost-button" id="boost-toggle" aria-pressed="false" aria-label="Volume boost"><i class="fa-solid fa-bolt media-button-icon"></i></button>
                                    </div>
                                    <media-tooltip trigger="boost-toggle" side="top" class="${tooltip}">Volume boost</media-tooltip>
                                </div>
                                <media-time-group class="media-time-group">
                                    <media-time class="media-time-toggle" type="current" toggle></media-time>
                                    <media-time class="media-time-current-value" type="current"></media-time>
                                    <media-time-separator class="media-time-separator vod-only"></media-time-separator>
                                    <media-time class="media-time-duration-value vod-only" type="duration"></media-time>
                                </media-time-group>
                            </media-controls-group>
                            <media-controls-group class="video-controls-group">
                                <button type="button" commandfor="settings-menu" class="media-button media-settings-button" id="settings-trigger">
                                    <i class="fa-solid fa-gear media-button-icon media-settings-button-icon"></i>
                                    <media-text class="media-settings-button-label" token="menu.settings">Settings</media-text>
                                </button>
                                <media-tooltip trigger="settings-trigger" side="top" class="${tooltip}"><media-text token="menu.settings">Settings</media-text><span class="media-tooltip-shortcut">S</span></media-tooltip>
                                <media-menu side="top" align="center" class="media-popup media-popup-safe-area media-menu-popup media-menu-resizable-popup" id="settings-menu">
                                    <media-menu-content class="media-menu-content">
                                        ${submenu('quality-menu', 'fa-sliders', '<media-text token="menu.quality">Quality</media-text>', '<media-menu-radio-group class="media-menu-radio-group" id="quality-group"></media-menu-radio-group>')}
                                        ${submenu('audio-menu', 'fa-language', '<media-text token="menu.audio">Audio</media-text>', '<media-audio-track-radio-group class="media-menu-radio-group"></media-audio-track-radio-group>')}
                                        ${submenu('speed-menu', 'fa-gauge-high', '<media-text token="menu.speed">Speed</media-text>', '<media-playback-rate-radio-group class="media-menu-radio-group"></media-playback-rate-radio-group>', 'vod-only')}
                                        ${submenu('captions-menu', 'fa-closed-captioning', '<media-text token="menu.captions">Captions</media-text>', '<media-captions-radio-group class="media-menu-radio-group"></media-captions-radio-group>')}
                                        ${submenu('loop-menu', 'fa-repeat', 'Loop', `
                                        <media-menu-checkbox-item class="media-menu-radio-item" id="loop-toggle">Loop<media-menu-item-indicator force-mount class="media-menu-indicator"><i class="fa-solid fa-check media-menu-radio-icon"></i></media-menu-item-indicator></media-menu-checkbox-item>
                                        <media-menu-item class="media-menu-item" id="range-start">Set start<span class="time_disp"></span></media-menu-item>
                                        <media-menu-item class="media-menu-item" id="range-end">Set end<span class="time_disp"></span></media-menu-item>
                                        `, 'vod-only')}
                                        ${submenu('download-menu', 'fa-download', 'Download', `
                                        <media-menu-item class="media-menu-item" data-download="best">Highest quality</media-menu-item>
                                        <media-menu-item class="media-menu-item" data-download="current">Current quality</media-menu-item>
                                        <media-menu-item class="media-menu-item" data-download="audio">Audio</media-menu-item>
                                        <media-menu-item class="media-menu-item" data-download="picture">Picture</media-menu-item>
                                        <media-menu-separator class="media-menu-separator"></media-menu-separator>
                                        <media-menu-checkbox-item class="media-menu-radio-item" id="download-trim">Trim<media-menu-item-indicator force-mount class="media-menu-indicator"><i class="fa-solid fa-check media-menu-radio-icon"></i></media-menu-item-indicator></media-menu-checkbox-item>
                                        <media-menu-item class="media-menu-item" id="download-start" hidden>Set start<span class="time_disp"></span></media-menu-item>
                                        <media-menu-item class="media-menu-item" id="download-end" hidden>Set end<span class="time_disp"></span></media-menu-item>
                                        `, 'vod-only')}
                                    </media-menu-content>
                                </media-menu>
                                ${appButton}
                                <media-pip-button class="media-button media-pip-button" id="pip-trigger">
                                    <i class="fa-solid fa-picture-in-picture media-button-icon media-pip-button-enter-icon"></i>
                                    <i class="fa-solid fa-window-restore media-button-icon media-pip-button-exit-icon"></i>
                                </media-pip-button>
                                <media-tooltip trigger="pip-trigger" side="top" class="${tooltip}"></media-tooltip>
                                <button type="button" class="media-button zoom-button" id="zoom-trigger" aria-label="Zoom to fill">
                                    <i class="fa-solid fa-up-right-and-down-left-from-center media-button-icon zoom-in-icon"></i>
                                    <i class="fa-solid fa-down-left-and-up-right-to-center media-button-icon zoom-out-icon"></i>
                                </button>
                                <media-tooltip trigger="zoom-trigger" side="top" class="${tooltip}">Zoom to fill<span class="media-tooltip-shortcut">G</span></media-tooltip>
                                <media-fullscreen-button class="media-button media-fullscreen-button" id="fullscreen-trigger">
                                    <i class="fa-solid fa-expand media-button-icon media-fullscreen-button-enter-icon"></i>
                                    <i class="fa-solid fa-compress media-button-icon media-fullscreen-button-exit-icon"></i>
                                </media-fullscreen-button>
                                <media-tooltip trigger="fullscreen-trigger" side="top" class="${tooltip}"></media-tooltip>
                            </media-controls-group>
                        </media-controls-group>
                    </div>
                </media-tooltip-group>
            </media-controls-content>
            </media-buffering-indicator>
        </media-controls>
        ${[['Space', 'togglePaused'], ['k', 'togglePaused'], ['m', 'toggleMuted'], ['ArrowRight', 'seekStep'], ['ArrowLeft', 'seekStep'], ['l', 'seekStep'], ['j', 'seekStep'],
            ['ArrowUp', 'volumeStep'], ['ArrowDown', 'volumeStep'], ['0-9', 'seekToPercent'], ['>', 'speedUp'], ['<', 'speedDown'], ['f', 'toggleFullscreen'], ['c', 'toggleSubtitles'], ['i', 'togglePictureInPicture'], ['p', 'togglePictureInPicture']]
            .map(([keys, action]) => `<media-hotkey target="document" keys="${keys}" action="${action}"></media-hotkey>`).join('\n')}
        <media-hotkey target="document" keys="." action="seekStep" value="0.1"></media-hotkey>
        <media-hotkey target="document" keys="," action="seekStep" value="-0.1"></media-hotkey>
        <media-gesture type="tap" action="togglePaused" pointer="mouse" region="center"></media-gesture>
        <media-gesture type="tap" action="toggleControls" pointer="touch"></media-gesture>
        <media-gesture type="doubletap" action="seekStep" region="left"></media-gesture>
        <media-gesture type="doubletap" action="toggleFullscreen" region="center"></media-gesture>
        <media-gesture type="doubletap" action="seekStep" region="right"></media-gesture>
        <media-status-announcer class="media-status-announcer"></media-status-announcer>
        <div aria-hidden="true" class="media-indicator-group">
            <media-volume-indicator class="media-indicator media-volume-indicator">
                <media-volume-indicator-fill class="media-volume-indicator-fill">
                    ${[['high', 'fa-volume'], ['low', 'fa-volume-off'], ['off', 'fa-volume-xmark']].map(([level, icon]) => `<i class="fa-solid ${icon} media-volume-indicator-icon media-volume-indicator-${level}-icon"></i>`).join('')}
                    <media-volume-indicator-value class="media-volume-indicator-value"></media-volume-indicator-value>
                </media-volume-indicator-fill>
            </media-volume-indicator>
            <media-status-indicator actions="toggleSubtitles,toggleFullscreen,togglePictureInPicture" class="media-indicator media-status-indicator">
                ${[['captions-on', 'fa-solid fa-closed-captioning'], ['captions-off', 'fa-regular fa-closed-captioning'], ['fullscreen-enter', 'fa-solid fa-expand'],
                    ['fullscreen-exit', 'fa-solid fa-compress'], ['pip-enter', 'fa-solid fa-picture-in-picture'], ['pip-exit', 'fa-solid fa-window-restore']]
                    .map(([status, icon]) => `<i class="${icon} media-status-indicator-icon media-status-indicator-${status}-icon"></i>`).join('')}
                <media-status-indicator-value></media-status-indicator-value>
            </media-status-indicator>
            <!-- Same look as media-status-indicator, for app actions it can't observe (zoom, hold to speed up) -->
            <div class="media-indicator media-status-indicator" id="app-indicator" hidden><span class="app-indicator-icon"></span><span class="app-indicator-value"></span></div>
            <media-seek-indicator class="media-indicator media-seek-indicator">
                <i class="fa-solid fa-angles-right media-seek-indicator-icon"></i>
                <media-seek-indicator-value class="media-seek-indicator-value"></media-seek-indicator-value>
            </media-seek-indicator>
        </div>
    </media-container>
</video-player>
<!-- Separate audio track for sources with split video and audio streams -->
<hlsjs-video id="audioPlayer" preload="auto" style="display: none"></hlsjs-video>
<!-- Check-marked menu option, cloned into every radio group by script.js -->
<template id="radio-item"><media-menu-radio-item class="media-menu-radio-item"><span data-part="label"></span><media-menu-item-indicator force-mount class="media-menu-indicator"><i class="fa-solid fa-check media-menu-radio-icon"></i></media-menu-item-indicator></media-menu-radio-item></template>`;
}


async function loadVideo()
{
    var debugView = document.getElementById('debug-view');
    if (debugView) debugView.onclick = displayDebugInfo;
    var url = getUrlInfo();
    if (url.urlParams.toString().length < 10) return;
    
    document.getElementById('video').insertAdjacentHTML('beforeend', playerMarkup());
    const appTitle = document.querySelector('meta[property="og:site_name"]').getAttribute('content');

    const radioItem = document.getElementById('radio-item');
    document.querySelectorAll('.media-menu-radio-group:not(#quality-group)').forEach(group => group.append(Object.assign(radioItem.cloneNode(true), { id: '' })));
    
    await Promise.all([customElements.whenDefined('video-player'), customElements.whenDefined('hlsjs-video')]);
    playerEl = document.getElementById('player');
    container = document.getElementById('player-container');
    player = document.getElementById('videoPlayer');
    audioPlayer = document.getElementById('audioPlayer');
    
    playerEl.setAttribute('poster', `/thumb?url=${url.encodedUrl}`);
    container.style.setProperty('--media-poster-url', `url("/thumb?url=${url.encodedUrl}")`);
    
    skipSegment = document.createElement('div');
    container.appendChild(skipSegment);
    skipSegment.id = "skipsegment";
    skipSegment.onclick = function() {skipclick();};
    ['pointerdown', 'pointerup', 'click', 'touchstart', 'touchend'].forEach(type => skipSegment.addEventListener(type, (event) => event.stopPropagation()));

    player.addEventListener('timeupdate', () => {
        const loopStart = repeatRange[0] ?? 0;
        const loopEnd = repeatRange[1] ?? player.duration;
        if (repeatMode && player.currentTime >= loopEnd)
        {
            player.currentTime = loopStart;
            setTimeout(() => {
                player.play();
            }, 100);
        }
        if (info && parseFloat(info.duration) == 0)
        {
            let timeDiff = bufferedEnd(player) - player.currentTime;
            if (playerMode == PlayerModes.VIDEO_AUDIO)
                timeDiff = Math.min(timeDiff, bufferedEnd(audioPlayer) - audioPlayer.currentTime);
            let minLiveBuffer = parseFloat(info.min_live_buffer);
            if (timeDiff > 30 || minLiveBuffer <= 0)
            {
                let rate = player.playbackRate;
                if (rate != 1 && rate < 1.15 && rate > 0.9) player.playbackRate = 1;
                return;
            }
            if (timeDiff < minBufferAheadTime) minBufferAheadTime = Math.max(timeDiff, 0);
            else minBufferAheadTime = (minBufferAheadTime * 2047 + timeDiff) / 2048;
            
            if (minBufferAheadTime < minLiveBuffer)
            {
                player.playbackRate = 0.95;
                log('-');
            }
            else if (minBufferAheadTime > minLiveBuffer * 3)
            {
                player.playbackRate = 1.1;
                log('++');
            }
            else if (minBufferAheadTime > minLiveBuffer * 2)
            {
                player.playbackRate = 1.05;
                log('+');
            }
            else
            {
                player.playbackRate = 1;
            }
        }
    });

    player.addEventListener('playing', () => {
        minBufferAheadTime = 1;
        if (info && parseFloat(info.duration) == 0 && player.currentTime < 1)
        {
            player.currentTime = 99999999;
        }
    });
    document.getElementById('video').style.filter = 'brightness(1)';

    // When video is loaded
    function playerReady() {
        if (!container.classList.contains('loading')) return;
        container.classList.remove('loading');
        document.querySelector('.media-poster-image').style.filter = 'none';
        container.style.transitionDuration = '0.5s';
        adjustVideoSize();
        window.addEventListener('resize', adjustVideoSize);
        setTimeout(() => {container.style.transitionDuration = '0s';}, 100);

        if (parseFloat(info.duration) < parseInt(info.generate_sprite_below) && parseFloat(info.duration) > 0)
        {
            retryFetch(`/sprite?url=${url.encodedUrl}`, {}, 100, undefined, false).then(response => response.blob()).then(blob => {
                const [width, height, columns, interval] = info.sprite;
                const duration = parseFloat(info.duration);
                const cues = [];
                const spriteUrl = URL.createObjectURL(blob);
                for (let i = 0; i * interval < duration; i++)
                {
                    const xywh = `${(i % columns) * width},${Math.floor(i / columns) * height},${width},${height}`;
                    cues.push({ startTime: i * interval, endTime: Math.min((i + 1) * interval, duration), text: `${spriteUrl}#xywh=${xywh}` });
                }
                addCues('metadata', 'thumbnails', cues);
                return createImageBitmap(blob);
            }).then(bitmap => sprite = bitmap);
        }

        if (info.autoplay)
        {
            player.play();
        }

        if (url.startTime && parseFloat(url.startTime) > 0)
        {
            player.currentTime = parseFloat(url.startTime);
        }
    }
    retryFetch(`/info?url=${url.encodedUrl}`)
        .then(response => response.json())
        .then(rawInfo => {
            info = rawInfo;
            if (info["error"] !== undefined)
            {
                displayPlayerError(info['error']);
                return;
            }
            if (info.alerts)
            {
                for (let i = 0; i < info.alerts.length; i++)
                {
                    alert(info.alerts[i]);
                }
            }
            player.addEventListener('durationchange', () => {if (player.duration > 0) playerReady()});
            player.addEventListener('loadeddata', () => {playerReady()});

            if (info.chapters.length > 0)
                addCues('chapters', '', info.chapters.map(chapter => ({ startTime: chapter.time, text: chapter.label })));

            setUpControls();
            loadSubtitles(info.subtitles);
            if (parseFloat(info.duration) == 0) container.classList.add('live');
            setVideoQuality(url.quality || info.default_quality);

            if (typeof info.title == 'string' && info.title != '')
            {
                const titleLength = 80 - (' | ' + appTitle).length;
                info.shortTitle = info.title.length > titleLength ? info.title.substring(0, titleLength - 3) + "..." : info.title;
                playerEl.setAttribute('content-title', info.title);
                if (info.uploader) container.querySelector('.media-uploader').textContent = info.uploader;
                document.title = info.shortTitle + ' | ' + appTitle;
                info.uploader = info.uploader? info.uploader : appTitle;
            }

            setupPlayerSync();
            setupSeekPreview();
            player.addEventListener('error', () => {
                const error = player.error;
                if (error)
                {
                    warn(`VIDEO PLAYER ERROR ${error.code} - Trying the next available source`);
                    playerEl.store.dismissError();
                    advanceVideoSource();
                }
            });
            audioPlayer.addEventListener('error', () => {
                const error = audioPlayer.error;
                if (error)
                {
                    warn(`AUDIO PLAYER ERROR ${error.code} - Trying the next available source`);
                    advanceAudioSource();
                }
            });
            try
            {
                loadMediaSession();
            }
            catch {}

            if (info.playlist_support == true && window.location.pathname != '/iframe')
            {
                retryFetch(`/playlist?url=${url.encodedUrl}`)
                    .then(response => response.json())
                    .then(playlistData => {
                        if (Array.isArray(playlistData) && playlistData.length > 0)
                        {
                            loadPlaylist(playlistData);
                        }
                    });
            }

            setInterval(()=>{ retryFetch(getVideoSource()[0], {}, 0, undefined, false, true).then(response => response.ok); }, 120000); // Keepalive

            setInterval(()=>{ updatePlaybackTime(); }, 10000);

            document.addEventListener('visibilitychange', () => {
                syncVideo(true);
                if (document.visibilityState === 'hidden') updatePlaybackTime();
                if (info.auto_bg_playback && navigator?.userAgentData?.mobile)
                {
                    var url = getUrlInfo();
                    if (url.quality == 'audio')
                    {
                        if (info.audio_visualizer)
                        {
                            if (document.visibilityState === 'hidden') pauseVisualizer(player);
                            else resumeVisualizer(player);
                        }
                        return;
                    }
                    if (document.pictureInPictureElement) return;
                    if (parseFloat(info.duration) == 0) return;
                }
                if (!info.auto_bg_playback && document.visibilityState === 'hidden')
                {
                    audioPlayer.pause();
                }
            });

        })
        .catch(error => {
            displayPlayerError(`Error: ${error.message}`);
        });

        
    retryFetch(`/sb?url=${url.encodedUrl}`)
        .then(response => response.json())
        .then(data => {
            if (Array.isArray(data)) {
                segments = data;
                player.addEventListener('loadeddata', () => {
                    addSponsorblock(data);
                });
                showSponsorblockTitles();
                player.addEventListener('timeupdate', checkSponsorTime);
                audioPlayer.addEventListener('timeupdate', checkSponsorTime);
            }
        });
}


function loadMediaSession()
{
    if (!("mediaSession" in navigator)) return;

    var url = getUrlInfo();
    navigator.mediaSession.metadata = new MediaMetadata({
        title: info.shortTitle,
        artist: info.uploader,
        album: "",
        artwork: [
            {
                src: `/thumb?url=${url.encodedUrl}`,
                sizes: "512x512",
                type: "image/png",
            },
        ],
    });

    navigator.mediaSession.setActionHandler("play", () => {
        player.play();
    });
    navigator.mediaSession.setActionHandler("pause", () => {
        player.pause();
    });
    navigator.mediaSession.setActionHandler("seekbackward", (details) => {
        player.currentTime -= (details.seekOffset || 10);
    });
    navigator.mediaSession.setActionHandler("seekforward", (details) => {
        player.currentTime += (details.seekOffset || 10);
    });
    navigator.mediaSession.setActionHandler("seekto", (details) => {
        player.currentTime = details.seekTime;
    });
    navigator.mediaSession.setActionHandler("previoustrack", null);
    navigator.mediaSession.setActionHandler("nexttrack", null);

    function updateMediaSession()
    {
        if (info.duration <= 0) return;
        navigator.mediaSession.playbackState = player.paused ? 'paused' : 'playing';
        navigator.mediaSession.setPositionState?.({ duration: info.duration, playbackRate: player.playbackRate, position: Math.min(player.currentTime, info.duration) });
    }
    ['play', 'pause', 'ratechange', 'seeked'].forEach(type => player.addEventListener(type, updateMediaSession));
    ['play', 'pause', 'ratechange', 'seeked'].forEach(type => audioPlayer.addEventListener(type, updateMediaSession));
    log("Loaded Media Player API");
}


let debugInterval = null;
function displayDebugInfo()
{
    let oldviewbox = document.getElementById('debug-viewbox');
    if (oldviewbox)
    {
        document.body.removeChild(oldviewbox);
        clearInterval(debugInterval);
        return;
    }
    let viewbox = document.createElement("div");
    viewbox.style = "width: 80%; height: 500px; overflow: scroll; position: absolute; top: 100vh; white-space: pre; background-color: #111; padding: 20pt;";
    viewbox.id = 'debug-viewbox';

    function updateDebugInfo()
    {
        const open = [...viewbox.querySelectorAll("details")].map(d => d.open);

        viewbox.innerHTML = `
            Debug logs for <b>${window.location.href}</b>
            <details><summary>URL info</summary>${JSON.stringify(getUrlInfo(), null, 2)}</details>
            <details><summary>Info dict</summary>${JSON.stringify(info, null, 2)}</details>
            <details><summary>Current source</summary>
            <br>Video:\n${JSON.stringify(player?.source, null, 2)}
            <button onclick="advanceVideoSource()">advanceVideoSource()</button>
            <br>Audio:\n${JSON.stringify(audioPlayer?.source, null, 2)}
            <button onclick="advanceAudioSource()">advanceAudioSource()</button>
            </details>
            <details><summary>Console log</summary>${JSON.stringify(logHistory, null, 2)}</details>
        `;

        [...viewbox.querySelectorAll("details")].forEach((d, i) => d.open = open[i] ?? false);
    }


    debugInterval = setInterval(() => { updateDebugInfo(); }, 1000);
    updateDebugInfo();

    document.body.appendChild(viewbox);
}


loadVideo();
