const storage = (typeof browser !== 'undefined' && browser.storage) ? browser.storage : (typeof chrome !== 'undefined' ? chrome.storage : null);
const storageSync = storage.sync || storage.local;


function renderAllowedDomains(domainsArray)
{
    const allowedDomainsList = document.getElementById('allowedDomainsList');
    allowedDomainsList.innerHTML = '';
    domainsArray.forEach((domain, index) => {
        const li = document.createElement('li');
        const span = document.createElement('span');
        span.textContent = domain;
        li.appendChild(span);

        const deleteButton = document.createElement('button');
        deleteButton.textContent = 'Remove';
        deleteButton.onclick = () => {
            updateDomains(getDomainsArray().filter((_, i) => i !== index));
        };
        li.appendChild(deleteButton);
        allowedDomainsList.appendChild(li);
    });

    chrome?.tabs?.query({ active: true, currentWindow: true }).then(tab =>{
        if (tab && tab[0].url)
        {
            const currentUrl = new URL(tab[0].url);
            const hostname = currentUrl.hostname;
            if (domainsArray.some(allowedDomain => { return hostname === allowedDomain || hostname.endsWith(`.${allowedDomain}`); }))
            {
                document.getElementById('addCurrentDomainButton').style.display = 'none';
                document.getElementById('removeCurrentDomainButton').style.display = 'block';
            }
            else
            {
                document.getElementById('addCurrentDomainButton').style.display = 'block';
                document.getElementById('removeCurrentDomainButton').style.display = 'none';
            }
        }
    });


}

function getDomainsArray()
{
    const domainsInput = document.getElementById('allowedDomains').value;
    if (!domainsInput) return [];
    return domainsInput.split(',').map(domain => domain.trim()).filter(domain => domain.length > 0);
}

function updateDomains(newDomainsArray)
{
    document.getElementById('allowedDomains').value = newDomainsArray.join(',');
    renderAllowedDomains(newDomainsArray);
    saveOptions();
}

function saveOptions()
{
    const playerUrl = document.getElementById('playerUrl').value.replace(/\/$/, '');
    const cookies = document.getElementById('cookies').checked;
    const allowedDomainsString = document.getElementById('allowedDomains').value;
    storageSync.set({ playerUrl: playerUrl, cookies: cookies, allowedDomains: allowedDomainsString }, () => {});
}

function restoreOptions()
{
    storageSync.get({ playerUrl: '', cookies: false, allowedDomains: '' }, (items) => {
        document.getElementById('playerUrl').value = items.playerUrl || 'http://localhost:5000';
        document.getElementById('cookies').checked = items.cookies;
        document.getElementById('allowedDomains').value = items.allowedDomains;
        renderAllowedDomains(items.allowedDomains.split(',').map(domain => domain.trim()).filter(domain => domain.length > 0));
    });
}

async function addCurrentDomain()
{
    const [tab] = await chrome?.tabs?.query({ active: true, currentWindow: true });
    if (!tab || !tab.url)
    {
        alert("Could not get current tab information");
        return;
    }
    try
    {
        const url = new URL(tab.url);
        const domain = url.hostname;
        
        const currentDomainsArray = getDomainsArray();
        if (currentDomainsArray.includes(domain))
        {
            alert('Domain already in the list');
            return;
        }
        currentDomainsArray.push(domain);
        updateDomains(currentDomainsArray);
    }
    catch (e)
    {
        alert("Could not parse URL or add domain");
    }
}

async function removeCurrentDomain()
{
    const [tab] = await chrome?.tabs?.query({ active: true, currentWindow: true });
    if (!tab || !tab.url)
    {
        alert("Could not get current tab information");
        return;
    }
    try
    {
        const url = new URL(tab.url);
        const domain = url.hostname;
        
        const currentDomainsArray = getDomainsArray();
        if (!currentDomainsArray.includes(domain))
        {
            alert('Domain not in the list');
            return;
        }
        currentDomainsArray.pop(domain);
        updateDomains(currentDomainsArray);
    }
    catch (e)
    {
        alert("Could not parse URL or add domain");
    }
}

async function sendMsg(action)
{
    const [tab] = await chrome?.tabs?.query({ active: true, currentWindow: true });
    if (!tab || !tab.id) return;
    chrome.tabs.sendMessage(tab.id, { action: action });
}


document.addEventListener('DOMContentLoaded', restoreOptions);
document.getElementById('addCurrentDomainButton').addEventListener('click', addCurrentDomain);
document.getElementById('removeCurrentDomainButton').addEventListener('click', removeCurrentDomain);
document.getElementById('startCurrentTabButton').addEventListener('click', () => sendMsg('start'));
document.getElementById('stopCurrentTabButton').addEventListener('click', () => sendMsg('stop'));
let playerUrlTimeoutId = null;
document.getElementById('playerUrl').addEventListener('input', () => {
    if (playerUrlTimeoutId) clearTimeout(playerUrlTimeoutId);
    playerUrlTimeoutId = setTimeout(() => {
        saveOptions();
        playerUrlTimeoutId = null;
    }, 1000);
});
document.getElementById('cookies').addEventListener('input', saveOptions);
document.getElementById('allowedDomains').addEventListener('input', saveOptions);
