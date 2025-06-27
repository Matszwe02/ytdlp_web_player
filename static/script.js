const videoSource = document.getElementById('videoSource');
const videoPlayer = document.getElementById('videoPlayer');
let player;
let playerContainer;
let skipSegment;
let skipTime = 0;
let currentVideoQuality = '720p';
let activeFetches = 0; // Counter for active retryFetch calls


function addFetch()
{
    activeFetches += 1;
    console.log(activeFetches);
    try
    {
        const settingsIcon = player.controlBar.SettingsButton.el().querySelector('.fa-gear');
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
        const settingsIcon = player.controlBar.SettingsButton.el().querySelector('.fa-gear');
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


async function retryFetch(url, options = {}, retries = 5, delay = 5000) {
    try {
        const response = await fetch(url, options);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return response;
    } catch (error) {
        console.error(`Fetch failed, retrying in ${delay / 1000} seconds...`, error);
        if (retries > 0) {
            await new Promise(resolve => setTimeout(resolve, delay));
            return retryFetch(url, options, retries - 1, delay);
        } else {
            console.error('Max retries reached. Fetch failed.');
            throw error; // Re-throw the error to be caught by the caller
        }
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
    
    handleClick(state = null)
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
            document.cookie = "zoomToFill=true; path=/";
        }
        else
        {
            video.style.setProperty('object-fit', 'contain');
            this.el().innerHTML = '<span class="fa-solid fa-up-right-and-down-left-from-center"></span>';
            this.controlText('Zoom to Fill');
            document.cookie = "zoomToFill=false; path=/";
        }
    };
}
videojs.registerComponent('ZoomToFillToggle', ZoomToFillToggle);


class SettingsButton extends videojs.getComponent('Button')
{
    constructor(player, options) {
        super(player, options);
        this.addClass('vjs-settings-button');
        this.controlText('Settings');
        this.el().innerHTML = '<i class="fa-solid fa-gear"></i>';

        this.menu = this.createSettingsMenu();
        this.el().appendChild(this.menu);

        this.resolutionSwitcher = new ResolutionSwitcherButton(player, options);
        this.subtitleSwitcher = new SubtitleSwitcherButton(player, options);
        this.downloadButton = new DownloadButton(player, options);
        this.resolutionSwitcher.parent = this;
        this.subtitleSwitcher.parent = this;
        this.downloadButton.parent = this;

        this.menu.appendChild(this.resolutionSwitcher.el());
        this.menu.appendChild(this.subtitleSwitcher.el());
        this.menu.appendChild(this.downloadButton.el());
    }

    handleClick(event)
    {
        event.stopPropagation();
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

    updateResolutions(resolutions)
    {
        this.resolutionSwitcher.updateResolutions(resolutions);
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
        this.trimMenu = this.createTrimMenu();
        this.el().innerHTML = '<span class="fa-solid fa-download"></span>';
        this.el().appendChild(this.menu);
        this.el().appendChild(this.trimMenu);
    }

    handleCloseMenu(propagate = true)
    {
        this.menu.style.height = '0em';
        this.trimMenu.style.height = '0em';
        player.removeClass('download-menu-open');
        if (this.parent && propagate)
        {
            this.parent.handleCloseMenu();
        }
    }

    handleClick(event)
    {
        event.stopPropagation();
        if (this.menu.contains(event.target)) return;
        if (this.menu.style.height == '3.5em') return this.handleCloseMenu(false);
        
        this.menu.style.height = '3.5em';
        this.trimMenu.style.height = '0em';
        player.addClass('download-menu-open');
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
        menu.classList.add('vjs-download-menu');
        
        const options = [
            { html: '<i class="fa-solid fa-circle-up"></i>', quality: 'best', title: 'Highest Quality' },
            { html: '<i class="fa-solid fa-film"></i>', quality: 'current', title: 'Current Quality' },
            { html: '<i class="fa-solid fa-music"></i>', quality: 'audio', title: 'Audio Only' },
            { html: '<i class="fa-solid fa-scissors"></i>', quality: 'trim', title: 'Trim Video' }
        ];
        
        options.forEach(option => {
            const button = document.createElement('button');
            button.innerHTML = option.html;
            button.title = option.title;
            button.classList.add('vjs-download-option');
            
            const handleEvent = (event) => {
                if (option.quality == 'trim')
                {
                    event.stopPropagation(); // Prevent the click from propagating to the parent DownloadButton
                    this.trimMenu.style.height = (this.trimMenu.style.height == '3.5em')?'0em':'3.5em';
                    this.startTime = null;
                    this.endTime = null;
                    this.updateTimeLabels();
                }
                else
                {
                    if (option.quality == 'current') option.quality = currentVideoQuality;
                                        
                    const link = document.createElement('a');
                    link.href = `${baseDownloadUrl}&quality=${option.quality}`;
                    
                    if (this.startTime != null && this.endTime != null)
                        link.href += `&start=${this.startTime.toFixed(1)}&end=${this.endTime.toFixed(1)}`;
                    
                    link.download = 'file';
                    document.body.appendChild(link);
                    link.click();
                    document.body.removeChild(link);
                    
                    menu.style.height = '4.5em';
                    setTimeout(() => { this.handleCloseMenu(); }, 200);
                    addFetch();
                    retryFetch(link.href)
                        .then(response => response.text())
                        .then(x => {removeFetch();})
                }
            };
            
            button.addEventListener('touchend', handleEvent);
            button.addEventListener('click', handleEvent);
            
            menu.appendChild(button);
        });
        
        return menu;
    }

    createTrimMenu()
    {
        
        const menu = document.createElement('div');
        menu.classList.add('vjs-download-menu');
        menu.style.bottom='200%';
        
        
        this.startBtn = document.createElement('button');
        this.startBtn.classList.add('vjs-download-option');
        this.startBtn.title = 'Click To Adjust Start Time';
        
        this.endBtn = document.createElement('button');
        this.endBtn.classList.add('vjs-download-option');
        this.endBtn.title = 'Click To Adjust End Time';
        
        this.updateTimeLabels();
        
        const startEvent = (event) => {
            event.stopPropagation();
            this.startTime = player.currentTime();
            this.updateTimeLabels();
        };
        
        const endEvent = (event) => {
            event.stopPropagation();
            this.endTime = player.currentTime();
            this.updateTimeLabels();
        };
        
        this.startBtn.addEventListener('touchend', (e) => startEvent(e));
        this.startBtn.addEventListener('click', (e) => startEvent(e));
        this.endBtn.addEventListener('touchend', (e) => endEvent(e));
        this.endBtn.addEventListener('click', (e) => endEvent(e));
        
        menu.appendChild(this.startBtn);
        menu.appendChild(this.endBtn);
        
        return menu;
    }
}
videojs.registerComponent('DownloadButton', DownloadButton);


class ResolutionSwitcherButton extends videojs.getComponent('Button') {
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
        event.stopPropagation();
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


    updateResolutions(resolutions)
    {        
        if (!resolutions || resolutions.length < 2) return;
        this.el().style.display = '';
        
        const urlParams = new URLSearchParams(window.location.search);
        
        resolutions.sort((a, b) => (b.height || b) - (a.height || a)); // Sort descending
        resolutions.push('audio');
        
        resolutions.forEach(resItem => {
            const height = resItem === 'audio' ? 'audio' : (resItem.height || resItem);
            if (typeof height !== 'number' && height !== 'audio') return;
            
            const button = document.createElement('button');
            button.textContent = height === 'audio' ? 'Audio' : `${height}p`;
            button.classList.add('vjs-resolution-option');
            
            button.onclick = (event) => {
                event.stopPropagation();
                
                const buttons = this.menu.querySelectorAll('.vjs-resolution-option');
                const videoEl = player.el().querySelector('video');
                const posterEl = player.el().querySelector('.vjs-poster');
                const downloadUrl = `/download?${urlParams.toString()}&quality=${height}`;
                
                addFetch();
                retryFetch(downloadUrl)
                    .then(response => response.text())
                    .then(x => {
                        removeFetch();
                        const switchTime = player.currentTime();
                        const isPlaying = !player.paused();
                        currentVideoQuality = height;
                        player.src({ src: downloadUrl, type: 'video/mp4' });
                        player.currentTime(switchTime);
                        if (isPlaying) player.play();

                        if (currentVideoQuality === 'audio')
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
                        buttons.forEach(btn => btn.classList.remove('vjs-resolution-option-current'));
                        button.classList.add('vjs-resolution-option-current');
                    });

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


class SubtitleSwitcherButton extends videojs.getComponent('Button') {
    constructor(player, options) {
        super(player, options);
        this.addClass('menu-button');
        this.controlText('Subtitles');
        this.el().innerHTML = '<i class="fa-solid fa-closed-captioning"></i>';
        this.el().style.display = 'none';

        this.parent = null;
        this.menu = this.createSubtitleMenu();
        this.el().appendChild(this.menu);

        this.subtitles = {};
        this.loadSubtitles();
    }

    handleClick(event)
    {
        event.stopPropagation();
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

    loadSubtitles()
    {
        const urlParams = new URLSearchParams(window.location.search);
        retryFetch(`/subtitles?${urlParams.toString()}`)
            .then(response => response.json())
            .then(subtitleList => {
                this.subtitles = subtitleList;
                this.updateSubtitles(subtitleList);
            })
            .catch(error => {
                console.error('Error fetching subtitles:', error);
            });
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
                event.stopPropagation();
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
            addFetch();
            retryFetch(subtitleSrc)
                .then(response => response.text())
                .then(x => {removeFetch();})
            
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


function skipclick()
{
    if (player && player.currentTime() < skipTime) player.currentTime(skipTime);
};


function adjustVideoSize()
{
    const videoElement = playerContainer.querySelector('video');
    
    const width = videoElement.videoWidth;
    const height = videoElement.videoHeight;
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
    }
    else
    {
        skipSegment.style.opacity = 1;
        skipSegment.style.transform = 'translate(0, 0)';
        skipSegment.title = "skip " + segmentShown.category.replaceAll('_', ' ') + ' [Enter]';
        skipSegment.innerHTML = "skip <b>" + segmentShown.category.replaceAll('_', ' ') + '</b> <i class="fa-solid fa-angles-right"></i>';
        skipTime = segmentShown.end;
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
    player.spriteThumbnails({ url: `/sprite?${urlParams.toString()}`, width: 160, height: 90, columns: 10, interval: 10 });
    playerContainer = player.el();
    
    const zoomToFillCookie = document.cookie.split('; ').find(row => row.startsWith('zoomToFill='));
    player.controlBar.ZoomToFillToggle.handleClick(zoomToFillCookie?.split('=')[1] === 'true');
    
    const spacer = document.createElement('div');
    playerContainer.querySelector('.vjs-control-bar').appendChild(spacer);
    spacer.style="flex: auto;order: 3;";
    
    skipSegment = document.createElement('div');
    playerContainer.appendChild(skipSegment);
    skipSegment.id = "skipsegment";
    skipSegment.onclick = function() {skipclick();};
    
    const errorDisplay = playerContainer.querySelector('.vjs-error-display');
    errorDisplay.classList.add('spinner-parent');
    errorDisplay.querySelector('.vjs-modal-dialog-content').classList.add('spinner-body');
    
    const spinnerBody = document.createElement('div');
    const spinnerParent = playerContainer.querySelector('.vjs-loading-spinner')
    spinnerParent.appendChild(spinnerBody);
    spinnerBody.classList.add('spinner-body');
    spinnerParent.classList.add('spinner-parent');
    
    document.getElementById('video').style.filter = 'brightness(1)';
    
    retryFetch(`/search?${urlParams.toString()}`)
        .then(response => response.text())
        .then(data => {
        
            fetch(`/sprite?${urlParams.toString()}`).then(response => response.text()).then(data => {});
            playerContainer.querySelector('.vjs-poster').style.filter = '';
            
            // Set video source with the stream URL
            player.src({src: data, type: 'video/mp4'});
            
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
            player.load();
        })
        .catch(error => {
            console.error('Error fetching video URL:', error);
            errorDisplay.classList.remove('spinner-parent');
            errorDisplay.querySelector('.vjs-modal-dialog-content').classList.remove('spinner-body');
        });

    addFetch();
    retryFetch(`/formats?${urlParams.toString()}`)
        .then(response => response.json())
        .then(formats => {
            removeFetch();
            console.log('Available formats:', formats);
            if (player.controlBar && player.controlBar.SettingsButton)
            {
                player.controlBar.SettingsButton.updateResolutions(formats);
            }
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


loadVideo();
