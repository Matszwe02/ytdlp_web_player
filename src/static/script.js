let player;
let skipSegment;
let skipTime = 0;
let meta = null;
let activeFetches = 0; // Counter for active retryFetch calls
let abortController = null; // AbortController for cancelling fetches
let repeatMode = false;
let repeatStartTime = 0;
let repeatEndTime = 0;
let audioContext = null;
let audioSource = null;



class PlayerState
{
    constructor()
    {
        this.ongoing = false;
        this.switchTime = 0;
        this.isPlaying = false;
        this.tracks = null;
    }
    save()
    {
        if (this.ongoing && player.currentTime() == 0)
        {
            console.warn('Preventing saving unknown player state');
            return;
        }
        this.ongoing = false;
        this.switchTime = player.currentTime();
        this.isPlaying = !player.paused();
        this.tracks = [];
        const textTracks = player.textTracks();
        for (let i = 0; i < textTracks.length; i++)
        {
            const track = textTracks[i];
            if (!track.src || track.kind != 'subtitles') continue;
            this.tracks.push({
                kind: track.kind,
                src: track.src,
                srclang: track.srclang,
                label: track.label
            });
        }
    }
    apply()
    {
        player.currentTime(this.switchTime);
        if (this.isPlaying) player.play();
        for (let i = 0; i < this.tracks.length; i++)
        {
            const track = this.tracks[i];
            if (track.kind == 'subtitles') player.addRemoteTextTrack(track);
        }
        this.ongoing = true;
    }
}
let ps = new PlayerState();


function setUpAudioContext()
{
    if (audioContext == null)
    {
        audioContext = new (window.AudioContext || window.webkitAudioContext)();
        audioSource = audioContext.createMediaElementSource(player.el_.querySelector('video'));
        audioSource.connect(audioContext.destination);
    }
}


function tryStopPropagation(event)
{
    try
    {
        if (player && event.target?.classList.contains('menu-button'))
            player.clickedChildMenuButton = true;
        event.stopPropagation();
    }
    catch (error) {}
    player.el_.focus();
}


function addFetch()
{
    activeFetches += 1;
    console.log(activeFetches);
    try
    {
        const settingsIcon = player?.controlBar?.SettingsButton?.el().querySelector('.fa-gear');
        if (settingsIcon)
        {
            settingsIcon.classList.add('vjs-spin');
        }
    }
    catch (error)
    {
        console.log(error);
    }
}


function removeFetch()
{
    activeFetches -= 1;
    console.log(activeFetches);
    try
    {
        const settingsIcon = player?.controlBar?.SettingsButton?.el().querySelector('.fa-gear');
        if (settingsIcon)
        {
            if (activeFetches == 0)
            {
                settingsIcon.classList.remove('vjs-spin');
            }
        }
    }
    catch (error)
    {
        console.log(error);
    }
}


async function retryFetch(url, options = {}, retries = 5, delay = 5000, visible = true, head = false)
{
    if (visible) addFetch();
    try
    {
        const fetchOptions = { method: (head ? 'HEAD' : 'GET'), ...options };
        const error = new Error();
        const stack = error.stack.split('\n');
        let callerInfo = 'unknown';
        if (stack.length > 2)
        {
            const callerLine = stack[2];
            const match = callerLine.match(/at (.*?) \((.*?):(\d+):(\d+)\)/) || callerLine.match(/at (.*?):(\d+):(\d+)/);
            if (match)
            {
                if (match.length === 5) callerInfo = `${match[1]} (${match[2]}:${match[3]})`;
                else if (match.length === 4) callerInfo = `(${match[1]}:${match[2]})`;
            }
        }
        if (player != null)
        {
            console.log(`Fetching ${fetchOptions.method} "${url}" called from ${callerInfo}`);
            const response = await fetch(url, fetchOptions);
            if (response.status >= 500) throw new Error(`Server error: ${await response.text()}`);
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            return response;
        }
    }
    catch (error)
    {
        if (error.name === 'AbortError')
        {
            console.log(`Fetch for "${url}" aborted.`);
            throw error;
        }
        if (error.message.startsWith('Server error:'))
        {
            throw error;
        }
        console.error(`Fetch failed, retrying in ${delay / 1000} seconds...`, error);
        if (retries > 0)
        {
            await new Promise(resolve => setTimeout(resolve, delay));
            return retryFetch(url, options, retries - 1, delay, visible, head);
        }
        else
        {
            console.error(`Max retries reached for "${url}". Fetch failed.`);
            throw error;
        }
    }
    finally
    {
        if (visible) removeFetch();
    }
}

function formatTime(timeInSeconds)
{
    if (timeInSeconds === null || isNaN(timeInSeconds)) return '-';
    const hours = Math.floor(timeInSeconds / 3600);
    const minutes = Math.floor((timeInSeconds % 3600) / 60);
    const seconds = Math.floor(timeInSeconds % 60);
    const milliseconds = Math.floor((timeInSeconds % 1) * 10);
    return String(hours).padStart(2, '0') + ':' + String(minutes).padStart(2, '0') + ':' + String(seconds).padStart(2, '0') + '.' + String(milliseconds);
}

function formatTimeShort(timeInSeconds)
{
    if (timeInSeconds === null || isNaN(timeInSeconds)) return '-';
    var out_str = "";
    const hours = Math.floor(timeInSeconds / 3600);
    if (hours > 0) out_str += String(hours).padStart(2, '0') + ":";
    const minutes = Math.floor((timeInSeconds % 3600) / 60);
    const seconds = Math.floor(timeInSeconds % 60);
    out_str += String(minutes).padStart(2, '0') + ':' + String(seconds).padStart(2, '0');
    return out_str.startsWith("0") ? out_str.substring(1) : out_str;
}


var prevRotation = 0;
function fullscreenOnRotate()
{
    const screenAspect = (screen.height / screen.width);
    const videoAspect = ((player.videoHeight() || 480) / (player.videoWidth() || 720));
    const aspectDiff = Math.abs(videoAspect - screenAspect) - Math.abs((1/videoAspect) - screenAspect);
    if (aspectDiff < -0.3 && !player.isFullscreen())
    {
        player.requestFullscreen();
    }
    else if (aspectDiff > 0.3 && player.isFullscreen())
    {
        player.exitFullscreen();
    }
}
screen.orientation.addEventListener("change", (event) => {
    fullscreenOnRotate();
});


function displayPlayerError(message)
{
    console.error(message);
    if (!player) return;
    const errorDisplay = player.el_.querySelector('.vjs-error-display');
    errorDisplay.innerHTML = message;
    errorDisplay.classList.remove('spinner-parent');
    errorDisplay.classList.remove('vjs-hidden');
    player.src({ src: 'null', type: 'null' });
    player = null;
}


function loadChapters()
{
    var duration = player.duration();
    var progressEl = player.controlBar.progressControl.children_[0].el_;
    var timeToolip = progressEl.querySelector('.vjs-time-tooltip');
    var chapterHoverTooltip = document.createElement('div');
    chapterHoverTooltip.className = 'vjs-time-tooltip chapter-tooltip';
    chapterHoverTooltip.style.display = "none";
    progressEl.querySelector('.vjs-mouse-display').appendChild(chapterHoverTooltip);

    let isHoveringProgressBar = false;

    function turnOnChapterLabel(label)
    {
        chapterHoverTooltip.style.display = "block";
        chapterHoverTooltip.style.right = timeToolip.style.right;
        chapterHoverTooltip.textContent = label;
        chapterHoverTooltip.style.transform = 'translateY(-100%)';
    }

    function turnOffChapterLabel()
    {
        chapterHoverTooltip.style.display = "none";
    }

    function updateChapterVisibility(currentTime)
    {
        const progressControlWidth = progressEl.clientWidth;
        const scale = duration / progressControlWidth;
        const margin = 4; // px
        let chapterFound = false;
        for (let i = 0; i < meta.chapters.length; i++)
        {
            const chapter = meta.chapters[i];
            const diff = currentTime - chapter.time;
            if (diff > (-margin * scale) && diff < (margin * scale))
            {
                turnOnChapterLabel(chapter.label);
                chapterFound = true;
                break;
            }
        }
        if (!chapterFound)
        {
            turnOffChapterLabel();
        }
    }

    function onProgressBarMove(event)
    {
        isHoveringProgressBar = true;
        const progressControlWidth = progressEl.clientWidth;
        const rect = progressEl.getBoundingClientRect();
        const mouseX = (event.touches && event.touches[0] ? event.touches[0].clientX : event.clientX) - rect.left;

        updateChapterVisibility((mouseX / progressControlWidth) * duration);
    }

    function onProgressBarLeave()
    {
        isHoveringProgressBar = false;
        turnOffChapterLabel();
    }

    function updateChapterTooltipOnPlayback()
    {
        if (isHoveringProgressBar) return;
        updateChapterVisibility(player.currentTime());
    }

    player.controlBar.progressControl.on(['mousemove', 'touchmove'], onProgressBarMove);
    player.controlBar.progressControl.on(['mouseout', 'touchend'], onProgressBarLeave);
    player.on('timeupdate', updateChapterTooltipOnPlayback);


    for(let i=0; i<meta.chapters.length; i++)
    {
        var el = document.createElement('div');
        el.className = 'vjs-marker';
        el.style.left = `${(meta.chapters[i].time / duration * 100)}%`;
        let label = meta.chapters[i].label;
        el.addEventListener('mouseover', ()=>{turnOnChapterLabel(label);});
        el.addEventListener('mouseout', turnOffChapterLabel);
        progressEl.appendChild(el);
    }
}


function getVideoSource()
{
    const urlParams = new URLSearchParams(window.location.search);
    const originalUrl = urlParams.get('v') || urlParams.get('url');
    var quality = urlParams.get('quality');
    if (quality == '') quality = null;
    if (quality == 'null') quality = null;
    const hlsEnabled = quality != null && quality != 'audio'
    console.log(`Video quality: ${quality} ${hlsEnabled ? '(HLS)' : ''}`);

    let downloadUrl;
    let videoType;

    if (hlsEnabled)
    {
        downloadUrl = `/hls?url=${encodeURIComponent(originalUrl)}&quality=${quality}`;
        videoType = 'application/x-mpegURL';
    }
    else
    {
        downloadUrl = quality ? `/download?url=${encodeURIComponent(originalUrl)}&quality=${quality}` : `/direct?url=${encodeURIComponent(originalUrl)}`;
        videoType = 'video/mp4';
    }
    return [downloadUrl, videoType];
}


function applyVideoQuality()
{
    const urlParams = new URLSearchParams(window.location.search);
    var quality = urlParams.get('quality');
    if (meta['height'] == null && meta['width'] == null) quality = 'audio';
    const videoSource = getVideoSource();

    const videoEl = player.el_.querySelector('video');
    const posterEl = player.el_.querySelector('.vjs-poster');
    ps.save();
    player.src({ src: videoSource[0], type: videoSource[1] });
    ps.apply();

    if (quality === 'audio')
    {
        if (videoEl) videoEl.style.display = 'none';
        if (posterEl)
        {
            posterEl.style.display = 'block';
            posterEl.style.backgroundImage = `url('${player.poster()}')`;
            posterEl.style.backgroundSize = 'cover';
            posterEl.style.backgroundRepeat = 'no-repeat';
            posterEl.style.backgroundPosition = 'center';
            if (meta.audio_visualizer) enableVisualizer(player);
        }
    }
    else
    {
        if (meta.audio_visualizer) disableVisualizer(player);
        if (videoEl) videoEl.style.display = 'block';
        if (posterEl)
        {
            posterEl.style.display = '';
            posterEl.style.backgroundImage = '';
        }
    }
}


function setVideoQuality(height = 0, button = null)
{
    console.log(`Setting video quality to ${height}`)
    let menu = player.controlBar.SettingsButton.resolutionSwitcher.menu;
    if (abortController) abortController.abort();
    abortController = new AbortController();
    const signal = abortController.signal;
    const urlParams = new URLSearchParams(window.location.search);
    const buttons = menu.querySelectorAll('.vjs-resolution-option');
    if (height === 0)
    {
        height = urlParams.get('quality');
    }
    urlParams.set('quality', height);
    if (button == null)
    {
        buttons.forEach(b => {
            if ((b.textContent.toLowerCase().includes(height)) || (b.textContent == 'Direct' && height == '')) button = b;
        });
    }
    history.replaceState(null, '', `${window.location.pathname}?${urlParams.toString()}`);
    const hlsEnabled = height != null && height != '' && height != 'null' && height != 'audio';
    if (hlsEnabled)
    {
        console.log('HLS ENABLED');
        retryFetch(getVideoSource()[0])
            .then(response => response.text())
            .then(playlist => {
                function tryToFetchHLS()
                {
                    var segments = playlist.split('\n');
                    const segmentToDownload = String(Math.ceil((player.currentTime() + 5)/10)).padStart(4,'0') + ".ts";
                    var selectedSegment;
                    for (let i = 0; i < segments.length; i++) {
                        const segment = segments[i];
                        if (segment.endsWith('.ts'))
                        {
                            selectedSegment = segment;
                            if (segment.endsWith(segmentToDownload))
                                break;
                        }
                    }
                    retryFetch(selectedSegment, {}, undefined, undefined, undefined, true)
                        .then(response => {
                            applyVideoQuality();
                            buttons.forEach(btn => btn.classList.remove('vjs-menu-option-selected'));
                            button?.classList?.add('vjs-menu-option-selected');
                        })
                        .catch(error => {
                            console.log('HLS not ready. Retrying fetching...');
                            setTimeout(() => {
                                tryToFetchHLS();
                            }, 1000);
                        });
                }
                tryToFetchHLS();
        });
    }
    else
    {
        retryFetch(getVideoSource()[0], { signal }, undefined, undefined, undefined, true)
            .then(response => {
                applyVideoQuality();
                buttons.forEach(btn => btn.classList.remove('vjs-menu-option-selected'));
                button?.classList?.add('vjs-menu-option-selected');

                buttons.forEach(btn => btn.classList.remove('vjs-menu-option-selected'));
                button?.classList?.add('vjs-menu-option-selected');
            })
            .catch(error => {
                console.error('Error fetching new quality:', error);
            });
    }
}


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



class ZoomToFillToggle extends videojs.getComponent('Button')
{
    constructor(player, options)
    {
        super(player, options);
        this.addClass('vjs-zoom-control');
    }
    
    handleClick(event, state = null)
    {
        const video = player.el_.querySelector('video');
        var newState = video.style.objectFit == 'contain';
        if (state === false || state === true)
        {
            newState = state;
        }
        if (newState === true)
        {
            video.style.setProperty('object-fit', 'cover');
            this.el().innerHTML = '<span class="fa-solid fa-down-left-and-up-right-to-center"></span>';
            this.controlText('Restore Zoom');
        }
        else
        {
            video.style.setProperty('object-fit', 'contain');
            this.el().innerHTML = '<span class="fa-solid fa-up-right-and-down-left-from-center"></span>';
            this.controlText('Zoom to Fill');
        }
    };
}
videojs.registerComponent('ZoomToFillToggle', ZoomToFillToggle);


class PlayerButton extends videojs.getComponent('Button')
{
    constructor(player, options)
    {
        super(player, options);
        this.addClass('vjs-player-button');
        this.el().innerHTML = `<img src="/favicon.svg" width="50%">`;
        this.controlText(`Watch in ${document.querySelector('meta[property="og:site_name"]').getAttribute('content')}`);
    }

    handleClick(event, state = null)
    {
        window.open(window.location.href.replace('iframe', 'watch'), '_blank');
    }
}
videojs.registerComponent('PlayerButton', PlayerButton);


class SettingsButton extends videojs.getComponent('Button')
{
    constructor(player, options)
    {
        super(player, options);
        this.addClass('vjs-settings-button');
        this.controlText('Settings');
        this.el().innerHTML = '<i class="fa-solid fa-gear"></i>';

        this.menu = this.createSettingsMenu();
        this.el().appendChild(this.menu);

        this.resolutionSwitcher = new ResolutionSwitcherButton(player, options);
        this.subtitleSwitcher = new SubtitleSwitcherButton(player, options);
        this.playbackSpeedButton = new PlaybackSpeedButton(player, options);
        this.downloadButton = new DownloadButton(player, options);
        this.repeatButton = new RepeatButton(player, options);
        this.overAmplificationButton = new OverAmplificationButton(player, options);
        this.resolutionSwitcher.parent = this;
        this.subtitleSwitcher.parent = this;
        this.playbackSpeedButton.parent = this;
        this.downloadButton.parent = this;
        this.repeatButton.parent = this;

        this.menu.appendChild(this.resolutionSwitcher.el());
        this.menu.appendChild(this.subtitleSwitcher.el());
        this.menu.appendChild(this.playbackSpeedButton.el());
        this.menu.appendChild(this.downloadButton.el());
        this.menu.appendChild(this.repeatButton.el());
        this.menu.appendChild(this.overAmplificationButton.el());
    }

    closeAllSubmenus()
    {
        this.resolutionSwitcher.handleCloseMenu();
        this.subtitleSwitcher.handleCloseMenu();
        this.playbackSpeedButton.handleCloseMenu();
        this.downloadButton.handleCloseMenu();
        this.repeatButton.handleCloseMenu();
    }

    handleClick(event)
    {
        if (player.clickedChildMenuButton)
        {
            setTimeout(() => {player.clickedChildMenuButton = false;}, 100);
            return;
        }
        tryStopPropagation(event);
        if (this.menu.style.display === 'flex')
        {
            this.handleCloseMenu();
            this.closeAllSubmenus();
        }
        else
        {
            this.handleOpenMenu();
        }
    }

    handleOpenMenu()
    {
        this.menu.style.display = 'flex';
    }

    handleCloseMenu()
    {
        this.menu.style.display = 'none';
        player.clickedChildMenuButton = false;
    }

    createSettingsMenu()
    {
        const menu = document.createElement('div');
        menu.classList.add('vjs-settings-menu');
        menu.style.display = 'none';
        return menu;
    }

    updateResolutions()
    {
        this.resolutionSwitcher.updateResolutions();
    }

    updateSubtitles(subtitleList)
    {
        this.subtitleSwitcher.updateSubtitles(subtitleList);
    }
}
videojs.registerComponent('SettingsButton', SettingsButton);


class OverAmplificationButton extends videojs.getComponent('Button')
{
    constructor(player, options)
    {
        super(player, options);
        const urlParams = new URLSearchParams(window.location.search);
        this.addClass('menu-button');
        this.el().innerHTML = '<i class="fa-solid fa-bullhorn"></i>';
        this.enabled = false;
        this.gainNode = null;
        this.controlText('Over-Amplification');
    }

    handleClick(event, state = null)
    {
        setTimeout(() => {player.clickedChildMenuButton = false;}, 100);
        this.enabled = state != null ? state : !this.enabled;
        this.setUpGain(this.enabled);
    }

    setUpGain()
    {
        if (this.enabled)
        {
            if (this.gainNode === null)
            {
                setUpAudioContext();
                this.gainNode = new GainNode(audioContext);
                audioSource.disconnect(audioContext.destination);
                audioSource.connect(this.gainNode).connect(audioContext.destination);
            }
            this.el().classList.add('vjs-active');
            this.gainNode.gain.value = 2;
        }
        else
        {
            this.el().classList.remove('vjs-active');
            this.gainNode.gain.value = 1;
        }
    }
}
videojs.registerComponent('OverAmplificationButton', OverAmplificationButton);


class DownloadButton extends videojs.getComponent('Button')
{
    constructor(player, options)
    {
        super(player, options);
        this.addClass('menu-button');
        this.controlText('Download');
        this.startTime = null;
        this.endTime = null;
        this.startBtn = null;
        this.endBtn = null;
        this.parent = null;
        this.menu = this.createDownloadMenu();
        this.el().innerHTML = '<span class="fa-solid fa-download"></span>';
        this.el().appendChild(this.menu);
    }

    handleClick(event)
    {
        setTimeout(() => {player.clickedChildMenuButton = false;}, 100);
        tryStopPropagation(event);
        if (this.menu.style.display === 'block')
        {
            this.handleCloseMenu();
        }
        else
        {
            this.handleOpenMenu();
        }
    }

    handleOpenMenu()
    {
        this.parent.closeAllSubmenus();
        this.menu.style.display = 'block';
    }

    handleCloseMenu(propagate = false)
    {
        this.menu.style.display = 'none';
        if (this.parent && propagate)
        {
            this.parent.handleCloseMenu();
        }
    }

    updateTimeLabels()
    {
        if (this.startBtn != null)
            this.startBtn.innerHTML = "Start<br><div class=time_disp>" + formatTime(this.startTime) + "</div>";
        if (this.endBtn != null)
            this.endBtn.innerHTML = "End<br><div class=time_disp>" + formatTime(this.endTime) + "</div>";
    }

    createDownloadMenu()
    {
        const urlParams = new URLSearchParams(window.location.search);
        const baseDownloadUrl = `/download?${urlParams.toString()}`;

        const menu = document.createElement('div');
        menu.classList.add('vjs-setting-menu');
        menu.style.display = 'none'; // Initially hidden

        const options = [
            { quality: 'best', title: 'Highest Quality' },
            { quality: 'current', title: 'Current Quality' },
            { quality: 'audio', title: 'Audio Only' },
            { quality: 'trim', title: 'Trim Video' }
        ];

        options.forEach(option => {
            const button = document.createElement('button');
            button.textContent = option.title;
            button.classList.add('vjs-resolution-option');

            const handleEvent = (event) => {
                tryStopPropagation(event);
                if (option.quality == 'trim') {
                    if (this.startBtn.style.display === 'block')
                    {
                        this.startBtn.style.display = 'none';
                        this.endBtn.style.display = 'none';
                    }
                    else
                    {
                        this.startBtn.style.display = 'block';
                        this.endBtn.style.display = 'block';
                        this.startTime = null;
                        this.endTime = null;
                        this.updateTimeLabels();
                    }
                }
                else
                {
                    const urlParams = new URLSearchParams(window.location.search);
                    const originalUrl = urlParams.get('v') || urlParams.get('url');
                    const currentQuality = urlParams.get('quality') || meta.default_quality;
                    var quality = option.quality;
                    if (option.quality == 'current') quality = currentQuality;

                    const link = document.createElement('a');
                    link.href = `/download?url=${encodeURIComponent(originalUrl)}&quality=${quality}`;

                    if (this.startTime != null && this.endTime != null)
                        link.href += `&start=${this.startTime.toFixed(1)}&end=${this.endTime.toFixed(1)}`;

                    link.download = 'file';
                    document.body.appendChild(link);
                    link.click();
                    document.body.removeChild(link);

                    this.handleCloseMenu(true);
                    retryFetch(link.href)
                        .then(response => response.text())
                }
            };

            button.addEventListener('touchend', handleEvent);
            button.addEventListener('click', handleEvent);

            menu.appendChild(button);
        });

        this.startBtn = document.createElement('button');
        this.startBtn.classList.add('vjs-resolution-option');
        this.startBtn.title = 'Click To Adjust Start Time';
        this.startBtn.style.display = 'none'; // Initially hidden
        this.startBtn.addEventListener('touchend', (e) => { tryStopPropagation(e); this.startTime = player.currentTime(); this.updateTimeLabels(); });
        this.startBtn.addEventListener('click', (e) => { tryStopPropagation(e); this.startTime = player.currentTime(); this.updateTimeLabels(); });
        menu.appendChild(this.startBtn);

        this.endBtn = document.createElement('button');
        this.endBtn.classList.add('vjs-resolution-option');
        this.endBtn.title = 'Click To Adjust End Time';
        this.endBtn.style.display = 'none'; // Initially hidden
        this.endBtn.addEventListener('touchend', (e) => { tryStopPropagation(e); this.endTime = player.currentTime(); this.updateTimeLabels(); });
        this.endBtn.addEventListener('click', (e) => { tryStopPropagation(e); this.endTime = player.currentTime(); this.updateTimeLabels(); });
        menu.appendChild(this.endBtn);

        this.updateTimeLabels();

        return menu;
    }
}
videojs.registerComponent('DownloadButton', DownloadButton);


// TODO: Universal time range selection: Share between RepeatButton and DownloadButton, draggable markers on seekbar
class RepeatButton extends videojs.getComponent('Button')
{
    constructor(player, options)
    {
        super(player, options);
        this.addClass('menu-button');
        this.controlText('Repeat');
        this.el().innerHTML = '<i class="fa-solid fa-repeat"></i>';
        this.repeatActive = false;
        this.repeatStartTime = null;
        this.repeatEndTime = null;
        this.startBtn = null;
        this.endBtn = null;
        this.parent = null;
        this.menu = this.createRepeatMenu();
        this.el().appendChild(this.menu);
    }

    handleClick(event)
    {
        setTimeout(() => {player.clickedChildMenuButton = false;}, 100);
        tryStopPropagation(event);
        if (this.menu.style.display === 'block')
        {
            this.handleCloseMenu();
        }
        else
        {
            this.handleOpenMenu();
        }
    }

    handleOpenMenu()
    {
        this.parent.closeAllSubmenus();
        this.menu.style.display = 'block';
    }

    handleCloseMenu(propagate = false)
    {
        this.menu.style.display = 'none';
        if (this.parent && propagate)
        {
            this.parent.handleCloseMenu();
        }
    }

    updateTimeLabels()
    {
        if (this.startBtn != null)
            this.startBtn.innerHTML = "Start<br><div class=time_disp>" + formatTime(this.repeatStartTime) + "</div>";
        if (this.endBtn != null)
            this.endBtn.innerHTML = "End<br><div class=time_disp>" + formatTime(this.repeatEndTime) + "</div>";
    }

    createRepeatMenu()
    {
        const menu = document.createElement('div');
        menu.classList.add('vjs-setting-menu');
        menu.style.display = 'none';

        const toggleButton = document.createElement('button');
        toggleButton.textContent = 'Toggle Repeat';
        toggleButton.classList.add('vjs-resolution-option');
        toggleButton.addEventListener('click', (e) => {
            tryStopPropagation(e);
            this.repeatActive = !this.repeatActive;
            if (this.repeatActive)
            {
                this.addClass('vjs-active');
                this.controlText('Repeat Active');
                this.repeatStartTime = 0;
                this.repeatEndTime = player.duration();
                this.updateTimeLabels();
            }
            else
            {
                this.removeClass('vjs-active');
                this.controlText('Toggle Repeat');
            }
            repeatMode = this.repeatActive;
            repeatStartTime = this.repeatStartTime;
            repeatEndTime = this.repeatEndTime;
        });
        toggleButton.ontouchstart = (event) => {
            setTimeout(() => {
                event.preventDefault();
                tryStopPropagation(event);
                toggleButton.click();
            }, 200);
        };
        menu.appendChild(toggleButton);

        this.startBtn = document.createElement('button');
        this.startBtn.classList.add('vjs-resolution-option');
        this.startBtn.title = 'Click To Adjust Start Time';
        this.startBtn.addEventListener('click', (e) => { tryStopPropagation(e); this.repeatStartTime = player.currentTime(); this.updateTimeLabels(); repeatStartTime = this.repeatStartTime; });

        this.startBtn.ontouchstart = (event) => {
            setTimeout(() => {
                event.preventDefault();
                tryStopPropagation(event);
                this.startBtn.click();
            }, 200);
        };
        menu.appendChild(this.startBtn);

        this.endBtn = document.createElement('button');
        this.endBtn.classList.add('vjs-resolution-option');
        this.endBtn.title = 'Click To Adjust End Time';
        this.endBtn.addEventListener('click', (e) => { tryStopPropagation(e); this.repeatEndTime = player.currentTime(); this.updateTimeLabels(); repeatEndTime = this.repeatEndTime; });

        this.endBtn.ontouchstart = (event) => {
            setTimeout(() => {
                event.preventDefault();
                tryStopPropagation(event);
                this.endBtn.click();
            }, 200);
        };
        menu.appendChild(this.endBtn);

        this.updateTimeLabels();

        return menu;
    }
}
videojs.registerComponent('RepeatButton', RepeatButton);


class ResolutionSwitcherButton extends videojs.getComponent('Button')
{
    constructor(player, options)
    {
        super(player, options);
        this.addClass('menu-button');
        this.controlText('Resolution');
        this.el().innerHTML = '<i class="fa-solid fa-sliders"></i>';
        this.el().style.display = 'none';
        
        this.parent = null;
        this.menu = this.createResolutionMenu();
        this.el().appendChild(this.menu);
    }

    handleClick(event)
    {
        setTimeout(() => {player.clickedChildMenuButton = false;}, 100);
        tryStopPropagation(event);
        if (this.menu.style.display === 'block')
        {
            this.menu.style.display = 'none';
        }
        else
        {
            this.handleOpenMenu();
        }
    }

    handleOpenMenu()
    {
        this.parent.closeAllSubmenus();
        this.menu.style.display = 'block';
    }

    handleCloseMenu(propagate = false)
    {
        this.menu.style.display = 'none';
        if (this.parent && propagate)
        {
            this.parent.handleCloseMenu();
        }
    }


    updateResolutions()
    {
        let resolutions = meta.formats;
        if (!resolutions || resolutions.length < 1) return;
        this.el().style.display = '';
        this.menu.innerHTML = ''
        
        resolutions.sort((a, b) => (b.height || b) - (a.height || a)); // Sort descending
        if (!resolutions.includes('audio')) resolutions.push('audio');
        if (!resolutions.includes('direct')) resolutions.push('direct');
        
        resolutions.forEach(resItem => {
            const height = resItem === 'audio' ? 'audio' : resItem === 'direct' ? '' : (resItem.height || resItem);
            if (typeof height !== 'number' && height !== 'audio' && height !== '') return;
            
            const button = document.createElement('button');
            button.textContent = height === 'audio' ? 'Audio' : height === '' ? 'Direct' : `${height}p`;
            button.classList.add('vjs-resolution-option');
            const urlParams = new URLSearchParams(window.location.search);
            if (urlParams.get('quality') == height || (urlParams.get('quality') == null && height == ''))
            {
                button.classList.add('vjs-menu-option-selected');
            }

            var moved = false;
            button.ontouchstart = (event) => {
                setTimeout(() => {
                    if (moved) return;
                    event.preventDefault();
                    tryStopPropagation(event);
                    button.click();
                }, 200);
                moved = false;
            };

            button.ontouchmove = (event) => {
                moved = true;
            };


            button.onclick = (event) => {
                tryStopPropagation(event);
                setVideoQuality(height, button);
                this.handleCloseMenu(true);
            };
            this.menu.appendChild(button);
        });
    }


    createResolutionMenu()
    {
        const menu = document.createElement('div');
        menu.classList.add('vjs-setting-menu');
        menu.style.display = 'none';
        return menu;
    }
}
videojs.registerComponent('ResolutionSwitcherButton', ResolutionSwitcherButton);


class SubtitleSwitcherButton extends videojs.getComponent('Button')
{
    constructor(player, options)
    {
        super(player, options);
        this.addClass('menu-button');
        this.controlText('Subtitles');
        this.el().innerHTML = '<i class="fa-solid fa-closed-captioning"></i>';
        this.el().style.display = 'none';

        this.parent = null;
        this.menu = this.createSubtitleMenu();
        this.el().appendChild(this.menu);

        this.subtitles = {};
    }

    handleClick(event)
    {
        setTimeout(() => {player.clickedChildMenuButton = false;}, 100);
        tryStopPropagation(event);
        if (this.menu.style.display === 'block')
        {
            this.menu.style.display = 'none';
        }
        else
        {
            this.handleOpenMenu();
        }
    }

    handleOpenMenu()
    {
        this.parent.closeAllSubmenus();
        this.menu.style.display = 'block';
    }

    handleCloseMenu(propagate = false)
    {
        this.menu.style.display = 'none';
        if (this.parent && propagate)
        {
            this.parent.handleCloseMenu();
        }
    }

    updateSubtitles(subtitleList)
    {
        if (!subtitleList || subtitleList.length === 0) return;
        this.el().style.display = '';

        // Prepend "none" to the subtitle list
        subtitleList.unshift('none');

        // Sort subtitle languages alphabetically (excluding "none")
        const sortedSubtitleList = subtitleList.slice(1).sort();
        sortedSubtitleList.unshift('none'); // Add "none" back to the beginning

        sortedSubtitleList.forEach(lang => {
            const button = document.createElement('button');
            button.textContent = lang === 'none' ? 'None' : lang;
            button.classList.add('vjs-subtitle-option');


            var moved = false;
            button.ontouchstart = (event) => {
                setTimeout(() => {
                    if (moved) return;
                    event.preventDefault();
                    tryStopPropagation(event);
                    button.click();
                }, 200);
                moved = false;
            };

            button.ontouchmove = (event) => {
                moved = true;
            };


            button.onclick = (event) => {
                tryStopPropagation(event);
                this.handleSubtitleSelection(lang);
                this.menu.querySelectorAll('.vjs-subtitle-option').forEach(btn => {
                    btn.classList.remove('vjs-menu-option-selected');
                });
                button.classList.add('vjs-menu-option-selected');

                this.handleCloseMenu(true);
            };
            this.menu.appendChild(button);
        });
    }

    handleSubtitleSelection(lang)
    {
        let tracks = player.textTracks();
        if (lang !== 'none')
        {
            const urlParams = new URLSearchParams(window.location.search);
            const subtitleSrc = `/subtitle?${urlParams.toString()}&lang=${lang}`;
            retryFetch(subtitleSrc)
                .then(response => response.text())
            
            let trackExists = false;
            for (let i = 0; i < tracks.length; i++)
            {
                if (tracks[i].kind === 'subtitles' && tracks[i].language === lang && tracks[i].src === subtitleSrc)
                {
                    trackExists = true;
                    break;
                }
            }
            if (!trackExists)
            {
                player.addRemoteTextTrack({
                    kind: 'subtitles',
                    src: subtitleSrc,
                    srclang: lang,
                    label: lang
                });
            }
            this.el().classList.add('vjs-active');
        }
        else
        {
            this.el().classList.remove('vjs-active');
        }

        tracks = player.textTracks();
        for (let i = 0; i < tracks.length; i++)
        {
            if (tracks[i].kind === 'subtitles')
            {
                if (tracks[i].language === lang)
                {
                    tracks[i].mode = 'showing';
                }
                else
                {
                    tracks[i].mode = 'disabled';
                }
            }
        }
    }

    createSubtitleMenu() {
        const menu = document.createElement('div');
        menu.classList.add('vjs-setting-menu');
        menu.style.display = 'none';
        return menu;
    }
}
videojs.registerComponent('SubtitleSwitcherButton', SubtitleSwitcherButton);


class PlaybackSpeedButton extends videojs.getComponent('Button')
{
    constructor(player, options)
    {
        super(player, options);
        this.player = player;
        this.addClass('menu-button');
        this.controlText('Playback Speed');
        this.el().innerHTML = '<i class="fa-solid fa-forward"></i>';

        this.parent = null;
        this.menu = this.createPlaybackSpeedMenu();
        this.el().appendChild(this.menu);
    }

    handleClick(event)
    {
        setTimeout(() => {player.clickedChildMenuButton = false;}, 100);
        tryStopPropagation(event);
        if (this.menu.style.display === 'flex')
            this.menu.style.display = 'none';
        else
            this.handleOpenMenu();
    }

    handleOpenMenu()
    {
        this.parent.closeAllSubmenus();
        this.menu.style.display = 'flex';
    }

    handleCloseMenu(propagate = false)
    {
        this.menu.style.display = 'none';
        if (this.parent && propagate)
        {
            this.parent.handleCloseMenu();
        }
    }

    createPlaybackSpeedMenu()
    {
        const menu = document.createElement('div');
        menu.classList.add('vjs-setting-menu');
        menu.style.display = 'none';

        const speeds = [0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0];
        speeds.forEach(speed => {
            const button = document.createElement('button');
            button.textContent = `${speed}x`;
            button.classList.add('vjs-playback-speed-option');
            if (this.player && this.player.playbackRate() === speed)
            {
                button.classList.add('vjs-menu-option-selected');
            }


            var moved = false;
            button.ontouchstart = (event) => {
                setTimeout(() => {
                    if (moved) return;
                    event.preventDefault();
                    tryStopPropagation(event);
                    button.click();
                }, 200);
                moved = false;
            };

            button.ontouchmove = (event) => {
                moved = true;
            };


            button.onclick = (event) => {
                tryStopPropagation(event);
                this.player.playbackRate(speed);
                if (speed == 1.0)
                    this.el().classList.remove('vjs-active');
                else
                    this.el().classList.add('vjs-active');

                this.menu.querySelectorAll('.vjs-playback-speed-option').forEach(btn => {
                    btn.classList.remove('vjs-menu-option-selected');
                });
                button.classList.add('vjs-menu-option-selected');

                this.handleCloseMenu(true);
            };
            menu.appendChild(button);
        });
        return menu;
    }
}
videojs.registerComponent('PlaybackSpeedButton', PlaybackSpeedButton);


const Component = videojs.getComponent('Component');

class TitleBar extends Component
{
    constructor(player, options = {})
    {
        super(player, options);

        if (options.title)
        {
            this.updateTextContent(options.title, options.uploader);
        }
    }

    createEl()
    {
        return videojs.dom.createEl('div', {
            className: 'vjs-title-bar'
        }, {
            'aria-label': 'Video Title'
        });
    }

    updateTextContent(title, uploader)
    {
        videojs.emptyEl(this.el());
        videojs.appendContent(this.el(), videojs.dom.createEl('div', { className: 'vjs-title-bar-text' }, {}, title));
        if (uploader)
        {
            videojs.appendContent(this.el(), videojs.dom.createEl('div', { className: 'vjs-uploader-text' }, {}, uploader));
        }
    }
}

videojs.registerComponent('TitleBar', TitleBar);


class PlaylistComponent extends Component
{
    constructor(player, options = {})
    {
        super(player, options);
        this.options = options;
        this.player = player;
        this.addClass('vjs-playlist-component');
        var params = new URLSearchParams(window.location.search);
        this.currentVideoUrl = params.get('v') || params.get('url');

        this.menu = this.createPlaylistMenu();
        this.el().appendChild(this.menu);

        this.toggleButton = this.createToggleButton();
        this.el().appendChild(this.toggleButton);

        if (options.playlistData)
        {
            this.updatePlaylist(options.playlistData);
        }
    }

    createEl()
    {
        return videojs.dom.createEl('div', {
            className: 'vjs-playlist-container'
        });
    }

    createToggleButton()
    {
        const button = videojs.dom.createEl('button', {
            className: 'vjs-playlist-toggle-button',
            id: 'vjs-playlist-toggle-button'
        });
        videojs.appendContent(button, videojs.dom.createEl('i', { className: 'fa-solid fa-list-ul' }));

        button.addEventListener('click', () => {
            this.toggleClass('active');
        });
        return button;
    }

    createPlaylistMenu()
    {
        const menu = videojs.dom.createEl('ul', {
            className: 'vjs-playlist-items'
        });
        return menu;
    }

    updatePlaylist(playlistData)
    {
        videojs.emptyEl(this.menu);
        playlistData.forEach(item => {
            const listItem = videojs.dom.createEl('li', {
                className: 'vjs-playlist-item'
            });

            console.log(`Item URL: ${item.url}, self URL: ${this.currentVideoUrl}`);

            if (item.url === this.currentVideoUrl)
            {
                listItem.classList.add('vjs-current-video');
            }

            const link = videojs.dom.createEl('a', {
                href: `${window.location.pathname}?url=${encodeURIComponent(item.url)}`
            });

            const thumbnail = videojs.dom.createEl('img', {
                src: `/thumb?url=${encodeURIComponent(item.url)}`,
                alt: item.title,
                className: 'vjs-playlist-thumbnail'
            });

            const info = videojs.dom.createEl('div', {
                className: 'vjs-playlist-info'
            });

            const title = videojs.dom.createEl('div', {
                className: 'vjs-playlist-title'
            }, {}, item.title);

            const uploader = videojs.dom.createEl('div', {
                className: 'vjs-playlist-uploader'
            }, {}, item.uploader);

            const duration = videojs.dom.createEl('div', {
                className: 'vjs-playlist-duration'
            }, {}, formatTimeShort(item.duration));

            videojs.appendContent(link, thumbnail);
            videojs.appendContent(link, duration);
            videojs.appendContent(link, info);
            videojs.appendContent(listItem, link);
            videojs.appendContent(info, title);
            videojs.appendContent(info, uploader);
            videojs.appendContent(this.menu, listItem);
        });
    }
}
videojs.registerComponent('PlaylistComponent', PlaylistComponent);


function skipclick()
{
    if (player && player.currentTime() < skipTime) player.currentTime(skipTime);
};


function adjustVideoSize()
{
    const videoElement = player.el_.querySelector('video');

    const width = videoElement.videoWidth || parseInt(meta['width']) || 720;
    const height = videoElement.videoHeight || parseInt(meta['height']) || 480;
    const innerWidth = window.innerWidth * 0.9;
    const innerHeight = window.innerHeight * 0.9;
    
    const min_dim = Math.min(innerWidth, innerHeight);
    const min_width = (min_dim + innerWidth) / 2;
    const min_height = (min_dim + innerHeight) / 2;
    
    const scaling = Math.min(min_width / width, min_height / height);
    
    player.el_.style.width = width * scaling + 'px';
    player.el_.style.height = height * scaling + 'px';
}


function checkSponsorTime()
{
    var segmentShown = null;
    const currentTime = player.currentTime();
    
    segments.forEach(segment => {
        if (currentTime > segment.start && currentTime < segment.end)
        {
            segmentShown = segment;
        }
    });
    
    if (segmentShown == null)
    {
        skipSegment.style.opacity = 0;
        skipSegment.style.transform = 'translate(120%, 0)';

        if ( "mediaSession" in navigator)
        {
            navigator.mediaSession.metadata.album = "";
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

        if ( "mediaSession" in navigator)
        {
            navigator.mediaSession.metadata.album = `[${segmentShown.category.replaceAll('_', ' ')}]`;
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
    const duration = player.duration();
    const sbContainer = document.querySelector('.vjs-progress-holder.vjs-slider.vjs-slider-horizontal');
    const existingSegments = sbContainer.querySelectorAll('.seg');
    existingSegments.forEach(el => el.remove());
    
    data.forEach(entry => {
        const indicator = document.createElement('div');
        sbContainer.appendChild(indicator);
        
        const startPosition = (entry.start / duration) * 100;
        const endPosition = (entry.end / duration) * 100;
        const width = endPosition - startPosition;
        
        if (entry.category == 'poi_highlight') indicator.style.aspectRatio = 1;
        else indicator.style.width = `${width}%`;
        
        indicator.className = 'seg';
        indicator.style.left = `${startPosition}%`;
        indicator.style.backgroundColor = sbColorMap[entry.category] || '#ffffff';
        indicator.title = `${entry.category.replaceAll('_', ' ')}`;
    });
}


function loadVideo()
{
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.toString().length < 10) return;
    
    videojs.options.languages.en = videojs.mergeOptions(videojs.options.languages.en, {
        "Play": "Play [Space]",
        "Pause": "Pause [Space]",
        "Fullscreen": "Fullscreen [f]",
        "Exit Fullscreen": "Exit Fullscreen [f]",
        "Mute": "Mute [m]",
        "Unmute": "Unmute [m]",
        "Zoom to Fill" : "Zoom to Fill [g]",
        "Restore Zoom" : "Restore Zoom [g]",
        "Picture-in-Picture" : "Picture-in-Picture [p]",
    });
    
    player = videojs('videoPlayer', {
        controls: false,
        preload: 'auto',
        responsive: true,
        fluid: true,
        poster: `/thumb?${urlParams.toString()}`,
        enableSmoothSeeking: true,
        disableSeekWhileScrubbingOnMobile: true,
        html5:
        {
            hls:
            {
                withCredentials: true
            }
        },
        controlBar:
        {
            children:
            [
                'playToggle',
                'volumePanel',
                'CurrentTimeDisplay',
                'TimeDivider',
                'DurationDisplay',
                'progressControl',
                'SettingsButton',
                'PictureInPictureToggle',
                'ZoomToFillToggle',
                'fullscreenToggle'
            ]
        },
        plugins:
        {
            hotkeys:
            {
                customKeys:
                {
                    sbKey:
                    {
                        key: function (event) {return event.code == "Enter";},
                        handler: function (player, options, event) {skipclick();},
                    },
                    zoomKey:
                    {
                        key: function (event) {return event.code == "KeyG";},
                        handler: function (player, options, event) {document.querySelector('.vjs-zoom-control').click();},
                    },
                    pipKey:
                    {
                        key: function (event) {return event.code == "KeyP";},
                        handler: function (player, options, event) {document.querySelector('.vjs-picture-in-picture-control').click();},
                    },
                    preciseBackwardKey:
                    {
                        key: function (event) {return event.code == "Comma";},
                        handler: function (player, options, event) {player.currentTime(player.currentTime() - 0.1);},
                    },
                    preciseForwardKey:
                    {
                        key: function (event) {return event.code == "Period";},
                        handler: function (player, options, event) {player.currentTime(player.currentTime() + 0.1);},
                    },
                },
                captureDocumentHotkeys: true,
                documentHotkeysFocusElementFilter: e => e.tagName.toLowerCase() === 'body',
                enableHoverScroll: true,
            },
        },
    });
    player.doubleTapFF();
    player.controlBar.ZoomToFillToggle.handleClick(null, state = false);
    if (window.location.href.includes('/iframe?')) player.controlBar.addChild('PlayerButton');
    
    const spacer = document.createElement('div');
    player.el_.querySelector('.vjs-control-bar').appendChild(spacer);
    spacer.style="flex: auto;order: 3;";
    
    skipSegment = document.createElement('div');
    player.el_.appendChild(skipSegment);
    skipSegment.id = "skipsegment";
    skipSegment.onclick = function() {skipclick();};

    player.on('timeupdate', () => {
        if (repeatMode && player.currentTime() >= repeatEndTime)
        {
            player.currentTime(repeatStartTime);
            setTimeout(() => {
                player.play();
            }, 100);
        }
    });

    const errorDisplay = player.el_.querySelector('.vjs-error-display');
    errorDisplay.classList.add('spinner-parent');
    errorDisplay.querySelector('.vjs-modal-dialog-content').classList.add('spinner-body');
    
    const spinnerBody = document.createElement('div');
    const spinnerParent = player.el_.querySelector('.vjs-loading-spinner')
    spinnerParent.appendChild(spinnerBody);
    spinnerBody.classList.add('spinner-body');
    spinnerParent.classList.add('spinner-parent');
    
    document.getElementById('video').style.filter = 'brightness(1)';

    player.el_.querySelector('.vjs-poster').style.filter = '';

    const originalUrl = urlParams.get('v') || urlParams.get('url');
    player.src({ src: `/direct?url=${encodeURIComponent(originalUrl)}`, type: 'video/mp4' });

    // When video is loaded
    player.on('loadeddata', () => {
        player.el_.style.transitionDuration = '1s';
        player.el_.querySelector('img').classList.add('loaded-img');
        adjustVideoSize();
        window.addEventListener('resize', adjustVideoSize);
        setTimeout(() => {player.el_.style.transitionDuration = '0s';}, 1000);
        player.controls(true);
        errorDisplay.classList.remove('spinner-parent');
        errorDisplay.querySelector('.vjs-modal-dialog-content').classList.remove('spinner-body');
        player.el_.querySelector('.vjs-control-bar').classList.add('display-flex');

        if (meta.chapters.length > 0)
            loadChapters();
    });
    retryFetch(`/meta?${urlParams.toString()}`)
        .then(response => response.json())
        .then(metaData => {
            meta = metaData;
            if (meta["error"] !== undefined)
            {
                displayPlayerError(meta['error']);
                return;
            }
            if (player.controlBar && player.controlBar.SettingsButton)
            {
                player.controlBar.SettingsButton.updateResolutions();
                player.controlBar.SettingsButton.updateSubtitles(meta.subtitles);

                if (urlParams.get('quality') == null && meta.load_default_quality)
                {
                    setVideoQuality(meta.default_quality);
                }
                else
                {
                    setVideoQuality();
                }
            }

            if (typeof meta.title == 'string' && meta.title != '')
            {
                const appTitle = document.querySelector('meta[property="og:site_name"]').getAttribute('content');
                const titleLength = 80 - (' | ' + appTitle).length;
                meta.shortTitle = meta.title.length > titleLength ? meta.title.substring(0, titleLength - 3) + "..." : meta.title;
                player.addChild('TitleBar', { title: meta.title, uploader: meta.uploader });
                document.title = meta.shortTitle + ' | ' + appTitle;
                meta.uploader = meta.uploader? meta.uploader : appTitle;
            }

            try
            {
                const spriteElement = document.getElementById('enable-sprite');
                const spriteDuration = parseFloat(spriteElement ? spriteElement.dataset.spriteDuration : null);
                const videoLength = parseInt(meta.duration);
    
                if (spriteElement && !isNaN(spriteDuration) && videoLength < spriteDuration)
                {
                    player.spriteThumbnails({ url: `/sprite?${urlParams.toString()}`, width: 160, height: 90, columns: 10, interval: 10 });
                    player.spriteThumbnails().setState({ready: false});
                    retryFetch(`/sprite?${urlParams.toString()}`, { visible: false }).then(response => {
                        player.spriteThumbnails().setState({ready: true});
                    });
                }
            }
            catch {}

            player.load();
            player.on('error', () => {
                const error = player.error();
                if (error && error.code === 4)
                {
                    if (player.src().includes('/direct') && meta.formats.length > 1)
                    {
                        setTimeout(() => {
                            console.warn("Changing video quality due to unsupported format...");
                            setVideoQuality(meta.default_quality);
                        }, 500);
                    }
                }
            });
            try
            {
                loadMediaPlayer();
            }
            catch {}

            if (meta.playlist_support == true && window.location.pathname != '/iframe')
            {
                retryFetch(`/playlist?url=${encodeURIComponent(urlParams.get('v') || urlParams.get('url'))}`)
                    .then(response => response.json())
                    .then(playlistData => {
                        if (Array.isArray(playlistData) && playlistData.length > 0)
                        {
                            player.addChild('PlaylistComponent', { playlistData: playlistData });
                        }
                    });
            }

            setInterval(()=>{ retryFetch(getVideoSource()[0], {}, 0, undefined, false, true).then(response => response.ok); }, 120000); // Keepalive

            if (meta.auto_bg_playback && navigator?.userAgentData?.mobile)
            {
                document.addEventListener('visibilitychange', () => {
                    if (meta.audio_visualizer)
                    {
                        if (document.visibilityState === 'hidden') pauseVisualizer(player);
                        else resumeVisualizer(player);
                    }
                    if (player.isInPictureInPicture()) return;
                    if (document.visibilityState === 'hidden')
                    {
                        if (!player.src().includes('&quality=audio')) // assume audio always works
                        {
                            ps.save();
                            player.src({ src: `/download?url=${encodeURIComponent(originalUrl)}&quality=audio`, type: 'audio/mpeg' });
                            ps.apply();
                        }
                    }
                    else
                    {
                        const urlParams = new URLSearchParams(window.location.search);
                        if (urlParams.get('quality') != 'audio')
                        {
                            setVideoQuality();
                        }
                    }
                });
            }

        })
        .catch(error => {
            displayPlayerError(`Error: ${error.message}`);
        });

        
    retryFetch(`/sb?${urlParams.toString()}`)
        .then(response => response.json())
        .then(data => {
            if (Array.isArray(data)) {
                segments = data;
                player.on('loadeddata', () => {
                    addSponsorblock(data);
                });
                player.on('timeupdate', checkSponsorTime);
            }
        });
    document.addEventListener('click', (e) => {
        player.el_.focus();
    });
}


function loadMediaPlayer()
{
    if (! "mediaSession" in navigator) return;

    const urlParams = new URLSearchParams(window.location.search);
    navigator.mediaSession.metadata = new MediaMetadata({
        title: meta.shortTitle,
        artist: meta.uploader,
        album: "",
        artwork: [
            {
                src: `/thumb?${urlParams.toString()}`,
                sizes: "512x512",
                type: "image/png",
            },
        ],
    });

    navigator.mediaSession.setActionHandler("seekbackward", (details) => {
        player.currentTime(player.currentTime() - (details.seekOffset || 10));
    });
    navigator.mediaSession.setActionHandler("seekforward", (details) => {
        player.currentTime(player.currentTime() + (details.seekOffset || 10));
    });
    navigator.mediaSession.setActionHandler("seekto", (details) => {
        player.currentTime(details.seekTime);
    });
    navigator.mediaSession.setActionHandler("previoustrack", null);
    navigator.mediaSession.setActionHandler("nexttrack", null);
    console.log("Loaded Media Player API");
}


loadVideo();
