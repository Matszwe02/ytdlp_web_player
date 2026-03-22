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

        // Function to request background script to post cookies to the iframe's server
        function requestPostCookies(iframeBaseUrl) {
            if (!iframeBaseUrl) {
                console.warn('iframeBaseUrl is not set, cannot request posting cookies.');
                return;
            }
            const documentCookies = document.cookie;
            if (documentCookies) {
                chrome.runtime.sendMessage({
                    action: 'postNetscapeCookies',
                    iframeBaseUrl: iframeBaseUrl,
                    documentCookies: documentCookies,
                    currentWebsiteUrl: window.top.location.href // Keep this to send the URL context
                });
            }
        }

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
            console.log(`Updating iframe geometry`);
            if (!currentHiddenContainer || !currentIframe) return;
            
            const rect = currentHiddenContainer.getBoundingClientRect();
            const vidRect = currentLargestVideo.getBoundingClientRect();

            currentIframe.style.width = `${Math.max(rect.width, vidRect.width)}px`;
            currentIframe.style.height = `${Math.max(rect.height, vidRect.height)}px`;
            currentIframe.style.transform = `translate(${rect.left}px, ${rect.top}px)`;
        }

        // Add scroll event listener
        window.addEventListener('scroll', updateIframeGeometry, { passive: true });

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

            // --- Video Selection Logic ---
            const allVideos = Array.from(document.querySelectorAll('video')).concat(Array.from(document.querySelectorAll('.html5-video-player')));
            console.log(`Total videos found: ${allVideos.length}`);

            // Filter out videos with zero or negative dimensions.
            const validDimensionVideos = allVideos.filter(video => {
                const rect = video.getBoundingClientRect();
                const area = rect.width * rect.height;
                console.log(`  - Video: Pos={top:${rect.top}, left:${rect.left}}, Size={w:${rect.width}, h:${rect.height}}, Area:${area}`);
                if (rect.width <= 0 || rect.height <= 0) {
                    console.log(`    -> Filtered out: zero or negative dimensions.`);
                    return false;
                }
                return true;
            });
            console.log(`Videos passing dimension filter: ${validDimensionVideos.length}`);

            if (validDimensionVideos.length === 0) {
                // No videos found, clean up and return
                if (currentLargestVideo) videoResizeObserver.unobserve(currentLargestVideo);
                currentLargestVideo = null;
                currentHiddenContainer = null;
                document.querySelectorAll('.content-replacer-iframe').forEach(iframe => iframe.remove());
                currentIframe = null;
                return;
            }

            // Find the maximum area among all videos with valid dimensions.
            let maxArea = 0;
            validDimensionVideos.forEach(video => {
                const rect = video.getBoundingClientRect();
                const area = rect.width * rect.height;
                if (area > maxArea) {
                    maxArea = area;
                }
            });

            // Define the minimum valid area based on 20% tolerance.
            const minValidArea = maxArea * 0.80;

            // Filter for videos that are within the valid area range (close to the largest).
            const potentialCandidates = validDimensionVideos.filter(video => {
                const rect = video.getBoundingClientRect();
                const area = rect.width * rect.height;
                return area >= minValidArea;
            });
            console.log(`Potential candidates (area >= ${minValidArea.toFixed(2)}): ${potentialCandidates.length}`);

            const viewportWidth = window.innerWidth;
            const viewportHeight = window.innerHeight;

            // Function to calculate visible intersection area
            const calculateIntersectionArea = (videoRect) => {
                const intersectionLeft = Math.max(videoRect.left, 0);
                const intersectionTop = Math.max(videoRect.top, 0);
                const intersectionRight = Math.min(videoRect.right, viewportWidth);
                const intersectionBottom = Math.min(videoRect.bottom, viewportHeight);

                const intersectionWidth = Math.max(0, intersectionRight - intersectionLeft);
                const intersectionHeight = Math.max(0, intersectionBottom - intersectionTop);
                return intersectionWidth * intersectionHeight;
            };

            let bestVideo = null;
            let maxIntersectionArea = -1;
            let maxAreaAmongTiedIntersection = -1; // For tie-breaking

            potentialCandidates.forEach(video => {
                const rect = video.getBoundingClientRect();
                const intersectionArea = calculateIntersectionArea(rect);
                const videoArea = rect.width * rect.height; // Total area of the video

                console.log(`  - Candidate: Total Area - ${videoArea.toFixed(2)}, Intersection Area - ${intersectionArea.toFixed(2)}, Pos={top:${rect.top}, left:${rect.left}}, Size={w:${rect.width}, h:${rect.height}}`);

                // Primary sorting criteria: Maximize intersection area.
                if (intersectionArea > maxIntersectionArea) {
                    maxIntersectionArea = intersectionArea;
                    maxAreaAmongTiedIntersection = videoArea; // Reset tie-breaker
                    bestVideo = video;
                } 
                // Secondary sorting criteria: If intersection areas are tied, pick the one with larger total area.
                else if (intersectionArea === maxIntersectionArea && videoArea > maxAreaAmongTiedIntersection) {
                    maxAreaAmongTiedIntersection = videoArea; // Update tie-breaker
                    bestVideo = video;
                }
            });
            // --- End Video Selection Logic ---
            
            // The logic below now uses 'bestVideo' instead of 'foundLargestVideo'
            // Check if the selected video has changed or if iframeBaseUrl is needed
            if (bestVideo !== currentLargestVideo || !iframeBaseUrl) { 
                
                // 1. Clean up old elements and observers
                if (currentHiddenContainer) {
                    currentHiddenContainer.style.opacity = '';
                    currentHiddenContainer.style.pointerEvents = '';
                }

                // Request background script to post cookies when iframe is about to be created/updated
                if (iframeBaseUrl) {
                    requestPostCookies(iframeBaseUrl);
                }

                // Unobserve the old video if it exists and is different from the new best video.
                if (currentLargestVideo && currentLargestVideo !== bestVideo) {
                    videoResizeObserver.unobserve(currentLargestVideo);
                }

                currentLargestVideo = bestVideo; // Assign the selected video
                currentHiddenContainer = null; // Reset hidden container, it will be re-evaluated by updateVideoVisibility

            // 2. Setup the new elements
            // Remove existing iframes before creating a new one
            document.querySelectorAll('.content-replacer-iframe').forEach(iframe => iframe.remove());
            currentIframe = null; // Reset currentIframe

            if (currentLargestVideo && iframeBaseUrl) {
                currentIframe = document.createElement('iframe');
                currentIframe.className = 'content-replacer-iframe'; // Add helper class
                currentIframe.src = `${iframeBaseUrl}/iframe?url=${encodeURIComponent(window.top.location.href)}`;
                    Object.assign(currentIframe.style, {
                        border: 'none', position: 'fixed', zIndex: '9999', top: '0px', left: '0px'
                    });
                    currentIframe.allowFullscreen = true;
                    document.body.appendChild(currentIframe);

                    // Always observe the new video (if it exists and is valid)
                    if (currentLargestVideo) { // Ensure currentLargestVideo is not null
                        videoResizeObserver.observe(currentLargestVideo);
                    }
                } else {
                    currentIframe = null;
                }
            } 
            
            // 3. Process the logic (runs initially and on debounced DOM changes)
            // Use the new currentLargestVideo here to update visibility and geometry
            if (currentLargestVideo && currentIframe) {
                updateVideoVisibility(); 
                updateIframeGeometry();  
            }
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
                    requestPostCookies(iframeBaseUrl); // Request background script to post cookies on URL change
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