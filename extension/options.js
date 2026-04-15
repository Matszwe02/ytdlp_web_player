
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
    const iframeBaseUrl = document.getElementById('iframeBaseUrl').value;
    const cookies = document.getElementById('cookies').checked;
    const allowedDomainsString = document.getElementById('allowedDomains').value;
    chrome.storage.sync.set({ iframeBaseUrl: iframeBaseUrl, cookies: cookies, allowedDomains: allowedDomainsString }, () => {});
}

function restoreOptions()
{
    chrome.storage.sync.get({ iframeBaseUrl: '', cookies: false, allowedDomains: '' }, (items) => {
        document.getElementById('iframeBaseUrl').value = items.iframeBaseUrl;
        document.getElementById('cookies').checked = items.cookies;
        document.getElementById('allowedDomains').value = items.allowedDomains;
        renderAllowedDomains(items.allowedDomains.split(',').map(domain => domain.trim()).filter(domain => domain.length > 0));
    });
}

async function addCurrentDomain()
{
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
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


document.addEventListener('DOMContentLoaded', restoreOptions);
document.getElementById('addCurrentDomainButton').addEventListener('click', addCurrentDomain);
document.getElementById('iframeBaseUrl').addEventListener('input', saveOptions);
document.getElementById('cookies').addEventListener('input', saveOptions);
document.getElementById('allowedDomains').addEventListener('input', saveOptions);
