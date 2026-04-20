// ==UserScript==
// @name         YT-DLP Web Player
// @namespace    https://github.com/Matszwe02/ytdlp_web_player
// @downloadURL  https://github.com/Matszwe02/ytdlp_web_player
// @updateURL    https://github.com/Matszwe02/ytdlp_web_player
// @homepageURL  https://github.com/Matszwe02/ytdlp_web_player
// @supportURL   https://github.com/Matszwe02/ytdlp_web_player
// @version      1.0.0
// @description  Replaces videos with YT-DLP Player
// @author       matszwe02
// @match        *://*.youtube.com/*
// @icon         https://github.com/Matszwe02/ytdlp_web_player/raw/main/src/static/favicon.svg
// @grant        none
// @run-at       document-start
// ==/UserScript==


// if running this script in standalone mode (tampermonkey), fill in playerUrl with your YT-DLP Player instance

var playerUrl = '';

var iframe = null;
var iframeContainer = null;
var cookies = false;
var isPosFixed = false;
var posUpdatesInRow = 0;
var tabEnabled = true;


function blockVideos()
{
    if (!tabEnabled) return;
    for (let media of document.querySelectorAll('video, audio'))
    {
        try
        {
            if (media.muted && media.volume == 0 && media.paused && !media.autoplay) continue;
            console.log(`Blocking ${media}`);
            
            const stopMedia = (e = null) => {
                if (!tabEnabled) return;
                if (e !== null)
                {
                    e.stopImmediatePropagation();
                    e.preventDefault();
                }
                media.removeAttribute('autoplay');
                media.muted = true;
                media.volume = 0;
                media.pause();
            };
            ['play', 'playing', 'loadeddata', 'loadedmetadata', 'timeupdate']
                .forEach(e => media.addEventListener(e, stopMedia, true));
            if (!media.muted && media.volume > 0) media.classList.add('ytdlp-player-muted');
            stopMedia();
        }
        catch (e)
        {
            if (e.name != 'InvalidStateError') console.warn(e);
        };
    }
}


function unblockVideos()
{
    if (tabEnabled) return;
    document.querySelectorAll('.ytdlp-player-muted').forEach(element => {
        element.muted = false;
        element.volume = 1;
    });
}


function getIframeContainer()
{
    const allVideos = Array.from(document.querySelectorAll('video, .html5-video-player'));
    console.log(`Total videos found: ${allVideos.length}`);


    let maxArea = 0;
    allVideos.forEach(video => {
        const rect = video.getBoundingClientRect();
        const area = rect.width * rect.height;
        console.log(`  - top:${rect.top}, left:${rect.left}, w:${rect.width}, h:${rect.height}`);
        if (area > maxArea) maxArea = area;
    });

    if (maxArea === 0)
    {
        if (iframeContainer) videoResizeObserver.unobserve(iframeContainer);
        return;
    }

    const potentialCandidates = allVideos.filter(video => {
        const rect = video.getBoundingClientRect();
        const area = rect.width * rect.height;
        return area >= maxArea * 0.80;
    });
    console.debug(`Potential candidates: ${potentialCandidates.length}`);

    let bestVideo = null;
    let maxVisibilityScore = -Infinity;

    potentialCandidates.forEach(video => {
        const rect = video.getBoundingClientRect();
        const closeX = Math.min(rect.left - 0, window.innerWidth - rect.right);
        const closeY = Math.min(rect.top - 0, window.innerHeight - rect.bottom);
        const visibilityScore = Math.min(closeX, closeY);

        console.debug(`  - Visibility ${visibilityScore.toFixed(0)}, top:${rect.top}, left:${rect.left}, w:${rect.width}, h:${rect.height}`);

        if (visibilityScore >= maxVisibilityScore)
        {
            maxVisibilityScore = visibilityScore;
            bestVideo = video;
        }
    });
    if (bestVideo)
    {
        const rect = bestVideo.getBoundingClientRect();
        while (bestVideo.parentElement !== document.body)
        {
            const parentRect = bestVideo.parentElement.getBoundingClientRect();
            if (parentRect.width > (rect.width * 1.02) || parentRect.height > (rect.height * 1.02)) break;
            bestVideo = bestVideo.parentElement;
        }
    }
    console.debug(bestVideo);
    return bestVideo;
}


function createIframe(src='')
{
    if (iframe = document.getElementById('ytdlp-player')) return;
    console.log(`Creating iframe`);
    iframe = document.createElement('iframe');
    iframe.id = 'ytdlp-player';
    iframe.style.border = 'none';
    iframe.style.position = 'absolute';
    iframe.style.zIndex = '9999';
    iframe.style.top = '0px';
    iframe.style.left = '0px';
    iframe.allowFullscreen = true;
    iframe.src = src;
    isPosFixed = false;
    document.body.appendChild(iframe);
    if (cookies)
    {
        try
        {
            chrome?.runtime?.sendMessage({
                action: 'postCookies',
                playerUrl: playerUrl,
                documentCookies: document.cookie,
                currentWebsiteUrl: window.top.location.href
            });
            
        }
        catch (error)
        {
            console.warn(error);
        }
    }
}


function updateIframeGeometry(forceZero = false)
{
    if (!tabEnabled) return;
    const rect = iframeContainer?.getBoundingClientRect();
    const vidRect = iframeContainer?.querySelector('video')?.getBoundingClientRect();
    const iframeRect = iframe.getBoundingClientRect();
    const width = Math.max(rect?.width || 0, vidRect?.width || 0);
    const height = Math.max(rect?.height || 0, vidRect?.height || 0);

    if ((width == 0 || height == 0) && iframe.style.width && iframe.style.height && !forceZero)
    {
        return;
    }

    iframe.style.width = `${width}px`;
    iframe.style.height = `${height}px`;

    if (isPosFixed)
    {
        iframe.style.top = `${rect?.top || 0}px`;
        iframe.style.left = `${rect?.left || 0}px`;
    }
    else
    {
        const top = (rect?.top || 0) - iframeRect.top + parseFloat(iframe.style.top || 0);
        const left = (rect?.left || 0) - iframeRect.left + parseFloat(iframe.style.left || 0);
        if (iframe.style.top != `${top}px` || iframe.style.left != `${left}px`) posUpdatesInRow ++;
        else posUpdatesInRow = 0;
        if (posUpdatesInRow > 20)
        {
            isPosFixed = true;
            iframe.style.position = 'fixed';
            console.log(`Could not stabilize iframe in position absolute. Changing to position fixed.`);
        }
        iframe.style.top = `${top}px`;
        iframe.style.left = `${left}px`;
    }
}


function updateIframe(updateContainer = false)
{
    if (!tabEnabled) return;
    let src = window.top.location.href;
    let srcUrl = new URL(src);
    let iframeEnabled = srcUrl.pathname != '/' || srcUrl.search;
    let iframeSrc = `${playerUrl}/iframe?url=${encodeURIComponent(src)}`;
    if (iframe === null || !document.getElementById('ytdlp-player')) createIframe(iframeSrc);
    if ((iframe.src != iframeSrc && iframeEnabled))
    {
        console.log(`Chaning iframe src from ${iframe.src} to ${iframeSrc}`);
        iframe.remove();
        createIframe(iframeSrc);
    }
    if (updateContainer)
    {
        if (iframeContainer)
        {
            iframeContainer.style.opacity = '';
            iframeContainer.style.pointerEvents = '';
        }
        iframeContainer = getIframeContainer();
        if (iframeContainer)
        {
            iframeContainer.style.opacity = '0';
            iframeContainer.style.pointerEvents = 'none';
        }
    }
    if (!iframeEnabled)
    {
        if (iframeContainer)
        {
            iframeContainer.style.opacity = '';
            iframeContainer.style.pointerEvents = '';
            iframeContainer = null;
        }
        if (iframe !== null && iframe.src !== '')
        {
            console.log('Disabling iframe');
            iframe.src = '';
        }
    }
    updateIframeGeometry(forceZero = !iframeEnabled);
}


function start()
{
    tabEnabled = true;
    window.addEventListener('scroll', updateIframeGeometry, { passive: true });
    window.addEventListener('popstate', updateIframe);

    if (window.navigation)
    {
        window.navigation.addEventListener('navigate', () => {
            setTimeout(updateIframe, 100); 
        });
    }

    let applyLogicTimeout = null;
    const observer = new MutationObserver(() => {
        updateIframe();
        blockVideos();
        clearTimeout(applyLogicTimeout);
        applyLogicTimeout = setTimeout(()=>{updateIframe(true);}, 100);
    });
    observer.observe(document.body, { childList: true, subtree: true });
    setInterval(updateIframe, 500);

    videoResizeObserver = new ResizeObserver(() => {
        updateIframe();
    });
    updateIframe(true);
    blockVideos();
    document.addEventListener('click', (e) => {
        if (iframe !== null && e.target.tagName !== 'INPUT' && e.target.tagName !== 'TEXTAREA' && e.target.tagName !== 'SELECT')
        {
            iframe.focus();
        }
    });
}


function stop()
{
    tabEnabled = false;
    if (iframe)
    {
        iframe.remove();
    }
    if (iframeContainer)
    {
        iframeContainer.style.opacity = '';
        iframeContainer.style.pointerEvents = '';
    }
    unblockVideos();
}


function tryStart()
{
    if (!playerUrl)
    {
        chrome.storage.sync.get({ playerUrl: '', cookies: false }, (items) => {
            playerUrl = items.playerUrl;
            cookies = items.cookies;
            tryStart();
        });
        chrome.storage.onChanged.addListener((changes, namespace) => {
            if (namespace !== 'sync' || !changes.playerUrl) return;
            playerUrl = changes.playerUrl.newValue;
        });
        return;
    }
    if (!document.body)
    {
        setTimeout(() => {
            tryStart();
        }, 100);
        return;
    }
    try
    {
        start();
    }
    catch (error)
    {
        console.warn(error);
        setTimeout(() => {
            tryStart();
        }, 1000);
    }
}


if (playerUrl) tryStart();
else
{

    chrome.storage.sync.get({ allowedDomains: '' }, (items) => {
        if (!items.allowedDomains) return;
    
        const currentUrl = new URL(window.top.location.href);
        const hostname = currentUrl.hostname;
    
        const allowedDomains = items.allowedDomains.split(',').map(domain => domain.trim());
        if (allowedDomains.some(allowedDomain => { return hostname === allowedDomain || hostname.endsWith(`.${allowedDomain}`); }))
        {
            tryStart();
        }
        else
        {
            stop();
        }
    });

    chrome.storage.onChanged.addListener((changes, namespace) => {
        if (namespace !== 'sync' || !changes.allowedDomains) return;
    
        const currentUrl = new URL(window.top.location.href);
        const hostname = currentUrl.hostname;
    
        const allowedDomains = changes.allowedDomains.newValue.split(',').map(domain => domain.trim());
        if (allowedDomains.some(allowedDomain => { return hostname === allowedDomain || hostname.endsWith(`.${allowedDomain}`); }))
        {
            tryStart();
        }
        else
        {
            stop();
        }
    });

    chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
        if (message.action === 'start')
        {
            tryStart();
        }
        else if (message.action === 'stop')
        {
            stop();
        }
    });

}
