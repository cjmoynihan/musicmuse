"""
A file for managing any last_fm calls
"""
import json.decoder

# imports
import requests
import time
from threading import Thread, Event
from collections import deque
import urllib.parse

# constants
api_key = "a7dd7b2ec7530f54b6873584c8b87621"
similar_web_address = "http://ws.audioscrobbler.com/2.0/?method=track.getsimilar&artist={artist}&track={title}&autocorrect=1&api_key={api}format=json"
limit_similar_web_address = "http://ws.audioscrobbler.com/2.0/?method=track.getsimilar&artist={artist}&track={title}&autocorrect=1&limit={limit}&api_key={api}format=json"
popular_user_agent = "'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/35.0.1916.47 Safari/537.36'"
request_headers = {
    'User-Agent': popular_user_agent
}
request_endpoint = "http://ws.audioscrobbler.com/2.0/"
# wait_time = 1  # Seconds between request calls
api_call_min_wait = 2

"""
Similar json format:
similartracks: {
    track: [
        0: {
            match: "similarity" as float (between 1 and 0),
            name: "song name",
            artist: {
                name: "artist name",
                mbid: "mbid"
            },
            playcount: "number of plays" as int,
            mbid: "mbid"
        },
        1: {...}
        ... sorted by match desc
    ],
    @attr: {
        artist: "fixed artist name if any",
        title: "fixed artist name if any"
    }
}
"""

# Threading class
class DelayedApiCalls(Thread):
    def __init__(self, callback_func):
        Thread.__init__(self)
        self.song_deque = deque()
        self.stopped = Event()
        self.last_call = None

    def add_songs(self, song_data):
        for (title, artist) in song_data:
            self.song_deque.append((title, artist))
        if not self.isAlive:
            self.run()

    def run(self):
        while self.song_deque:
            title, artist = self.song_deque.popleft()
            while (self.last_call is None) or (not self.stopped.wait(time.time() - self.last_call)):
                self.last_call = time.time()

previous_calls = [None]
def track_similars(title, artist, *args, limit=None, last_call=False, max_calls=5):
    """
    Queries the lastfm database to get the similar music data for a given title and artist
    If limit is provided, it will get no more than limit results
    """
    title, artist = title.lower(), artist.lower()
    data = {
        "method": "track.getsimilar",
        "artist": artist,
        "track": title,
        "autocorrect": "1",
        "api_key": api_key,
        "format": "json"
    }
    if limit:
        data["limit"] = limit
    if last_call and previous_calls[0]:
        time.sleep(api_call_min_wait)
    else:
        wait_time = api_call_min_wait - (time.time() - (previous_calls[0] or time.time()))
        if wait_time > 0:
            time.sleep(wait_time)
    resp = requests.get(url=request_endpoint, headers=request_headers, params=data)
    previous_calls[0] = time.time()
    try:
        j = resp.json()
    except json.decoder.JSONDecodeError:
        if max_calls:
            return track_similars(title, artist, *args, limit, last_call, max_calls-1)
        else:
            raise
    return j

def _get_popular():
    # Gets the popular music
    data = {
        "method": "chart.gettoptracks",
        "api_key": api_key,
        "format": "json"
    }
    time.sleep(1)
    resp = requests.get(url=request_endpoint, headers=request_headers, params=data)
    j = resp.json()
    return j

def get_top_songs(artist):
    data = {
        "method": "artist.getTopTracks",
        "api_key": api_key,
        "format": "json",
        "artist": artist
    }
    time.sleep(1)
    # Originally call wasn't working because I was using data as an endpoint instead data
    resp = requests.get(url=request_endpoint, headers=request_headers, params=data)
    # Simple work around:
    # request_and_data = request_endpoint + '?' + urllib.parse.urlencode(data)
    # resp = requests.get(url=request_and_data, headers=request_headers)
    j = resp.json()
    yield from map(read_sim_track_json, j["toptracks"]["track"])

def get_popular():
    j = _get_popular()
    return list(map(read_sim_track_json, j["tracks"]["track"]))

def read_sim_track_json(track_dict):
    other_title = track_dict['name']
    other_artist = track_dict['artist']['name']
    other_sim = track_dict.get('match', 0)
    return (other_title.lower(), other_artist.lower(), other_sim)

def run_tests():
    test_title, test_artist = (
        "Don't stop believin'",
        "Journey"
    )
    j = track_similars(test_title, test_artist)
    print(j)

if __name__ == "__main__":
    run_tests()
