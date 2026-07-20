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
var iframeContainer = null;
var cookies = false;
var lastContainerRect = null;
var lastBodyRect = null;
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
    let ordered_video_types = ['.html5-video-player', 'shreddit-player', 'video', 'img'];
    let allVideos = [];
    for (let index = 0; index < ordered_video_types.length; index++) {
        allVideos = Array.from(document.querySelectorAll(ordered_video_types[index]));
        if (allVideos.length > 0)
        {
            console.debug(`Total videos of type "${ordered_video_types[index]}" found: ${allVideos.length}`);
            break;
        }
    }


    let maxArea = 0;
    let bestVideo = null;
    let maxDisplayScore = -Infinity;

    allVideos.forEach(video => {
        const rect = video.getBoundingClientRect();
        const area = rect.width * rect.height;
        const closeX = Math.min(rect.left - 0, window.innerWidth - rect.right);
        const closeY = Math.min(rect.top - 0, window.innerHeight - rect.bottom);
        const visibilityScore = Math.max(Math.min(Math.min(closeX, closeY), (window.innerHeight + window.innerWidth) / 4), -(window.innerHeight + window.innerWidth) / 8);
        console.debug(`Visibility score: ${visibilityScore}`);
        const displayScore = Math.sqrt(area) + visibilityScore * 2;
        if (area > maxArea) maxArea = area;

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
    if (bestVideo)
    {
        const rect = bestVideo.getBoundingClientRect();

        altSrc = "";
        let a = bestVideo;
        while (a.parentElement !== document.body)
        {
            a = a.parentElement;
        }
        let left = Math.max(Math.min(window.innerWidth - 10, rect.left + rect.width / 2), 10);
        let top = Math.max(Math.min(window.innerHeight - 10, rect.top + rect.height / 2), 10);
        document.elementsFromPoint(left, top).forEach((el, i) => {
            if (el.tagName == "A") altSrc = el.href;
        });
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
    iframe.style.position = 'fixed';
    iframe.style.zIndex = '9999';
    iframe.style.top = '0px';
    iframe.style.left = '0px';
    iframe.allowFullscreen = true;
    iframe.allow = 'autoplay';
    iframe.src = src;
    document.body.appendChild(iframe);
    setTimeout(() => {
        iframe.focus();
    }, 2000);
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
    if (document.fullscreenElement !== null) return;
    const containerRect = iframeContainer?.getBoundingClientRect();
    const vidRect = iframeContainer?.querySelector('video')?.getBoundingClientRect();
    const iframeRect = iframe ? iframe.getBoundingClientRect() : null;
    const bodyRect = document.body.getBoundingClientRect();
    if (!iframeRect) return;
    const width = Math.max(containerRect?.width || 0, vidRect?.width || 0);
    const height = Math.max(containerRect?.height || 0, vidRect?.height || 0);

    if ((width == 0 || height == 0) && iframe.style.width && iframe.style.height && !forceZero)
    {
        return;
    }

    iframe.style.width = `${width}px`;
    iframe.style.height = `${height}px`;

    if (containerRect && lastContainerRect && bodyRect && lastBodyRect)
    {
        var fixedChange = Math.abs(containerRect.top - lastContainerRect.top) + Math.abs(containerRect.left - lastContainerRect.left);
        var absoluteChange = Math.abs((containerRect.top - lastContainerRect.top) - (bodyRect.top - lastBodyRect.top))
            + Math.abs((containerRect.left - lastContainerRect.left) - (bodyRect.left - lastBodyRect.left));

        if (absoluteChange > fixedChange + 1) iframe.style.position = 'fixed';
        if (absoluteChange < fixedChange - 1) iframe.style.position = 'absolute';
    }

    lastContainerRect = containerRect;
    lastBodyRect = bodyRect;

    if (iframe.style.position == 'fixed')
    {
        iframe.style.top = `${containerRect?.top || 0}px`;
        iframe.style.left = `${containerRect?.left || 0}px`;
    }
    else
    {
        iframe.style.top = `${(containerRect?.top || 0) - iframeRect.top + parseFloat(iframe.style.top || 0)}px`;
        iframe.style.left = `${(containerRect?.left || 0) - iframeRect.left + parseFloat(iframe.style.left || 0)}px`;
    }
}


function updateIframe(updateContainer = false)
{
    if (!tabEnabled) return;
    let src = altSrc || window.top.location.href;
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
    const currentUrl = new URL(window.top.location.href);
    const hostname = currentUrl.hostname;

    const allowedDomainsList = allowedDomains.split(',').map(domain => domain.trim());
    if (allowedDomainsList.some(allowedDomain => { return hostname === allowedDomain || hostname.endsWith(`.${allowedDomain}`); }))
    {
        tryStart();
    }
    else
    {
        stop();
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
else
{
    try
    {
        GM_registerMenuCommand("Start", start);
        GM_registerMenuCommand("Stop", stop);

        playerUrl = playerUrl || GM_getValue("playerUrl", null);
        if (!playerUrl)
        {
            playerUrl = prompt("Enter YT-DLP Web Player URL (it will be saved in tampermonkey storage):");
            GM_setValue("playerUrl", playerUrl);
        }

        function GM_toggleDomain()
        {
            var allowedDomains = GM_loadDomains().split(',');
            const currentUrl = new URL(window.top.location.href);
            if (allowedDomains.includes(currentUrl.hostname))
            {
                allowedDomains.pop(currentUrl.hostname);
            }
            else
            {
                allowedDomains.push(currentUrl.hostname);
            }
            allowedDomains = allowedDomains.join(',');
            GM_setValue("allowedDomains", allowedDomains);
            updateAllowedDomains(GM_loadDomains());   
        }

        var cmd = null;
        function GM_loadDomains()
        {
            if (cmd) GM_unregisterMenuCommand(cmd);
            var allowedDomains = GM_getValue("allowedDomains", '').split(',').map(domain => domain.trim());
            console.warn(allowedDomains);
            const currentUrl = new URL(window.top.location.href);
            if (allowedDomains.includes(currentUrl.hostname))
            {
                cmd = GM_registerMenuCommand("Remove Current Domain", GM_toggleDomain);
            }
            else
            {
                cmd = GM_registerMenuCommand("Add Current Domain", GM_toggleDomain);
            }
            return allowedDomains.join(',');
        }
        updateAllowedDomains(GM_loadDomains());
    }
    catch
    {
        if (!playerUrl)
        {
            playerUrl = prompt("Enter YT-DLP Web Player URL:");
        }
        tryStart();
    }
}