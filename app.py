import os
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from flask import Flask, render_template, redirect, request, session, url_for
import random

import config  # Import the config file

# Initialize Flask app and session management
app = Flask(__name__)
app.secret_key = os.urandom(24)
app.config['SESSION_COOKIE_NAME'] = 'spotify_session'
app.config['SESSION_TYPE'] = 'filesystem'
# Session(app)

# Spotify API credentials
CLIENT_ID = config.CLIENT_ID
CLIENT_SECRET = config.CLIENT_SECRET
REDIRECT_URI = config.REDIRECT_URI
SCOPE = "user-library-read playlist-modify-private playlist-read-private playlist-read-collaborative user-read-private"


sp_oauth = SpotifyOAuth(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, redirect_uri=REDIRECT_URI, scope=SCOPE)

# Global variables
playlists = {}
playlist_ids = {}
songs_to_sort = []

# Initial languages for playlist creation
# initial_languages = ['Hindi', 'English']

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login')
def login():
    auth_url = sp_oauth.get_authorize_url()
    return redirect(auth_url)


def get_playlists(sp):
    results = sp.current_user_playlists(limit=50)
    while results:
        for item in results['items']:
            if len(item['name']) == 0:
                continue
            # print(item['name'], len(item['name']), type(item['name']))
            if item['name'][-1] == ' ':
                # playlists.append({
                #     'name': item['name'],
                #     'id': item['id'],
                #     'owner': item['owner']['display_name'],
                #     'tracks': item['tracks']['total']
                # })
                print(item['name'])
                playlists[item['name']] = item['id']
        if results['next']:
            results = sp.next(results)
        else:
            break
    return playlists



@app.route('/callback')
def callback():
    token_info = sp_oauth.get_access_token(request.args['code'])
    session['token_info'] = token_info
    sp = spotipy.Spotify(auth=token_info['access_token'])
    user_id = sp.me()['id']

    # Create playlists for initial languages if they don't exist
    get_playlists(sp)
    saved_tracks = sp.current_user_saved_tracks(limit=50)
    while saved_tracks:
        for item in saved_tracks['items']:
            songs_to_sort.append(item['track'])
        if saved_tracks['next']:
            saved_tracks = sp.next(saved_tracks)
        else:
            break


    # for lang in initial_languages:
    #     matching = next((p for p in playlists if p['name'] == f"{lang}"), None)
    #     if matching:
    #         playlist_ids[lang] = matching['id']
    #         songs_to_subtract = sp.playlist_tracks(matching['id'])
    #         playlists[lang] = songs_to_subtract['items']
    #         for song in songs_to_subtract['items']:
    #             track_ids_to_remove = {item['track']['id'] for item in songs_to_subtract['items']}
    #             songs_to_sort[:] = [song for song in songs_to_sort if song['id'] not in track_ids_to_remove]

    #     else:
    #         new_playlist = sp.user_playlist_create(user=user_id, name=f"{lang}", public=False)
    #         # playlist_ids[lang] = new_playlist['id']
    #         playlists[lang] = new_playlist['id']

    for lang in playlists.keys():
        songs_to_subtract = sp.playlist_tracks(playlists[lang])
        track_ids_to_remove = {item['track']['id'] for item in songs_to_subtract['items']}
        songs_to_sort[:] = [song for song in songs_to_sort if song['id'] not in track_ids_to_remove]

    random.shuffle(songs_to_sort)
    return redirect(url_for('sort'))

@app.route('/sort', methods=['GET', 'POST', 'SKIP'])
def sort():
    token_info = session.get('token_info', None)
    if not token_info:
        return redirect(url_for('login'))

    sp = spotipy.Spotify(auth=token_info['access_token'])

    if request.method == 'POST':
        lang = request.form.get('language')
        song = songs_to_sort.pop(0)  # Get and remove the first song from the list

        if lang != '__SKIP__':
            # Add the song to the corresponding Spotify playlist
            sp.playlist_add_items(playlist_id=playlists[lang], items=[song['id']])

        # If there are no more songs to sort, redirect to the done page
        if not songs_to_sort:
            return redirect(url_for('done'))

    if songs_to_sort:
        current_song = songs_to_sort[0]
        return render_template('index.html', song=current_song, languages=list(playlists.keys()))
    else:
        return redirect(url_for('done'))

@app.route('/done')
def done():
    return render_template('done.html', playlists=playlists)

@app.route('/add_language', methods=['POST'])
def add_language():
    new_lang = request.form.get('new_language')
    token_info = session.get('token_info', None)
    if not token_info:
        return redirect(url_for('login'))

    sp = spotipy.Spotify(auth=token_info['access_token'])
    user_id = sp.me()['id']

    # Avoid duplicates
    if new_lang not in playlists.keys():
        new_playlist = sp.user_playlist_create(user=user_id, name=f"{new_lang} ", public=False)
        playlists[new_lang] = new_playlist['id']

    return redirect(url_for('sort'))


if __name__ == '__main__':
    app.run(debug=True)
