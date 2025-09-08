import os
import random
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from flask import Flask, render_template, redirect, request, session, url_for

load_dotenv('config.env')

# Flask app
app = Flask(__name__)
app.secret_key = os.urandom(24)
app.config['SESSION_COOKIE_NAME'] = 'spotify_session'
app.config['SESSION_TYPE'] = 'filesystem'

# Spotify API
CLIENT_ID = os.getenv('CLIENT_ID')
CLIENT_SECRET = os.getenv('CLIENT_SECRET')
REDIRECT_URI = os.getenv('REDIRECT_URI')
SCOPE = "user-library-read playlist-modify-private playlist-read-private playlist-read-collaborative user-read-private"

sp_oauth = SpotifyOAuth(
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    redirect_uri=REDIRECT_URI,
    scope=SCOPE
)

# Globals
playlists = {}       # {lang: playlist_id}
songs_to_sort = []   # for Language Sorter


# -------------------
# Auth
# -------------------
@app.route('/')
def home():
    token_info = session.get('token_info')
    user_name = None
    if token_info:
        try:
            sp = spotipy.Spotify(auth=token_info['access_token'])
            user_name = sp.me()['display_name']
        except Exception:
            session.pop('token_info', None)
    return render_template("home.html", user_name=user_name)


@app.route('/login')
def login():
    return redirect(sp_oauth.get_authorize_url())


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))


@app.route('/callback')
def callback():
    token_info = sp_oauth.get_access_token(request.args['code'])
    session['token_info'] = token_info
    return redirect(url_for('home'))


def get_spotify():
    token_info = session.get('token_info')
    if not token_info:
        return None
    return spotipy.Spotify(auth=token_info['access_token'])


# -------------------
# Language Sorter
# -------------------
def get_lang_playlists(sp):
    results = sp.current_user_playlists(limit=50)
    while results:
        for item in results['items']:
            if item['name'].endswith(" "):
                playlists[item['name']] = item['id']
        if results['next']:
            results = sp.next(results)
        else:
            break
    return playlists


@app.route('/language_sorter')
def language_sorter():
    sp = get_spotify()
    if not sp:
        return redirect(url_for('login'))

    get_lang_playlists(sp)

    global songs_to_sort
    songs_to_sort.clear()
    saved_tracks = sp.current_user_saved_tracks(limit=50)
    while saved_tracks:
        for item in saved_tracks['items']:
            songs_to_sort.append(item['track'])
        if saved_tracks['next']:
            saved_tracks = sp.next(saved_tracks)
        else:
            break

    for lang in playlists.keys():
        songs_to_subtract = sp.playlist_tracks(playlists[lang])
        track_ids_to_remove = {item['track']['id'] for item in songs_to_subtract['items']}
        songs_to_sort[:] = [song for song in songs_to_sort if song['id'] not in track_ids_to_remove]

    random.shuffle(songs_to_sort)
    return redirect(url_for('sort'))


@app.route('/sort', methods=['GET', 'POST'])
def sort():
    sp = get_spotify()
    if not sp:
        return redirect(url_for('login'))

    if request.method == 'POST':
        lang = request.form.get('language')
        song = songs_to_sort.pop(0)

        if lang != '__SKIP__':
            sp.playlist_add_items(playlist_id=playlists[lang], items=[song['id']])

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
    sp = get_spotify()
    if not sp:
        return redirect(url_for('login'))

    user_id = sp.me()['id']
    if new_lang not in playlists.keys():
        new_playlist = sp.user_playlist_create(user=user_id, name=f"{new_lang} ", public=False)
        playlists[new_lang] = new_playlist['id']
    return redirect(url_for('sort'))


# -------------------
# Random Shuffler
# -------------------
def get_all_liked_songs(sp):
    results = sp.current_user_saved_tracks(limit=50)
    liked_songs = []
    while results:
        for item in results['items']:
            track = item['track']
            liked_songs.append({
                'id': track['id'],
                'name': track['name'],
                'artist': track['artists'][0]['name'],
                'album': track['album']['name'],
                'added_at': item['added_at']
            })
        if results['next']:
            results = sp.next(results)
        else:
            results = None
    return liked_songs


def get_random_playlists(sp):
    playlists = []
    results = sp.current_user_playlists()
    # print(results)
    while results:
        for item in results['items']:
            try:
                if item['name'].index('Random') == 0:
                    playlists.append({
                        'name': item['name'],
                        'id': item['id'],
                        'owner': item['owner']['display_name'],
                        'tracks': item['tracks']['total']
                    })
            except ValueError:
                continue
        if results['next']:
            results = sp.next(results)
        else:
            results = None

    return playlists


def delete_playlist(sp, playlists):
    for playlist in playlists:
        try:
            sp.current_user_unfollow_playlist(playlist['id'])
            print(f"Successfully deleted playlist: {playlist['name']}")
        except Exception as e:
            print(f"An error occurred: {e}")



def create_playlist(sp, user_id, playlist_name, description=''):
    return sp.user_playlist_create(user=user_id, name=playlist_name, public=False, description=description)


def add_songs_to_playlist(sp, playlist_id, tracks):
    track_ids = [track['id'] for track in tracks]
    sp.playlist_add_items(playlist_id, track_ids)


@app.route('/random_shuffler', methods=['GET', 'POST'])
def random_shuffler():
    sp = get_spotify()
    if not sp:
        return redirect(url_for('login'))

    if request.method == 'POST':
        mode = request.form.get('mode')  # "num_playlists" or "songs_per_playlist"
        value = int(request.form.get('value'))
        leftover_action = request.form.get('leftover_action')  # "distribute" or "new_playlist"

        playlists = get_random_playlists(sp)
        delete_playlist(sp, playlists)

        liked_songs = get_all_liked_songs(sp)
        random.shuffle(liked_songs)

        user_id = sp.me()['id']
        playlists_created = []

        if mode == "num_playlists":
            chunk_size = len(liked_songs) // value
            extras = len(liked_songs) % value

            for i in range(value):
                start = i * chunk_size
                end = start + chunk_size
                playlist = create_playlist(sp, user_id, f"Random Mix {i+1}")
                playlists_created.append(playlist)
                add_songs_to_playlist(sp, playlist['id'], liked_songs[start:end])

            leftover_songs = liked_songs[-extras:] if extras else []

        else:  # songs_per_playlist
            chunk_size = value
            leftover_songs = []
            for i in range(0, len(liked_songs), chunk_size):
                chunk = liked_songs[i:i+chunk_size]
                if len(chunk) < chunk_size:
                    leftover_songs = chunk
                    break
                playlist = create_playlist(sp, user_id, f"Random Mix {len(playlists_created)+1}")
                playlists_created.append(playlist)
                add_songs_to_playlist(sp, playlist['id'], chunk)

        # Handle leftovers
        if leftover_songs:
            if leftover_action == "distribute" and playlists_created:
                for track in leftover_songs:
                    target = random.choice(playlists_created)
                    add_songs_to_playlist(sp, target['id'], [track])
            elif leftover_action == "new_playlist":
                playlist = create_playlist(sp, user_id, f"Random Mix {len(playlists_created)+1}")
                playlists_created.append(playlist)
                add_songs_to_playlist(sp, playlist['id'], leftover_songs)

        return render_template("shuffler_done.html")

    return render_template("shuffler.html")


if __name__ == '__main__':
    app.run(debug=True)
