const videoSource = document.getElementById('videoSource');
const videoPlayer = document.getElementById('videoPlayer');
const expandButton = document.getElementById('expand-button');
const expandableContent = document.getElementById('expandable-content');
let isExpanded = false;
let player;
let playerContainer;
let skipSegment;
let skipTime = 0;


const sbColorMap = {
    'selfpromo': '#ffff00',
    'outro': '#0000ff',
    'sponsor': '#00ff00',
    'preview': '#0077ff',
    'interaction': '#ff00ff',
    'intro': '#00ffff'
};


expandButton.addEventListener('click', function() {
    isExpanded = !isExpanded;
    if (isExpanded)
    {
        expandableContent.style.maxHeight = expandableContent.scrollHeight + "px";
        expandButton.classList.add('expanded');
    }
    else
    {
        expandableContent.style.maxHeight = "0";
        expandButton.classList.remove('expanded');
    }
});


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
    }
    else
    {
        skipSegment.style.opacity = 1;
        skipSegment.innerHTML = "skip " + segmentShown.category + ' <i class="fa-solid fa-angles-right"></i>';
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
        
        indicator.className = 'seg';
        indicator.style.left = `${startPosition}%`;
        indicator.style.width = `${width}%`;
        indicator.style.backgroundColor = sbColorMap[entry.category] || '#ffffff';
        indicator.title = `${entry.category}`;
    });
}
    
// Main function to load video
function loadVideo() {
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.toString().length < 10) return;
    
    // TODO: split index.html
    document.querySelectorAll('.non-video').forEach(element => {
        element.style.display = 'none';
    });
    document.querySelectorAll('.video').forEach(element => {
        element.style.display = 'block';
    });
    
    // Initialize Video.js
    if (!player && document.getElementById('videoPlayer')) {
        player = videojs('videoPlayer', {
            controls: false,
            preload: 'auto',
            responsive: true,
            fluid: true,
            poster: `/thumb?${urlParams.toString()}`,
            controlBar: {
                children: [
                    'playToggle',
                    'progressControl',
                    'volumePanel',
                    'PictureInPictureToggle',
                    'fullscreenToggle'
                ]
            },
            plugins: {  
                hotkeys: {
                    customKeys: {
                        sbKey: {
                            key: function (event) {return event.code == "Enter";},
                            handler: function (player, options, event) {skipclick();},
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
        
        skipSegment = document.createElement('div');
        playerContainer.appendChild(skipSegment);
        skipSegment.id = "skipsegment";
        skipSegment.onclick = function() {skipclick();};
    }
    
    const errorDisplay = playerContainer.querySelector('.vjs-error-display');
    errorDisplay.classList.add('spinner-parent');
    errorDisplay.querySelector('.vjs-modal-dialog-content').classList.add('spinner-body');
    
    const spinnerBody = document.createElement('div');
    const spinnerParent = playerContainer.querySelector('.vjs-loading-spinner')
    spinnerParent.appendChild(spinnerBody);
    spinnerBody.classList.add('spinner-body');
    spinnerParent.classList.add('spinner-parent');
    
    fetch(`/search?${urlParams.toString()}`)
        .then(response => {
            if (!response.ok) {
                throw new Error(response.status);
            }
            return response.text();
        })
        .then(data => {
            playerContainer.querySelector('.vjs-poster').style.filter = '';
            
            // Set video source with the stream URL
            player.src({src: data, type: 'video/mp4'});
            playerContainer.querySelector('img').classList.add('loaded-img')
            
            // When video is loaded
            player.on('loadeddata', () => {
                adjustVideoSize();
                window.addEventListener('resize', adjustVideoSize);
                setTimeout(() => {playerContainer.style.transitionDuration = '0s';}, 1000);
                player.controls(true);
                errorDisplay.classList.remove('spinner-parent');
                errorDisplay.querySelector('.vjs-modal-dialog-content').classList.remove('spinner-body');
            });
            player.load();
        })
        .catch(error => {
            console.error('Error fetching video URL:', error);
            errorDisplay.classList.remove('spinner-parent');
            errorDisplay.querySelector('.vjs-modal-dialog-content').classList.remove('spinner-body');
        });
    
    // Fetch SponsorBlock
    fetch(`/sb?${urlParams.toString()}`)
        .then(response => {return response.json();})
        .then(data => {
            segments = data;
            player.on('loadeddata', () => {
                addSponsorblock(data);
            });
            player.on('timeupdate', checkSponsorTime);
        });
}


loadVideo();