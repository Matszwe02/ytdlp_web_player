// Thanks to https://github.com/lopiacode/audio-visualizer

let visualizerActive = false;
let visualizerPaused = false;

function enableVisualizer(player)
{
    if (visualizerActive) return;
    if (player.paused())
    {
        setTimeout(() => {
            enableVisualizer(player);
        }, 500);
        return;
    }
    if (visualizerActive) return;
    visualizerActive = true;
    setUpAudioContext();
    var poster = player.el_.querySelector('.vjs-poster');
    var visBody = document.createElement('div');
    var visContainer = document.createElement('div');
    var visOverlay = document.createElement('div');
    var visIcon = document.createElement('div');
    visOverlay.classList.add('vis-overlay');
    visContainer.classList.add('vis-container');
    visIcon.innerHTML = '<img src="/favicon.svg"></img>';
    visContainer.appendChild(visBody);
    visOverlay.appendChild(visIcon);
    poster.appendChild(visContainer);
    poster.appendChild(visOverlay);
    const analyser = audioContext.createAnalyser();
    audioSource.connect(analyser);
    analyser.fftSize = 64;
    analyser.smoothingTimeConstant = 0.2;
    const bufferLength = analyser.frequencyBinCount;

    let dataArray = new Uint8Array(bufferLength);
    let elements = [];
    for(let i = 0; i < bufferLength * 2; i++)
    {
        const element = document.createElement('span');
        elements.push(element);
        visBody.appendChild(element);
    }

    const update = () => {
        if (!visualizerActive) return;
        setTimeout(() => {
            requestAnimationFrame(update);
        }, 30);
        analyser.getByteFrequencyData(dataArray);
        let scale = Math.max((dataArray[0] + dataArray[1] + dataArray[2] + dataArray[3] + dataArray[4]) / 5, 150) - 150;
        let scale1 = 1 + scale * 0.001;
        let scale2 = 1.005 + scale * 0.0001;
        scale1 *= poster.clientWidth / 500;
        visContainer.style.scale = scale1;
        visOverlay.style.scale = scale1;
        poster.style.scale = scale2;
        for (let i = 0; i < bufferLength; i++)
        {
            let item = dataArray[i];
            item = item > 150 ? item / 2 : item;
            item = Math.pow(item, 0.7) + 25;
            elements[i].style.transform = `rotateZ(${i * (180 / bufferLength)}deg) translate(-50%, ${item}px)`;
            elements[i + bufferLength].style.transform = `rotateZ(${i * (-180 / bufferLength)}deg) translate(-50%, ${item}px)`;
        }
    };
    update();
}


function disableVisualizer(player)
{
    if (!visualizerActive) return;
    visualizerActive = false;
    player.el_.querySelector('.vis-container').remove();
    player.el_.querySelector('.vis-overlay').remove();
    player.el_.querySelector('.vjs-poster').style.scale = 1.005;
}


function pauseVisualizer(player)
{
    disableVisualizer(player);
    visualizerPaused = true;
}


function resumeVisualizer(player)
{
    if (visualizerPaused)
    {
        enableVisualizer(player);
    }
    visualizerPaused = false;
}
