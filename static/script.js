const sbContainer = document.getElementById('sponsorblock');
const skipsegment = document.getElementById('skipsegment');
const videoSource = document.getElementById('videoSource');
const videoPlayer = document.getElementById('videoPlayer');
var videoControls = document.querySelector('video::-webkit-media-controls-panel');

var segments = [];
var skipTime = 0;

function videoDisplay()
{
    const url = document.getElementById('standard_url').value;
    const encodedUrl = encodeURIComponent(url);
    window.history.pushState({}, "", `?url=${encodedUrl}`);
    loadVideo();
}

function adjustVideoSize()
{
    var width = videoPlayer.videoWidth;
    var height = videoPlayer.videoHeight;
    var aspectRatio = width / height;
    var bodyAspectRatio = (document.body.clientWidth * 0.7) / (document.body.clientHeight * 0.9);
    if (width == 0 || height == 0)
    {
        videoPlayer.style.width = '70vw';
        videoPlayer.style.height = '50px';
    }
    else if (aspectRatio > bodyAspectRatio) {
        videoPlayer.style.width = '70vw';
        videoPlayer.style.height = 'calc(70vw / ' + aspectRatio + ')';
    } else {
        videoPlayer.style.height = '90vh';
        videoPlayer.style.width = 'calc(90vh * ' + aspectRatio + ')';
    }
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
        skipsegment.innerHTML="skip " + segmentShown.category;
        skipTime=segmentShown.end;
    }
    
    setTimeout(() => {checkSponsorTime();}, 200);
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
    
    if (data.length > 0)
    {
        checkSponsorTime();
    }
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
            videoSource.src = data;
            const videoId = new URLSearchParams(window.location.search).get('url');
            videoPlayer.load();
            videoPlayer.style.filter = 'brightness(1)';
            
            videoPlayer.addEventListener('loadeddata', () => {
                adjustVideoSize();
                window.addEventListener('resize', adjustVideoSize);
                videoLoader.style.opacity = 0;
                setTimeout(() => {
                    videoLoader.style.display = 'none';
                    videoPlayer.style.transitionDuration = '0s';
                    videoPlayer.controls = true;
                }, 1000);
            });
        })
        .catch(error => {
            console.error('Error fetching video URL:', error);
            const loader = document.getElementsByClassName('custom-loader-container')[0];
            loader.innerHTML = '<i class="fa-solid fa-circle-exclamation" style="font-size:7vw; color:red;"></i>';
        });

    fetch(`/sb?${(urlParams.toString())}`)
        .then(response => {
            return response.json();
        })
        .then(data => {
            segments = data;
            videoPlayer.addEventListener('loadedmetadata', () => {addSponsorblock(data);});
        });
}
loadVideo();
