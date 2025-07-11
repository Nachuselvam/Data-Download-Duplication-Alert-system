// background.js

// Listen for download events
chrome.downloads.onDeterminingFilename.addListener((downloadItem, suggest) => {
    const fileName = downloadItem.filename;

    // Send a request to the Flask server to check if the file is a duplicate
    fetch('http://localhost:5000/check-file', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ file_name: fileName })
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'duplicate') {
            // Show an alert if the file is a duplicate
            chrome.notifications.create({
                type: "basic",
                iconUrl: "icon.png",
                title: "Duplicate Download Alert",
                message: `The file "${fileName}" already exists in your downloads.`
            });

            // Cancel the download
            chrome.downloads.cancel(downloadItem.id);
        } else {
            // Proceed with the download
            suggest({ filename: fileName });
        }
    })
    .catch(error => {
        console.error('Error:', error);
    });
});
