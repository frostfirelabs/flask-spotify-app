import os, requests, zipfile
from flask import Flask, redirect, request, jsonify, send_file, url_for
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import yt_dlp
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC, TIT2, TPE1, TALB

app = Flask(__name__)

# Spotify OAuth setup
sp_oauth = SpotifyOAuth(
    client_id="f0ab25b12248424792bdb4f9267d55e1",
    client_secret="e506d3b1d7004be498bd89af3e0e2cd3",
    redirect_uri="https://flask-spotify-app-8jib.onrender.com/",
    scope="playlist-read-private"
)

def download_song(query, filename):
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': filename,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([f"ytsearch:{query}"])

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
        audio.tags.add(APIC(
            encoding=3,
            mime='image/jpeg',
            type=3,
            desc='Cover',
            data=img_data
        ))
    audio.save()

@app.route("/")
def index():
    return """
    <html>
      <head><title>Spotify Downloader</title></head>
      <body>
        <h1>Spotify → YouTube Downloader</h1>
        <a href="/login">Login with Spotify</a>
      </body>
    </html>
    """

@app.route("/login")
def login():
    auth_url = sp_oauth.get_authorize_url()
    return redirect(auth_url)

@app.route("/callback")
def callback():
    code = request.args.get("code")
    token_info = sp_oauth.get_access_token(code)
    sp = spotipy.Spotify(auth=token_info['access_token'])
    playlists = sp.current_user_playlists()
    html = "<h2>Your Playlists</h2><ul>"
    for p in playlists['items']:
        html += f'<li>{p["name"]} - <a href="/download/{p["id"]}">Download</a></li>'
    html += "</ul>"
    return html

@app.route("/download/<playlist_id>")
def download_playlist(playlist_id):
    sp = spotipy.Spotify(auth_manager=sp_oauth)
    playlist = sp.playlist(playlist_id)
    playlist_name = playlist['name']
    folder = os.path.join("downloads", playlist_name)
    os.makedirs(folder, exist_ok=True)

    for item in playlist['tracks']['items']:
        track = item['track']
        title = track['name']
        artist = track['artists'][0]['name']
        album = track['album']['name']
        cover_url = track['album']['images'][0]['url'] if track['album']['images'] else None

        filename = os.path.join(folder, f"{title}.mp3")
        download_song(f"{title} {artist}", filename)
        embed_metadata(filename, title, artist, album, cover_url)

    # Zip the folder
    zip_path = f"{folder}.zip"
    with zipfile.ZipFile(zip_path, 'w') as zipf:
        for root, _, files in os.walk(folder):
            for file in files:
                zipf.write(os.path.join(root, file), arcname=file)

    return send_file(zip_path, as_attachment=True, download_name=f"{playlist_name}.zip")

if __name__ == "__main__":
    app.run(ssl_context=('cert.pem', 'key.pem'))
