// Thanks to https://github.com/WithoutHair/Disable-Content-Security-Policy

let options = {};


async function loadOptions()
{
    options = await chrome.storage.sync.get({ playerUrl: '' });
    if (typeof options.playerUrl !== 'string') options.playerUrl = '';
}


async function applyCSPRule()
{
    await loadOptions();
    const { url } = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
    if (!url) return;

    const ruleId = 1;
    await chrome.declarativeNetRequest.updateSessionRules({ removeRuleIds: [ruleId] });

    if (url.startsWith(options.playerUrl)) return;

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


chrome.tabs.onActivated.addListener(applyCSPRule);

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
    if (!changeInfo.url) return;
    applyCSPRule();
});

chrome.runtime.onInstalled.addListener(async () => {
    applyCSPRule();
});

chrome.storage.onChanged.addListener(async (changes, namespace) => {
    if (namespace != 'sync' || !changes.playerUrl) return;
    applyCSPRule();
});
