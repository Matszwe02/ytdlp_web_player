// ==UserScript==
// @name         YT-DLP Web Player
// @namespace    https://github.com/Matszwe02/ytdlp_web_player
// @homepageURL  https://github.com/Matszwe02/ytdlp_web_player
// @supportURL   https://github.com/Matszwe02/ytdlp_web_player
// @downloadURL  https://github.com/Matszwe02/ytdlp_web_player/raw/main/extension/extension.js
// @updateURL    https://github.com/Matszwe02/ytdlp_web_player/raw/main/extension/extension.js
// @version      1.0.0
// @description  Replaces videos with YT-DLP Player
// @author       matszwe02
// @match        *://*/*
// @icon         https://github.com/Matszwe02/ytdlp_web_player/raw/main/src/static/favicon.svg
// @grant        GM_registerMenuCommand
// @grant        GM_unregisterMenuCommand
// @grant        GM_setValue
// @grant        GM_getValue
// @run-at       document-start
// ==/UserScript==


// fill in playerUrl with your YT-DLP Player instance if running this script in standalone mode (optional)

var playerUrl = '';

var iframe = null;
var iframeStyle = {};
var iframeContainer = null;
var cookies = false;
var lastContainerRect = null;
var lastScroll = null;
var tabEnabled = true;
var altSrc = "";

var storage = null;
var storageSync = null;
var videoResizeObserver = null;
try
{
    storage = (typeof browser !== 'undefined' && browser.storage) ? browser.storage : (typeof chrome !== 'undefined' ? chrome.storage : null);
    storageSync = storage.sync || storage.local;
}
catch {}


function windowHref()
{
    try
    {
        return window.top.location.href;
    }
    catch
    {
        return window.location.href;
    }
}


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


function editable(element)
{
    return !!element && (element.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(element.tagName));
}


function getIframeContainer()
{
    const ordered_video_types = [
        '.html5-video-player',
        'shreddit-player,.vimeo-player,.jwplayer,.video-js,.wistia_embed,.flowplayer,.dm_player_container',
        '.player,.video',
        'video',
        'img'
    ];
    let allVideos = [];
    for (const selector of ordered_video_types)
    {
        allVideos = document.querySelectorAll(selector);
        if (allVideos.length > 0)
        {
            console.debug(`Total videos of type "${selector}" found: ${allVideos.length}`);
            break;
        }
    }

    let maxArea = 0;
    let bestVideo = null;
    let maxDisplayScore = -Infinity;
    const size = window.innerHeight + window.innerWidth;

    allVideos.forEach(video => {
        const rect = video.getBoundingClientRect();
        const area = rect.width * rect.height;
        const closest = Math.min(rect.left, rect.top, window.innerWidth - rect.right, window.innerHeight - rect.bottom);
        const visibilityScore = Math.max(Math.min(closest, size / 4), -size / 8);
        console.debug(`Visibility score: ${visibilityScore}`);
        const displayScore = Math.sqrt(area) + visibilityScore * 2;
        maxArea = Math.max(maxArea, area);

        console.debug(`  - Display Score: ${displayScore.toFixed(0)}, top:${rect.top}, left:${rect.left}, w:${rect.width}, h:${rect.height}`);

        if (displayScore >= maxDisplayScore)
        {
            maxDisplayScore = displayScore;
            bestVideo = video;
        }
    });
    if (maxArea === 0)
    {
        if (iframeContainer) videoResizeObserver.unobserve(iframeContainer);
        return;
    }
    const rect = bestVideo.getBoundingClientRect();
    altSrc = "";
    const left = Math.max(Math.min(window.innerWidth - 10, rect.left + rect.width / 2), 10);
    const top = Math.max(Math.min(window.innerHeight - 10, rect.top + rect.height / 2), 10);
    const currentOrigin = new URL(windowHref()).origin;
    for (const el of document.elementsFromPoint(left, top))
    {
        if (el.tagName != "A") continue;
        try
        {
            const url = new URL(el.href, currentOrigin);
            if (currentOrigin === url.origin && url.pathname != '/') altSrc = url.href;
        }
        catch {}
    }
    while (bestVideo.parentElement !== document.body)
    {
        const parentRect = bestVideo.parentElement.getBoundingClientRect();
        if (parentRect.width > (rect.width * 1.02) || parentRect.height > (rect.height * 1.02)) break;
        bestVideo = bestVideo.parentElement;
    }
    console.debug(bestVideo);
    return bestVideo;
}


function setIframeStyle(prop, value)
{
    if (iframeStyle[prop] === value) return false;
    iframeStyle[prop] = value;
    iframe.style[prop] = (typeof value === 'number') ? `${value}px` : value;
    return true;
}


function createIframe(src='')
{
    if (iframe = document.getElementById('ytdlp-player')) return;
    console.log(`Creating iframe`);
    iframe = document.createElement('iframe');
    iframeStyle = {};
    iframe.id = 'ytdlp-player';
    iframe.style.border = 'none';
    iframe.style.zIndex = '9999';
    setIframeStyle('position', 'absolute');
    setIframeStyle('top', 0);
    setIframeStyle('left', 0);
    iframe.allowFullscreen = true;
    iframe.allow = 'autoplay';
    iframe.src = src;
    document.body.appendChild(iframe);
    setTimeout(() => {
        if (!editable(document.activeElement)) iframe?.focus();
    }, 2000);
    if (!cookies) return;
    try
    {
        chrome.runtime.sendMessage({ action: 'postCookies', playerUrl, documentCookies: document.cookie, currentWebsiteUrl: windowHref() });
    }
    catch (error)
    {
        console.warn(error);
    }
}


function updateIframeGeometry(forceZero = false)
{
    if (!tabEnabled || !iframe || document.fullscreenElement) return;
    const containerRect = iframeContainer?.getBoundingClientRect();
    const vidRect = iframeContainer?.querySelector('video')?.getBoundingClientRect();
    const width = Math.max(containerRect?.width || 0, vidRect?.width || 0);
    const height = Math.max(containerRect?.height || 0, vidRect?.height || 0);

    if ((width == 0 || height == 0) && 'width' in iframeStyle && 'height' in iframeStyle && !forceZero) return;

    setIframeStyle('width', width);
    setIframeStyle('height', height);

    if (containerRect && lastContainerRect)
    {
        const dY = containerRect.top - lastContainerRect.top;
        const dX = containerRect.left - lastContainerRect.left;
        const fixedChange = Math.abs(dY) + Math.abs(dX);
        const absoluteChange = Math.abs(dY + scrollY - lastScroll.y) + Math.abs(dX + scrollX - lastScroll.x);
        if (absoluteChange > fixedChange + 1) setIframeStyle('position', 'fixed');
        if (absoluteChange < fixedChange - 1) setIframeStyle('position', 'absolute');
    }

    lastContainerRect = containerRect;
    lastScroll = { x: scrollX, y: scrollY };

    const { top = 0, left = 0 } = iframeStyle;
    const iframeRect = iframeStyle.position == 'fixed' ? { top, left } : iframe.getBoundingClientRect();
    setIframeStyle('top', (containerRect?.top || 0) - iframeRect.top + top);
    setIframeStyle('left', (containerRect?.left || 0) - iframeRect.left + left);
}


function updateIframe(updateContainer = false)
{
    if (!tabEnabled) return;
    let src = altSrc || windowHref();
    let srcUrl = new URL(src);
    let iframeEnabled = srcUrl.pathname != '/' || srcUrl.search || altSrc;
    let iframeSrc = `${playerUrl}/iframe?url=${encodeURIComponent(src)}`;
    if (iframe?.src && iframe?.src != iframeSrc)
    {
        console.debug('Creating temporary cancellation iframe');
        let cancellingIframe = document.createElement('iframe');
        cancellingIframe.src = iframe.src.replace('/iframe?', '/cancel?');
        iframe.style.display = 'none';
        document.body.appendChild(cancellingIframe);
        setTimeout(() => {
            cancellingIframe?.remove();
            console.debug('Removed cancellation iframe');
        }, 1000);
    }
    if (iframeEnabled)
    {
        if (iframe?.src != iframeSrc)
        {
            console.log(`Changing iframe src from ${iframe?.src} to ${iframeSrc}`);
            iframe?.remove();
            createIframe(iframeSrc);
        }
        else if (iframe === null || !document.getElementById('ytdlp-player'))
        {
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
        updateIframeGeometry(!iframeEnabled);
    }
    else
    {
        if (iframeContainer)
        {
            iframeContainer.style.opacity = '';
            iframeContainer.style.pointerEvents = '';
            iframeContainer = null;
        }
        if (iframe !== null)
        {
            console.log('Disabling iframe');
            iframe.remove();
            iframe = null;
        }
    }
}


function start()
{
    tabEnabled = true;
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
        if (iframe !== null && !editable(e.target)) iframe.focus();
    });

    var geometryFrame, geometryFramesLeft;
    ['scroll', 'resize', 'transitionrun'].forEach(type => window.addEventListener(type, () => {
        if (!tabEnabled) return;
        geometryFramesLeft = 20;
        geometryFrame ??= requestAnimationFrame(function loop() {
            geometryFrame = null;
            updateIframeGeometry();
            if (tabEnabled && --geometryFramesLeft > 0) geometryFrame = requestAnimationFrame(loop);
        });
    }, { passive: true, capture: true }));
}


function stop()
{
    tabEnabled = false;
    if (iframe)
    {
        iframe.remove();
        iframe = null;
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
    if (!playerUrl && storage !== null && storageSync !== null)
    {
        storageSync.get({ playerUrl: '', cookies: false }, (items) => {
            playerUrl = items.playerUrl;
            cookies = items.cookies;
            tryStart();
        });
        storage.onChanged.addListener((changes, namespace) => {
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
        if (new URL(windowHref()).origin == new URL(playerUrl).origin) return;
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


function updateAllowedDomains(allowedDomains)
{
    const currentUrl = new URL(windowHref());
    const hostname = currentUrl.hostname;

    const allowedDomainsList = allowedDomains.split(',').map(domain => domain.trim());
    if (allowedDomainsList.some(allowedDomain => { return hostname === allowedDomain || hostname.endsWith(`.${allowedDomain}`); }))
    {
        tryStart();
        return true;
    }
    else
    {
        stop();
        return false;
    }
}


if (storage !== null && storageSync !== null)
{
    storageSync.get({ allowedDomains: '' }, (items) => {
        if (!items.allowedDomains) return;
        updateAllowedDomains(items.allowedDomains);
    });

    storage.onChanged.addListener((changes, namespace) => {
        if (namespace !== 'sync' || !changes.allowedDomains) return;
        updateAllowedDomains(changes.allowedDomains.newValue);
    });

    chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
        if (message.action === 'start') tryStart();
        else if (message.action === 'stop') stop();
        else if (message.action === 'getTabStatus') sendResponse({ status: tabEnabled && playerUrl });
    });
}
else
{
    try
    {

        playerUrl = playerUrl || GM_getValue("playerUrl", null);
        if (!playerUrl)
        {
            playerUrl = prompt("Enter YT-DLP Web Player URL (it will be saved in tampermonkey storage):");
            GM_setValue("playerUrl", playerUrl);
        }

        var startCmd = null;
        function GM_toggleStart(state = null)
        {
            if (startCmd) GM_unregisterMenuCommand(startCmd);
            tabEnabled = !tabEnabled;
            if (state === true || state === false) tabEnabled = state;
            if (tabEnabled)
            {
                startCmd = GM_registerMenuCommand("Stop", GM_toggleStart);
                start();
            }
            else
            {
                startCmd = GM_registerMenuCommand("Start", GM_toggleStart);
                stop();
            }
        }

        function GM_toggleDomain()
        {
            const domains = GM_loadDomains().split(',');
            const hostname = new URL(windowHref()).hostname;
            const newDomains = domains.includes(hostname) ? domains.filter(domain => domain !== hostname) : [...domains, hostname];
            GM_setValue("allowedDomains", newDomains.join(','));
            GM_toggleStart(updateAllowedDomains(GM_loadDomains()));
        }

        var domainCmd = null;
        function GM_loadDomains()
        {
            if (domainCmd) GM_unregisterMenuCommand(domainCmd);
            const domains = GM_getValue("allowedDomains", '').split(',').map(domain => domain.trim());
            const label = domains.includes(new URL(windowHref()).hostname) ? "Remove Current Domain" : "Add Current Domain";
            domainCmd = GM_registerMenuCommand(label, GM_toggleDomain);
            return domains.join(',');
        }

        if (new URL(windowHref()).origin != new URL(playerUrl).origin)
        {
            GM_toggleStart(updateAllowedDomains(GM_loadDomains()));
        }
    }
    catch
    {
        playerUrl = playerUrl || prompt("Enter YT-DLP Web Player URL:");
        tryStart();
    }
}