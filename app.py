import os, requests, zipfile
from flask import Flask, redirect, request, send_file, render_template_string
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import yt_dlp
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC, TIT2, TPE1, TALB

app = Flask(__name__)

# Spotify OAuth setup
sp_oauth = SpotifyOAuth(
    client_id=os.environ.get("SPOTIPY_CLIENT_ID"),
    client_secret=os.environ.get("SPOTIPY_CLIENT_SECRET"),
    redirect_uri=os.environ.get("SPOTIPY_REDIRECT_URI", "https://flask-spotify-app-8jib.onrender.com/callback"),
    scope="playlist-read-private"
)

# Write YouTube cookies from env var to /tmp/cookies.txt
# Dark HTML template
INDEX_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Spotify Downloader</title>
  <style>
    body {
      background-color: #121212;
      color: #e0e0e0;
      font-family: 'Segoe UI', sans-serif;
      text-align: center;
      padding: 40px;
    }
    a {
      color: #1db954;
      text-decoration: none;
      font-weight: bold;
    }
    a:hover { text-decoration: underline; }
    h1, h2 { margin-bottom: 20px; }
    ul { list-style: none; padding: 0; }
    li { margin: 10px 0; }
    .btn {
      background-color: #1db954;
      color: #fff;
      padding: 10px 20px;
      border: none;
      border-radius: 25px;
      font-size: 16px;
      cursor: pointer;
    }
    .btn:hover { background-color: #1ed760; }
  </style>
</head>
<body>
  <h1>Spotify → YouTube Downloader</h1>
  <a class="btn" href="/login">Login with Spotify</a>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(INDEX_HTML)

@app.route("/login")
def login():
    return redirect(sp_oauth.get_authorize_url())

@app.route("/callback")
def callback():
    code = request.args.get("code")
    token_info = sp_oauth.get_access_token(code)
    sp = spotipy.Spotify(auth=token_info['access_token'])
    playlists = sp.current_user_playlists()

    html = """
    <html><head><title>Your Playlists</title></head>
    <body style="background:#121212;color:#e0e0e0;font-family:sans-serif;">
    <h2>Your Playlists</h2><ul>
    """
    for p in playlists['items']:
        html += f'<li>{p["name"]} - <a href="/download/{p["id"]}">Download</a></li>'
    html += "</ul></body></html>"
    return html

def download_song(query, filename):
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': filename,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        # Reduce bot-like behavior
        'quiet': True,
        'noplaylist': True,  # avoid triggering playlist scraping
        'http_headers': {
            'User-Agent': (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        },
        'sleep_interval': 2,   # wait between requests
        'max_sleep_interval': 5
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([f"ytsearch1:{query}"])  # only grab the top result



def embed_metadata(file_path, title, artist, album, cover_url):
    audio = MP3(file_path, ID3=ID3)
    try:
        audio.add_tags()
    except Exception:
        pass
    audio.tags.add(TIT2(encoding=3, text=title))
    audio.tags.add(TPE1(encoding=3, text=artist))
    audio.tags.add(TALB(encoding=3, text=album))
    if cover_url:
        img_data = requests.get(cover_url).content
        audio.tags.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='Cover', data=img_data))
    audio.save()

@app.route("/download/<playlist_id>")
def download_playlist(playlist_id):
    sp = spotipy.Spotify(auth_manager=sp_oauth)
    playlist = sp.playlist(playlist_id)
    playlist_name = playlist['name']
    folder = os.path.join("/tmp", playlist_name)
    os.makedirs(folder, exist_ok=True)

    for item in playlist['tracks']['items']:
        track = item['track']
        title = track['name']
        artist = track['artists'][0]['name']
        album = track['album']['name']
        cover_url = track['album']['images'][0]['url'] if track['album']['images'] else None
        duration = track['duration_ms'] // 1000

        # Find best YouTube match (no cookies)
        ydl_opts = {'quiet': True, 'skip_download': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch5:{title} {artist}", download=False)

        # Pick closest duration match
        best = min(info['entries'], key=lambda v: abs(v['duration'] - duration))
        video_url = best['webpage_url']

        filename = os.path.join(folder, f"{title}.mp3")

        # Download audio
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': filename,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'quiet': True
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])

        # Embed metadata
        embed_metadata(filename, title, artist, album, cover_url)

    # Package into ZIP
    zip_path = f"{folder}.zip"
    with zipfile.ZipFile(zip_path, 'w') as zipf:
        for root, _, files in os.walk(folder):
            for file in files:
                zipf.write(os.path.join(root, file), arcname=file)

    return send_file(zip_path, as_attachment=True, download_name=f"{playlist_name}.zip")


if __name__ == "__main__":
    app.run(ssl_context=('cert.pem', 'key.pem'))
