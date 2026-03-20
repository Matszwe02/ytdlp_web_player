function runScript() {
    try {
        'use strict';

        // --- Configuration ---
        let iframeBaseUrl = ''; // This will be loaded from chrome.storage.sync
        
        let currentIframe = null; 
        let currentLargestVideo = null; 
        let currentHiddenContainer = null; 
        let videoResizeObserver = null; 
        let applyLogicTimeout = null;

        // Initialize the ResizeObserver once
        videoResizeObserver = new ResizeObserver(() => {
            updateVideoVisibility();
            updateIframeGeometry();
        });

        // Find and hide the greatest parent within a 2% size margin, and manage its observation
        function updateVideoVisibility() {
            if (!currentLargestVideo) return;

            const videoRect = currentLargestVideo.getBoundingClientRect();
            let targetToHide = currentLargestVideo;
            let currentParent = currentLargestVideo.parentElement;

            // Traverse up the DOM tree
            while (currentParent && currentParent !== document.body) {
                const parentRect = currentParent.getBoundingClientRect();
                
                // Check if parent dimensions are at most 2% larger than the video
                const isWidthWithinMargin = parentRect.width <= (videoRect.width * 1.02);
                const isHeightWithinMargin = parentRect.height <= (videoRect.height * 1.02);

                if (isWidthWithinMargin && isHeightWithinMargin) {
                    targetToHide = currentParent;
                    currentParent = currentParent.parentElement;
                } else {
                    break; // Stop climbing when the 2% threshold is exceeded
                }
            }

            // If the targeted container has changed
            if (currentHiddenContainer && currentHiddenContainer !== targetToHide) {
                currentHiddenContainer.style.opacity = '';
                currentHiddenContainer.style.pointerEvents = '';
                // Unobserve the old container (unless it's the video itself, which we always track)
                if (currentHiddenContainer !== currentLargestVideo) {
                    videoResizeObserver.unobserve(currentHiddenContainer);
                }
            }

            currentHiddenContainer = targetToHide;

            // Apply styles and observe the new container
            if (currentHiddenContainer) {
                currentHiddenContainer.style.opacity = '0';
                currentHiddenContainer.style.pointerEvents = 'none';
                // Start observing the container to catch when the wrapper resizes
                if (currentHiddenContainer !== currentLargestVideo) {
                    videoResizeObserver.observe(currentHiddenContainer);
                }
            }
        }

        // Helper to update iframe geometry based on the hidden container
        function updateIframeGeometry() {
            if (!currentHiddenContainer || !currentIframe) return;
            
            const rect = currentHiddenContainer.getBoundingClientRect();
            Object.assign(currentIframe.style, {
                width: `${rect.width}px`,
                height: `${rect.height}px`,
                top: `${rect.top}px`,
                left: `${rect.left}px`
            });
        }

        // Debounce function
        function debounce(func, wait) {
            let timeout;
            return function(...args) {
                const context = this;
                clearTimeout(timeout);
                timeout = setTimeout(() => func.apply(context, args), wait);
            };
        }

        // Create a debounced version of updateIframeGeometry for scroll events
        const debouncedUpdateIframeGeometryOnScroll = debounce(updateIframeGeometry, 100); // Adjust debounce time as needed

        // Add scroll event listener
        window.addEventListener('scroll', debouncedUpdateIframeGeometryOnScroll, { passive: true });

        // Stop and disable a media element
        function stopAndDisableMedia(media) {
            if (!media) return;

            media.pause();
            try { media.load(); } catch (e) {} 
            
            media.removeAttribute('autoplay');
            media.removeAttribute('controls');
            media.muted = true;
            media.volume = 0;

            const preventEvent = (e) => {
                e.stopImmediatePropagation();
                e.preventDefault();
            };

            ['play', 'playing', 'canplay', 'canplaythrough', 'loadeddata', 'loadedmetadata', 'progress', 'seeking', 'seeked', 'timeupdate', 'ended']
                .forEach(evt => media.addEventListener(evt, preventEvent, true));
        }

        function applyVideoReplacementLogic() {
            currentUrl = new URL(window.top.location.href);
            if (currentUrl.pathname == '/' && !currentUrl.search) return;
            document.querySelectorAll('video, audio').forEach(stopAndDisableMedia);
            // Prevent recursion: do not run script on its own domain

            const foundLargestVideo = Array.from(document.querySelectorAll('video')).reduce((acc, video) => {
                const rect = video.getBoundingClientRect();
                const area = rect.width * rect.height;
                return area > acc.area ? { video, area } : acc;
            }, { video: null, area: 0 }).video;

            // If we found a new target video, or iframeBaseUrl changed
            if (foundLargestVideo !== currentLargestVideo || !iframeBaseUrl) { 
                
                // 1. Clean up old elements and observers
                if (currentHiddenContainer) {
                    currentHiddenContainer.style.opacity = '';
                    currentHiddenContainer.style.pointerEvents = '';
                    if (currentHiddenContainer !== currentLargestVideo) {
                        videoResizeObserver.unobserve(currentHiddenContainer);
                    }
                }
                if (currentLargestVideo) {
                    videoResizeObserver.unobserve(currentLargestVideo);
                }

                currentLargestVideo = foundLargestVideo;
                currentHiddenContainer = null;

            // 2. Setup the new elements
            // Remove existing iframes before creating a new one
            document.querySelectorAll('.content-replacer-iframe').forEach(iframe => iframe.remove());
            currentIframe = null; // Reset currentIframe

            if (currentLargestVideo && iframeBaseUrl) {
                currentIframe = document.createElement('iframe');
                currentIframe.className = 'content-replacer-iframe'; // Add helper class
                currentIframe.src = `${iframeBaseUrl}/iframe?url=${encodeURIComponent(window.top.location.href)}`;
                    Object.assign(currentIframe.style, {
                        border: 'none', position: 'fixed', zIndex: '9999'
                    });
                    currentIframe.allowFullscreen = true;
                    document.body.appendChild(currentIframe);

                    // Always observe the core video, just in case its intrinsic size changes
                    videoResizeObserver.observe(currentLargestVideo);
                } else {
                    currentIframe = null;
                }
            } 
            
            // 3. Process the logic (runs initially and on debounced DOM changes)
            if (currentLargestVideo && currentIframe) {
                updateVideoVisibility(); 
                updateIframeGeometry();  
            }

            document.querySelectorAll('video, audio').forEach(stopAndDisableMedia);
        }

        // Initial load of iframeBaseUrl from storage
        chrome.storage.sync.get({ iframeBaseUrl: '' }, (items) => {
            iframeBaseUrl = items.iframeBaseUrl;
            applyVideoReplacementLogic(); 
        });

        // Listen for changes in storage (e.g., from options page)
        chrome.storage.onChanged.addListener((changes, namespace) => {
            if (namespace === 'sync' && changes.iframeBaseUrl) {
                iframeBaseUrl = changes.iframeBaseUrl.newValue;
                applyVideoReplacementLogic(); 
            }
        });

        // --- Overrides ---
        const originalPlay = HTMLMediaElement.prototype.play;
        HTMLMediaElement.prototype.play = function() {
            if (this.tagName !== 'VIDEO' && this.tagName !== 'AUDIO') return originalPlay.apply(this, arguments);
            this.pause();
            this.currentTime = 0;
            return Promise.resolve();
        };

        const originalLoad = HTMLMediaElement.prototype.load;
        HTMLMediaElement.prototype.load = function() {
            if (this.tagName !== 'VIDEO' && this.tagName !== 'AUDIO') return originalLoad.apply(this, arguments);
            this.pause();
        };

        // --- SPA URL Handling ---
        let lastUrl = window.location.href;
        
        function handleUrlChange() {
            const currentUrl = window.location.href;
            if (currentUrl !== lastUrl) {
                lastUrl = currentUrl;
                
                // If a video is reused by the SPA (e.g. YouTube), update the iframe source directly.
                if (currentIframe && iframeBaseUrl) {
                    currentIframe.src = `${iframeBaseUrl}/iframe?url=${encodeURIComponent(currentUrl)}`;
                } else {
                    applyVideoReplacementLogic();
                }
            }
        }

        // Listen to native browser back/forward buttons
        window.addEventListener('popstate', handleUrlChange);

        // Modern Chromium Navigation API (Catches SPA routing perfectly)
        if (window.navigation) {
            window.navigation.addEventListener('navigate', () => {
                // Use setTimeout to allow the location object to update to the new route
                setTimeout(handleUrlChange, 0); 
            });
        }

        // --- Observers ---
        const observer = new MutationObserver(() => {
            // Check if URL changed during DOM updates (very common in SPAs)
            handleUrlChange();

            clearTimeout(applyLogicTimeout);
            applyLogicTimeout = setTimeout(applyVideoReplacementLogic, 200);
        });
        observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['src', 'autoplay', 'controls', 'style'] });

        // Fallback polling to guarantee we catch any sneaky history pushes 
        // that escape the Navigation API or DOM mutations
        setInterval(handleUrlChange, 500);

        // Initial run
        document.querySelectorAll('video, audio').forEach(stopAndDisableMedia);


        setInterval(() => {
            document.querySelectorAll('video, audio').forEach(stopAndDisableMedia);
        }, 500);

    } catch (error) {
        setTimeout(() => {
            runScript();
        }, 100);
    }
}

// --- Domain Check Logic ---
chrome.storage.sync.get({ allowedDomains: '' }, (items) => {
    const allowedDomainsString = items.allowedDomains;
    const currentUrlString = window.top.location.href;

    // If no domains are specified, the script is disabled by default.
    if (!allowedDomainsString) {
        return;
    }

    try {
        const currentUrl = new URL(currentUrlString);
        const hostname = currentUrl.hostname;

        const allowedDomains = allowedDomainsString.split(',').map(domain => domain.trim());

        // Check if the current hostname matches any of the allowed domains
        // or is a subdomain of an allowed domain.
        const isAllowedDomain = allowedDomains.some(allowedDomain => {
            // Exact match or subdomain match (e.g., "example.com" should match "www.example.com")
            return hostname === allowedDomain || hostname.endsWith(`.${allowedDomain}`);
        });

        if (isAllowedDomain) {
            runScript();
        }
    } catch (e) {
        console.error("Error checking domain:", e);
        // If URL parsing fails, do not run the script.
    }
});
