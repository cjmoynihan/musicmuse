"""
A file for managing any last_fm calls
"""
# imports
import requests

# constants
api_key = "a7dd7b2ec7530f54b6873584c8b87621"
similar_web_address = "http://ws.audioscrobbler.com/2.0/?method=track.getsimilar&artist={artist}&track={title}&autocorrect=1&api_key={api}format=json"
limit_similar_web_address = "http://ws.audioscrobbler.com/2.0/?method=track.getsimilar&artist={artist}&track={title}&autocorrect=1&limit={limit}&api_key={api}format=json"
popular_user_agent = "'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/35.0.1916.47 Safari/537.36'"
request_headers = {
    'User-Agent': popular_user_agent
}
request_endpoint = "http://ws.audioscrobbler.com/2.0/"

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

def track_similars(title, artist, limit=None):
    """
    Queries the lastfm database to get the similar music data for a given title and artist
    If limit is provided, it will get no more than limit results
    """
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
    resp = requests.get(url=request_endpoint, headers=request_headers, data=data)
    j = resp.json()
    return j

def _get_popular():
    # Gets the popular music
    data = {
        "method": "chart.gettoptracks",
        "api_key": api_key,
        "format": "json"
    }
    resp = requests.get(url=request_endpoint, headers=request_headers, data=data)
    j = resp.json()
    return j

def get_popular():
    j = _get_popular()
    print(j)
    return list(map(read_sim_track_json, j["tracks"]["track"]))

def read_sim_track_json(track_dict):
    print(track_dict)
    other_title = track_dict['name']
    other_artist = track_dict['artist']['name']
    other_sim = track_dict.get('match', 0.5)
    return (other_title, other_artist, other_sim)

def run_tests():
    test_title, test_artist = (
        "Lone Digger",
        "Caravan Palace"
    )
    j = track_similars(test_title, test_artist, 10)
    print(j)

if __name__ == "__main__":
    run_tests()
