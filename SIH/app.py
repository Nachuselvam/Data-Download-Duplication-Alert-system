import os
import sqlite3
import hashlib
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import shutil
from plyer import notification
from flask import Flask, render_template_string, request
import webbrowser

# Flask setup
app = Flask(__name__)
file_to_check = None
temp_path = None

# HTML template for the popup page
html_template = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Duplicate File Alert</title>
</head>
<body>
    <h1>Duplicate File Detected!</h1>
    <p>{{ message }}</p>
    <form method="post" action="/handle_choice">
        <input type="hidden" name="keep" value="yes">
        <button type="submit">Keep File</button>
    </form>
    <form method="post" action="/handle_choice">
        <input type="hidden" name="keep" value="no">
        <button type="submit">Delete File</button>
    </form>
</body>
</html>
"""

# Function to compute file hash (SHA-256)
def compute_file_hash(filepath):
    sha256 = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            sha256.update(chunk)
    return sha256.hexdigest()

# Function to check for duplicates
def check_for_duplicates(cursor, filename, filesize, filehash):
    cursor.execute("SELECT * FROM downloads WHERE (filename=? OR filehash=?) AND filesize=?", (filename, filehash, filesize))
    return cursor.fetchone()

# Function to log new downloads
def log_download(cursor, filename, filesize, filehash):
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute("INSERT INTO downloads (filename, filesize, filehash, timestamp) VALUES (?, ?, ?, ?)",
                   (filename, filesize, filehash, timestamp))

# Function to display a notification
def show_notification(title, message):
    notification.notify(
        title=title,
        message=message,
        timeout=10  # Notification timeout in seconds
    )

# Flask route to handle user decision
@app.route('/notify', methods=['GET'])
def notify():
    global file_to_check
    msg = (f"A duplicate file was detected!\n\n"
           f"Filename: {file_to_check['filename']}\n"
           f"Original Filename: {file_to_check['duplicate'][1]}\n"
           f"Size: {file_to_check['filesize']} bytes\n"
           f"Original File Size: {file_to_check['duplicate'][2]} bytes\n"
           f"Timestamp of Original File: {file_to_check['duplicate'][4]}\n\n"
           "Do you want to keep this new download?")
    return render_template_string(html_template, message=msg)

@app.route('/handle_choice', methods=['POST'])
def handle_choice():
    global file_to_check, temp_path
    keep = request.form['keep'] == 'yes'
    if keep:
        # Move the file back to its original location
        shutil.move(temp_path, file_to_check['filepath'])
        conn = sqlite3.connect('downloads_metadata.db')
        cursor = conn.cursor()
        log_download(cursor, file_to_check['filename'], file_to_check['filesize'], file_to_check['filehash'])
        conn.commit()
        conn.close()
        print(f"Duplicate download kept: {file_to_check['filename']}")
    else:
        os.remove(temp_path)
        print(f"Duplicate download removed: {file_to_check['filename']}")
    return "Action completed! You can close this window."

# Handler for monitoring file downloads
class DownloadHandler(FileSystemEventHandler):
    def on_created(self, event):
        global file_to_check, temp_path
        if not event.is_directory:
            filepath = event.src_path
            filename = os.path.basename(filepath)
            filesize = os.path.getsize(filepath)
            filehash = compute_file_hash(filepath)

            # Establish a new database connection in this thread
            conn = sqlite3.connect('downloads_metadata.db')
            cursor = conn.cursor()

            # Check if the file is a duplicate
            duplicate = check_for_duplicates(cursor, filename, filesize, filehash)
            if duplicate:
                # Move the file to a temporary location to "pause" the download
                temp_path = filepath + ".tmp"
                shutil.move(filepath, temp_path)

                # Store file information to be used in the Flask app
                file_to_check = {
                    'filepath': filepath,
                    'filename': filename,
                    'filesize': filesize,
                    'filehash': filehash,
                    'cursor': cursor,
                    'duplicate': duplicate
                }

                # Display a notification alert
                show_notification("Duplicate File Alert", "A duplicate file was detected! Click to view details.")
                webbrowser.open("http://localhost:5000/notify", new=1)

            else:
                # Log the download if it's not a duplicate
                log_download(cursor, filename, filesize, filehash)
                print(f"New file downloaded and logged: {filename}")

            conn.commit()
            conn.close()

# Initialize the database connection and create the table (if not already created)
conn = sqlite3.connect('downloads_metadata.db')
cursor = conn.cursor()

cursor.execute('''
CREATE TABLE IF NOT EXISTS downloads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    filesize INTEGER NOT NULL,
    filehash TEXT NOT NULL,
    timestamp TEXT NOT NULL
)
''')
conn.commit()
conn.close()

# Specify the directory to monitor (default download directory)
download_directory = os.path.expanduser("~/Downloads")
event_handler = DownloadHandler()
observer = Observer()
observer.schedule(event_handler, download_directory, recursive=False)
observer.start()
print(f"Monitoring downloads in: {download_directory}")

# Run Flask in a separate thread
from threading import Thread
flask_thread = Thread(target=lambda: app.run(port=5000, debug=False))
flask_thread.start()

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    observer.stop()
observer.join()
