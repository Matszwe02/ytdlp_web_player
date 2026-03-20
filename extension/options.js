document.addEventListener('DOMContentLoaded', restoreOptions);
document.getElementById('addCurrentDomainButton').addEventListener('click', addCurrentDomain);

// Auto-save on input changes
document.getElementById('iframeBaseUrl').addEventListener('input', saveOptions);
document.getElementById('allowedDomains').addEventListener('input', saveOptions);

// Helper function to render the list of allowed domains
function renderAllowedDomains(domainsArray) {
    const allowedDomainsList = document.getElementById('allowedDomainsList');
    allowedDomainsList.innerHTML = ''; // Clear current list
    domainsArray.forEach((domain, index) => {
        const li = document.createElement('li');
        const span = document.createElement('span');
        span.textContent = domain;
        li.appendChild(span);

        const deleteButton = document.createElement('button');
        deleteButton.textContent = 'Remove';
        deleteButton.onclick = () => {
            const currentDomains = getDomainsArray();
            const newDomains = currentDomains.filter((_, i) => i !== index);
            updateDomains(newDomains);
        };
        li.appendChild(deleteButton);
        allowedDomainsList.appendChild(li);
    });
}

// Helper function to get domains as an array from the input or storage
function getDomainsArray() {
    const domainsInput = document.getElementById('allowedDomains').value;
    if (!domainsInput) return [];
    return domainsInput.split(',').map(domain => domain.trim()).filter(domain => domain.length > 0);
}

// Helper function to update both the input field and the displayed list
function updateDomains(newDomainsArray) {
    const domainsString = newDomainsArray.join(',');
    document.getElementById('allowedDomains').value = domainsString;
    renderAllowedDomains(newDomainsArray);
    saveOptions(); // Auto-save after updating domains
}

function saveOptions() {
    const iframeBaseUrl = document.getElementById('iframeBaseUrl').value;
    const allowedDomainsString = document.getElementById('allowedDomains').value; // Get the comma-separated string
    
    chrome.storage.sync.set({ iframeBaseUrl: iframeBaseUrl, allowedDomains: allowedDomainsString }, () => {
        const status = document.getElementById('status');
        status.textContent = 'Options saved.';
        setTimeout(() => {
            status.textContent = '';
        }, 750);
    });
}

function restoreOptions() {
    // Retrieve both settings
    chrome.storage.sync.get({ iframeBaseUrl: '', allowedDomains: '' }, (items) => {
        document.getElementById('iframeBaseUrl').value = items.iframeBaseUrl;
        document.getElementById('allowedDomains').value = items.allowedDomains; // Restore the input value

        // Render the domains list
        const domainsArray = items.allowedDomains.split(',').map(domain => domain.trim()).filter(domain => domain.length > 0);
        renderAllowedDomains(domainsArray);
    });
}

async function addCurrentDomain() {
    // Get the current tab URL
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tab && tab.url) {
        try {
            const url = new URL(tab.url);
            const domain = url.hostname; // e.g., "www.example.com"
            
            const currentDomainsArray = getDomainsArray();
            if (!currentDomainsArray.includes(domain)) {
                currentDomainsArray.push(domain);
                updateDomains(currentDomainsArray);
            } else {
                alert('Domain already in the list.');
            }
        } catch (e) {
            console.error("Could not parse URL or add domain:", e);
            alert("Could not extract domain from the current URL.");
        }
    } else {
        alert("Could not get current tab information.");
    }
}
