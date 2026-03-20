// Thanks to https://github.com/WithoutHair/Disable-Content-Security-Policy

// Options object to store dynamic settings
let options = {};

// Load options from storage
async function loadOptions() {
    options = await chrome.storage.sync.get({ iframeBaseUrl: '' });
    // Ensure options.iframeBaseUrl is always a string, even if empty
    if (typeof options.iframeBaseUrl !== 'string') {
        options.iframeBaseUrl = '';
    }
}

// Function to dynamically apply CSP rules based on iframeBaseUrl
async function applyCSPRule() {
    await loadOptions(); // Make sure options are loaded
    const { url } = await chrome.tabs.query({ active: true, lastFocusedWindow: true });

    if (!url) return; // No active tab found

    const ruleId = 1; // Consistent rule ID

    // Check if the current URL is the iframeBaseUrl or starts with it
    const isIframeBaseUrl = options.iframeBaseUrl && url.startsWith(options.iframeBaseUrl);

    // Remove existing rules with the same ID
    await chrome.declarativeNetRequest.updateSessionRules({ removeRuleIds: [ruleId] });

    // If the current tab is NOT the iframe base URL, apply the CSP modification
    if (!isIframeBaseUrl) {
        const rule = {
            id: ruleId,
            action: {
                type: 'modifyHeaders',
                responseHeaders: [{ header: 'content-security-policy', operation: 'set', value: '' }]
            },
            condition: { urlFilter: url, resourceTypes: ['main_frame', 'sub_frame'] }
        };
        await chrome.declarativeNetRequest.updateSessionRules({ addRules: [rule] });
    }

    updateIconAndTitle(); // Update icon based on whether CSP is applied
}

// Update the extension icon and title
async function updateIconAndTitle() {
    await loadOptions();
    const { url } = await chrome.tabs.query({ active: true, lastFocusedWindow: true });

    if (!url) return;

    const isIframeBaseUrl = options.iframeBaseUrl && url.startsWith(options.iframeBaseUrl);
    const iconSuffix = isIframeBaseUrl ? '' : '_gray'; // If it's the iframe URL, use colored icon, otherwise gray
    const title = isIframeBaseUrl ? 'CSP Enabled' : 'CSP Disabled';

    chrome.action.setIcon({ path: `icon/cola${iconSuffix}.png` });
    chrome.action.setTitle({ title: `CSP ${title}` });
}

// Listen for tab activations and URL changes
chrome.tabs.onActivated.addListener(applyCSPRule);
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
    if (changeInfo.url) {
        applyCSPRule();
    }
});

// Initial setup when the extension is first loaded
chrome.runtime.onInstalled.addListener(async () => {
    await loadOptions();
    applyCSPRule();
});

// Listen for changes in storage
chrome.storage.onChanged.addListener(async (changes, namespace) => {
    if (namespace === 'sync' && changes.iframeBaseUrl) {
        await loadOptions();
        applyCSPRule();
    }
});
