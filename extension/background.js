chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "open-in-app",
    title: "Open in YT-DLP Player",
    contexts: ["link"]
  });
});

var urlBase = 'localhost';

// Initial load of iframeBaseUrl from storage
chrome.storage.sync.get({ iframeBaseUrl: '' }, (items) => {
    urlBase = items.iframeBaseUrl;
});

// Listen for changes in storage (e.g., from options page)
chrome.storage.onChanged.addListener((changes, namespace) => {
    if (namespace === 'sync' && changes.iframeBaseUrl) {
        urlBase = changes.iframeBaseUrl.newValue;
    }
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === "open-in-app" && info.linkUrl) {
    const targetUrl = urlBase + '/watch?url=' + encodeURIComponent(info.linkUrl);
    
    // Open in NEW INCOGNITO WINDOW
    chrome.windows.create({
      incognito: true,
      url: targetUrl,
      type: "popup",
      focused: true,
      state: "maximized"
    });
  }
});

