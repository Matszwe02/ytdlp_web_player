const videoSource = document.getElementById('videoSource');
const videoPlayer = document.getElementById('videoPlayer');
let player;
let playerContainer;
let skipSegment;
let skipTime = 0;
let currentVideoQuality = null;
let meta = null;
let activeFetches = 0; // Counter for active retryFetch calls
let abortController = null; // AbortController for cancelling fetches
let repeatMode = false;
let repeatStartTime = 0;
let repeatEndTime = 0;


function tryStopPropagation(event)
{
    try
    {
        event.stopPropagation();
    }
    catch (error) {}
}


function chooseGoodQuality()
{
    let targetQuality = 720
    let closestQuality = Infinity;
    for (const quality of meta.formats)
    {
        if (quality >= targetQuality && closestQuality > targetQuality)
        {
            closestQuality = quality;
        }
    }
    if (closestQuality === Infinity) closestQuality = 720;
    console.log(`Choosing quality ${closestQuality} for current video`);
    return closestQuality;
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


async function retryFetch(url, options = {}, retries = 5, delay = 5000, visible = true)
{
    if (visible) addFetch();
    try
    {
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
        if (player != null) {
            console.log(`Fetching "${url}" called from ${callerInfo}`);
            const response = await fetch(url, options);
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
        console.error(`Fetch failed, retrying in ${delay / 1000} seconds...`, error);
        if (retries > 0)
        {
            await new Promise(resolve => setTimeout(resolve, delay));
            return retryFetch(url, options, retries - 1, delay);
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


function getVideoSource()
{
    const urlParams = new URLSearchParams(window.location.search);
    const originalUrl = urlParams.get('v') || urlParams.get('url');
    const quality = urlParams.get('quality') || currentVideoQuality;
    const hlsEnabled = urlParams.get('hls') != 'false' && quality != null && quality != 'audio';
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
        downloadUrl = quality ? `/download?url=${encodeURIComponent(originalUrl)}&quality=${quality}` : `/fastest?url=${encodeURIComponent(originalUrl)}`;
        videoType = 'video/mp4';
    }
    return [downloadUrl, videoType];
}


function applyVideoQuality()
{
    const urlParams = new URLSearchParams(window.location.search);
    const quality = urlParams.get('quality') || currentVideoQuality;
    const videoSource = getVideoSource();

    const videoEl = player.el().querySelector('video');
    const posterEl = player.el().querySelector('.vjs-poster');
    player.src({ src: videoSource[0], type: videoSource[1] });

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
        }
    }
    else
    {
        if (videoEl) videoEl.style.display = 'block';
        if (posterEl)
        {
            posterEl.style.display = '';
            posterEl.style.backgroundImage = '';
        }
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
        const video = player.el().querySelector('video');
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


class HLSToggleButton extends videojs.getComponent('Button')
{
    constructor(player, options)
    {
        super(player, options);
        const urlParams = new URLSearchParams(window.location.search);
        this.addClass('menu-button');
        this.el().innerHTML = '<i class="fa-solid fa-video"></i>';
        this.hlsEnabled = urlParams.get('hls') != 'false';
        this.updateHlsState();
    }

    handleClick(event, state = null)
    {
        this.hlsEnabled = state != null ? state : !this.hlsEnabled;
        this.updateHlsState();
        if (this.hlsEnabled)
        {
            // TODO: Refetch with new timestamps, join logic with `updateResolutions`
            retryFetch(getVideoSource()[0])
                .then(response => response.text())
                .then(playlist => {
                    var segments = playlist.split('\n');
                    const segmentToDownload = String(Math.ceil(player.currentTime()/10)).padStart(4,'0') + ".ts";
                    segments.forEach(segment => {
                        console.log(`try ${segment} with ${segmentToDownload}`);
                        if (segment.endsWith(segmentToDownload))
                        {
                            console.log(`found ${segment}`);
                            retryFetch(segment)
                                .then(response => {
                                    const switchTime = player.currentTime();
                                    const isPlaying = !player.paused();
                                    applyVideoQuality();
                                    player.currentTime(switchTime);
                                    if (isPlaying) player.play();
                                });
                        }
                    });
                }
            );
        }
        else
        {
            applyVideoQuality();
        }
    }

    updateHlsState()
    {
        const urlParams = new URLSearchParams(window.location.search);
        if (this.hlsEnabled)
        {
            this.el().classList.add('vjs-active');
            this.controlText('HLS Streaming: On');
            urlParams.delete('hls');
        }
        else
        {
            this.el().classList.remove('vjs-active');
            this.controlText('HLS Streaming: Off');
            urlParams.set('hls', 'false');
        }
        history.replaceState(null, '', `${window.location.pathname}?${urlParams.toString()}`);
    }
}
videojs.registerComponent('HLSToggleButton', HLSToggleButton);


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
        this.hlsToggleButton = new HLSToggleButton(player, options);
        this.resolutionSwitcher.parent = this;
        this.subtitleSwitcher.parent = this;
        this.playbackSpeedButton.parent = this;
        this.downloadButton.parent = this;
        this.repeatButton.parent = this;
        this.hlsToggleButton.parent = this;

        this.menu.appendChild(this.resolutionSwitcher.el());
        this.menu.appendChild(this.subtitleSwitcher.el());
        this.menu.appendChild(this.playbackSpeedButton.el());
        this.menu.appendChild(this.downloadButton.el());
        this.menu.appendChild(this.repeatButton.el());
        this.menu.appendChild(this.hlsToggleButton.el());
    }

    handleClick(event)
    {
        tryStopPropagation(event);
        if (this.menu.style.display === 'flex')
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
        this.menu.style.display = 'flex';
    }

    handleCloseMenu()
    {
        this.menu.style.display = 'none';
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


class DownloadButton extends videojs.getComponent('Button')
{
    constructor(player, options)
    {
        super(player, options);
        this.addClass('menu-button');
        this.controlText('Download Video');
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
        menu.classList.add('vjs-resolution-menu');
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
                    const currentQuality = urlParams.get('quality') || currentVideoQuality || chooseGoodQuality();
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


class RepeatButton extends videojs.getComponent('Button')
{
    constructor(player, options)
    {
        super(player, options);
        this.addClass('menu-button');
        this.controlText('Toggle Repeat');
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
        menu.classList.add('vjs-repeat-menu');
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
        menu.appendChild(toggleButton);

        this.startBtn = document.createElement('button');
        this.startBtn.classList.add('vjs-resolution-option');
        this.startBtn.title = 'Click To Adjust Start Time';
        this.startBtn.addEventListener('click', (e) => { tryStopPropagation(e); this.repeatStartTime = player.currentTime(); this.updateTimeLabels(); repeatStartTime = this.repeatStartTime; });
        menu.appendChild(this.startBtn);

        this.endBtn = document.createElement('button');
        this.endBtn.classList.add('vjs-resolution-option');
        this.endBtn.title = 'Click To Adjust End Time';
        this.endBtn.addEventListener('click', (e) => { tryStopPropagation(e); this.repeatEndTime = player.currentTime(); this.updateTimeLabels(); repeatEndTime = this.repeatEndTime; });
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
        this.controlText('Select Resolution');
        this.el().innerHTML = '<i class="fa-solid fa-sliders"></i>';
        this.el().style.display = 'none';
        
        this.parent = null;
        this.menu = this.createResolutionMenu();
        this.el().appendChild(this.menu);
    }

    handleClick(event)
    {
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
        this.menu.style.display = 'block';
    }

    handleCloseMenu()
    {
        this.menu.style.display = 'none';
        if (this.parent)
        {
            this.parent.handleCloseMenu();
        }
    }


    updateResolutions()
    {
        let resolutions = meta.formats;
        if (!resolutions || resolutions.length < 2) return;
        this.el().style.display = '';
        this.menu.innerHTML = ''
        
        resolutions.sort((a, b) => (b.height || b) - (a.height || a)); // Sort descending
        if (!resolutions.includes('audio')) resolutions.push('audio');
        if (!resolutions.includes('default')) resolutions.push('default');
        
        resolutions.forEach(resItem => {
            const height = resItem === 'audio' ? 'audio' : resItem === 'default' ? '' : (resItem.height || resItem);
            if (typeof height !== 'number' && height !== 'audio' && height !== '') return;
            
            const button = document.createElement('button');
            button.textContent = height === 'audio' ? 'Audio' : height === '' ? 'Default' : `${height}p`;
            button.classList.add('vjs-resolution-option');
            const urlParams = new URLSearchParams(window.location.search);
            if (urlParams.get('quality') == height || (urlParams.get('quality') == null && height == ''))
            {
                button.classList.add('vjs-resolution-option-current');
            }
            
            button.onclick = (event) => {
                tryStopPropagation(event);
                
                if (abortController) abortController.abort();
                abortController = new AbortController();
                const signal = abortController.signal;
                const urlParams = new URLSearchParams(window.location.search);
                const buttons = this.menu.querySelectorAll('.vjs-resolution-option');
                urlParams.set('quality', height);
                history.replaceState(null, '', `${window.location.pathname}?${urlParams.toString()}`);
                const hlsEnabled = urlParams.get('hls') != 'false' && height != null && height != 'audio';
                if (hlsEnabled)
                {
                    console.log('HLS ENABLED');
                    retryFetch(getVideoSource()[0])
                        .then(response => response.text())
                        .then(playlist => {
                            var segments = playlist.split('\n');
                            const segmentToDownload = String(Math.ceil(player.currentTime()/10)).padStart(4,'0') + ".ts";
                            segments.forEach(segment => {
                                if (segment.endsWith(segmentToDownload))
                                {
                                    retryFetch(segment)
                                        .then(response => {
                                            const switchTime = player.currentTime();
                                            const isPlaying = !player.paused();
                                            applyVideoQuality();
                                            player.currentTime(switchTime);
                                            if (isPlaying) player.play();
                    
                                            buttons.forEach(btn => btn.classList.remove('vjs-resolution-option-current'));
                                            button.classList.add('vjs-resolution-option-current');
                                        });
                                }
                            });
                    });
                }
                else
                {
                    retryFetch(getVideoSource()[0], { signal })
                        .then(response => {
                            const switchTime = player.currentTime();
                            const isPlaying = !player.paused();
                            applyVideoQuality();
                            player.currentTime(switchTime);
                            if (isPlaying) player.play();
    
                            buttons.forEach(btn => btn.classList.remove('vjs-resolution-option-current'));
                            button.classList.add('vjs-resolution-option-current');
                        })
                        .catch(error => {
                            console.error('Error fetching new quality:', error);
                        });
                }

                this.handleCloseMenu();
            };
            this.menu.appendChild(button);
        });
    }


    createResolutionMenu()
    {
        const menu = document.createElement('div');
        menu.classList.add('vjs-resolution-menu');
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
        this.menu.style.display = 'block';
    }

    handleCloseMenu()
    {
        this.menu.style.display = 'none';
        if (this.parent)
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

            button.onclick = (event) => {
                tryStopPropagation(event);
                this.handleSubtitleSelection(lang);
                this.handleCloseMenu();
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
        menu.classList.add('vjs-subtitle-menu');
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
        tryStopPropagation(event);
        if (this.menu.style.display === 'flex')
            this.menu.style.display = 'none';
        else
            this.handleOpenMenu();
    }

    handleOpenMenu()
    {
        this.menu.style.display = 'flex';
    }

    handleCloseMenu()
    {
        this.menu.style.display = 'none';
        if (this.parent)
        {
            this.parent.handleCloseMenu();
        }
    }

    createPlaybackSpeedMenu()
    {
        const menu = document.createElement('div');
        menu.classList.add('vjs-playback-speed-menu');
        menu.style.display = 'none';

        const speeds = [0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0];
        speeds.forEach(speed => {
            const button = document.createElement('button');
            button.textContent = `${speed}x`;
            button.classList.add('vjs-playback-speed-option');
            if (this.player && this.player.playbackRate() === speed)
            {
                button.classList.add('vjs-playback-speed-option-current');
            }

            button.onclick = (event) => {
                tryStopPropagation(event);
                this.player.playbackRate(speed);
                if (speed == 1.0)
                    this.el().classList.remove('vjs-active');
                else
                    this.el().classList.add('vjs-active');

                menu.querySelectorAll('.vjs-playback-speed-option').forEach(btn => {
                    btn.classList.remove('vjs-playback-speed-option-current');
                });
                button.classList.add('vjs-playback-speed-option-current');

                this.handleCloseMenu();
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


function skipclick()
{
    if (player && player.currentTime() < skipTime) player.currentTime(skipTime);
};


function adjustVideoSize()
{
    const videoElement = playerContainer.querySelector('video');

    const width = videoElement.videoWidth || parseInt(meta.width);
    const height = videoElement.videoHeight || parseInt(meta.height);
    const innerWidth = window.innerWidth * 0.9;
    const innerHeight = window.innerHeight * 0.9;
    
    const min_dim = Math.min(innerWidth, innerHeight);
    const min_width = (min_dim + innerWidth) / 2;
    const min_height = (min_dim + innerHeight) / 2;
    
    const scaling = Math.min(min_width / width, min_height / height);
    
    playerContainer.style.width = width * scaling + 'px';
    playerContainer.style.height = height * scaling + 'px';
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
                },
                captureDocumentHotkeys: true,
                documentHotkeysFocusElementFilter: e => e.tagName.toLowerCase() === 'body',
                enableHoverScroll: true,
            },
        },
    });
    player.doubleTapFF();
    playerContainer = player.el();
    
    player.controlBar.ZoomToFillToggle.handleClick(state = false);
    
    const spacer = document.createElement('div');
    playerContainer.querySelector('.vjs-control-bar').appendChild(spacer);
    spacer.style="flex: auto;order: 3;";
    
    skipSegment = document.createElement('div');
    playerContainer.appendChild(skipSegment);
    skipSegment.id = "skipsegment";
    skipSegment.onclick = function() {skipclick();};

    player.on('timeupdate', () => {
        if (repeatMode && player.currentTime() >= repeatEndTime)
        {
            player.currentTime(repeatStartTime);
        }
    });

    const errorDisplay = playerContainer.querySelector('.vjs-error-display');
    errorDisplay.classList.add('spinner-parent');
    errorDisplay.querySelector('.vjs-modal-dialog-content').classList.add('spinner-body');
    
    const spinnerBody = document.createElement('div');
    const spinnerParent = playerContainer.querySelector('.vjs-loading-spinner')
    spinnerParent.appendChild(spinnerBody);
    spinnerBody.classList.add('spinner-body');
    spinnerParent.classList.add('spinner-parent');
    
    document.getElementById('video').style.filter = 'brightness(1)';

    playerContainer.querySelector('.vjs-poster').style.filter = '';
    try
    {
        applyVideoQuality();
    }
    catch
    {
        console.warn('Video quality list needed, delaying playback');
    }

    // When video is loaded
    player.on('loadeddata', () => {
        playerContainer.querySelector('img').classList.add('loaded-img');
        adjustVideoSize();
        window.addEventListener('resize', adjustVideoSize);
        setTimeout(() => {playerContainer.style.transitionDuration = '0s';}, 1000);
        player.controls(true);
        errorDisplay.classList.remove('spinner-parent');
        errorDisplay.querySelector('.vjs-modal-dialog-content').classList.remove('spinner-body');
        playerContainer.querySelector('.vjs-control-bar').classList.add('display-flex');
    });
    retryFetch(`/meta?${urlParams.toString()}`)
        .then(response => response.json())
        .then(metaData => {
            meta = metaData;
            if (meta["error"] !== undefined)
            {
                const errorDisplay = playerContainer.querySelector('.vjs-error-display');
                errorDisplay.innerHTML = meta['error'];
                errorDisplay.classList.remove('spinner-parent');
                errorDisplay.classList.remove('vjs-hidden');
                console.error(meta['error']);
                player.src({ src: 'null', type: 'null' });
                player = null;
                return;
            }
            applyVideoQuality();
            if (player.controlBar && player.controlBar.SettingsButton)
            {
                player.controlBar.SettingsButton.updateResolutions();
                player.controlBar.SettingsButton.updateSubtitles(meta.subtitles);
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
                    retryFetch(`/sprite?${urlParams.toString()}`, { visible: false }).then(response => response.text());
                }
            }
            catch {}

            player.load();
            player.on('error', () => {
                const error = player.error();
                if (error && error.code === 4)
                {
                    if (player.src().includes('/fastest'))
                    {
                        setTimeout(() => {
                            console.warn("Changing video quality due to unsupported format...");
                            currentVideoQuality = chooseGoodQuality();
                            applyVideoQuality();
                        }, 1000);
                    }
                }
            });
            loadMediaPlayer();
        })
        .catch(error => {
            console.error('Error fetching video:', error);
            const errorDisplay = playerContainer.querySelector('.vjs-error-display');
            errorDisplay.innerHTML = `${error.message}`;
            errorDisplay.classList.remove('spinner-parent');
            errorDisplay.classList.remove('vjs-hidden');
            player.src({ src: 'null', type: 'null' });
            player = null;
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

}


function copyCurrentUrl(event)
{
    if (event.button === 0)
    {
        event.preventDefault();
        navigator.clipboard.writeText(window.location.href).then(() => {
            var b = document.getElementById('url-copy');
            b.innerHTML = '<i class="fa-solid fa-copy"></i> URL Copied!';
            setTimeout(() => {
                b.innerHTML = '<i class="fa-solid fa-copy"></i> Copy URL';
            }, 2000);
        });
    }
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
    
    const videoElement = player.el().querySelector('video');
    navigator.mediaSession.setActionHandler("seekbackward", () => {
        videoElement.currentTime(videoElement.currentTime() - 10);
    });
    navigator.mediaSession.setActionHandler("seekforward", () => {
        videoElement.currentTime(videoElement.currentTime() + 10);
    });
    navigator.mediaSession.setActionHandler("previoustrack", null);
    navigator.mediaSession.setActionHandler("nexttrack", null);
    console.log("Loaded Media Player API");
}


loadVideo();
