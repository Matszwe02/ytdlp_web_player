const sbContainer = document.getElementById('sponsorblock');
const skipsegment = document.getElementById('skipsegment');
const videoSource = document.getElementById('videoSource');
const videoPlayer = document.getElementById('videoPlayer');
const expandButton = document.getElementById('expand-button');
const expandableContent = document.getElementById('expandable-content');
let isExpanded = false;



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

function handleFullscreenChange() {
    if (document.fullscreenElement === videoPlayer || document.webkitFullscreenElement === videoPlayer) {
        videoPlayer.classList.add('fullscreen');
    } else {
        videoPlayer.classList.remove('fullscreen');
    }
}

document.addEventListener('fullscreenchange', handleFullscreenChange);
document.addEventListener('webkitfullscreenchange', handleFullscreenChange);
const loader = document.getElementsByClassName('custom-loader-container')[0];
var videoControls = document.querySelector('video::-webkit-media-controls-panel');

var segments = [];
var skipTime = 0;

// function videoDisplay()
// {
//     const url = document.getElementById('standard_url').value;
//     const encodedUrl = encodeURIComponent(url);
//     window.history.pushState({}, "", `?url=${encodedUrl}`);
//     loadVideo();
// }

function adjustVideoSize()
{
    var width = videoPlayer.videoWidth;
    var height = videoPlayer.videoHeight;
    var innerWidth = window.innerWidth * 0.9;
    var innerHeight = window.innerHeight * 0.9;
    
    min_dim = Math.min(innerWidth, innerHeight);
    min_width = (min_dim + innerWidth) / 2;
    min_height = (min_dim + innerHeight) / 2;
    
    scaling = Math.min(min_width / width, min_height / height);
    
    videoPlayer.style.width = width * scaling + 'px';
    videoPlayer.style.height = height * scaling + 'px';
    
}

function skipclick()
{
    if (videoPlayer.currentTime < skipTime)
    {
        videoPlayer.currentTime = skipTime;
    }
}

function checkSponsorTime()
{
    var segmentShown = null;
    segments.forEach(segment => {
        if (videoPlayer.currentTime > segment.start && videoPlayer.currentTime < segment.end)
        {
            segmentShown = segment;
        }
    });
    
    if (segmentShown == null)
    {
        skipsegment.style.opacity=0;
    }
    else
    {
        skipsegment.style.opacity=1;
        skipsegment.innerHTML="skip " + segmentShown.category + ' <i class="fa-solid fa-angles-right"></i>';
        skipTime=segmentShown.end;
    }
}

function addSponsorblock(data)
{
    const colorMap = {
        'selfpromo': '#ffff00',
        'outro': '#0000ff',
        'sponsor': '#00ff00',
        'preview': '#0077ff',
        'interaction': '#ff00ff',
        'intro': '#00ffff'
    };

    const duration = videoPlayer.duration;
    
    data.forEach(entry => {
        const indicator = document.createElement('div');
        sbContainer.appendChild(indicator);
        
        const startPosition = (entry.start / duration) * 100;
        const endPosition = (entry.end / duration) * 100;
        const width = endPosition - startPosition;
        
        indicator.className = 'seg';
        indicator.style.position = 'absolute';
        indicator.style.left = `${startPosition}%`;
        indicator.style.width = `${width}%`;
        indicator.style.height = '100%';
        indicator.style.backgroundColor = colorMap[entry.category] || '#ffffff';
        indicator.title = `${entry.category}`;
    });
}

function readKey(e)
{
    console.log(e.key);
    if (e.key === 'Enter')
    {
        skipclick();
        e.preventDefault();
    }
    if (e.key == ' ' || e.key == 'k')
    {
        if (videoPlayer.paused) videoPlayer.play();
        else videoPlayer.pause();
        e.preventDefault();
    }
    if (e.key == 'a' || e.key == 'j' || e.key == 'ArrowLeft')
    {
        videoPlayer.currentTime -= 10;
        e.preventDefault();
    }
    if (e.key == 'd' || e.key == 'l' || e.key == 'ArrowRight')
    {
        videoPlayer.currentTime += 10;
        e.preventDefault();
    }
    if (e.key == 'm')
    {
        videoPlayer.muted = !videoPlayer.muted;
        e.preventDefault();
    }
    if (e.key == 'f')
    {
        if (document.fullscreenElement)
            document.exitFullscreen();
        else
            videoPlayer.requestFullscreen();
        e.preventDefault();
    }
}

function loadVideo()
{
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.toString().length < 10) return;
    
    document.addEventListener('keydown', readKey);
    
    document.querySelectorAll('.non-video').forEach(element => {element.style.display = 'none';});
    document.querySelectorAll('.video').forEach(element => {element.style.display = 'block';});
    
    videoPlayer.poster = `/thumb?${(urlParams.toString())}`;
            
    fetch(`/search?${(urlParams.toString())}`)
        .then(response => {
            if (!response.ok)
            {
                throw new Error(response.status);
            }
            return response.text();
        })
        .then(data => {
            videoPlayer.style.transitionDuration = '1s';
            videoSource.src = data;
            videoPlayer.load();
            videoPlayer.style.filter = 'brightness(1)';
            
            videoPlayer.addEventListener('loadeddata', () => {
                adjustVideoSize();
                window.addEventListener('resize', adjustVideoSize);
                loader.style.opacity = 0;
                setTimeout(() => {
                    loader.style.display = 'none';
                    videoPlayer.style.transitionDuration = '0s';
                    videoPlayer.controls = true;
                }, 1000);
            });
        })
        .catch(error => {
            console.error('Error fetching video URL:', error);
            loader.innerHTML = '<i class="fa-solid fa-circle-exclamation" style="font-size:7vw; color:red;"></i>';
        });

    fetch(`/sb?${(urlParams.toString())}`)
        .then(response => {
            return response.json();
        })
        .then(data => {
            segments = data;
            videoPlayer.addEventListener('loadedmetadata', () => {addSponsorblock(data);});
            videoPlayer.addEventListener('timeupdate', checkSponsorTime)
        });
}
loadVideo();
