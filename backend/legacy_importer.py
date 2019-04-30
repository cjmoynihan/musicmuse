"""
Legacy code for interfacing with old track_pair datasets
"""
# Imports
import sqlite3 as sq3

# Constants
example_tracks = [
    "TRAWOYD128F4215DDD",
    "TRLMKTL128F429D8D5"
]
example_track = example_tracks[0]
dbfile = 'lastfm_similars.db'


# Utility functions
def format_data(data, num_elements=2):
    # Unformats the data from a string
    result = data.split(',')
    is_digits = [True] * num_elements
    for i in range(num_elements):
        try:
            float(result[i])
        except ValueError:
            is_digits[i] = False
    return list(zip(*
        (
        list(map(float, result[i::num_elements])) if is_digits[i] else result[i::num_elements]
        for i in range(num_elements)
        )
    ))


class db:
    def __init__(self):
        self.conn = sq3.connect(dbfile)
        self.c = self.conn.cursor()

    def get_similars(self, track_id):
        # Gets all similar track_ids, and values, of a track_id
        self.c.execute("SELECT target FROM similars_src WHERE tid=?", (track_id,))
        result = self.c.fetchone()
        if not result:
            return list()
        return format_data(result[0])

    def sorted_similars(self, track_id):
        return sorted(self.get_similars(track_id), key=lambda x: x[1], reverse=True)

    def get_reverse_similar(self, track_id):
        # Gets all tracks to which track_id is similar
        self.c.execute("SELECT target FROM similars_dest WHERE tid=?", (track_id,))
        return format_data(self.c.fetchone()[0])

    def get_songs_with_similar(self):
        self.c.execute("SELECT DISTINCT tid FROM similars_dest")
        yield from list(self.c)

    def get_ordered_similar(self, track_id):
        self.c.execute("SELECT target FROM similars_dest WHERE tid=?", (track_id,))
        return sorted(format_data(self.c.fetchone()[0]), key=lambda x: x[1], reverse=True)

class TrackReader:
    def __init__(self):
        self.conn = sq3.connect('track_names.db')
        self.c = self.conn.cursor()

    def get_song(self, track_id):
        self.c.execute("SELECT title, artist FROM track_song WHERE track_id = ?", (track_id,))
        return self.c.fetchall()

    def get_track_ids(self, title=None, artist=None):
        temp_c = self.conn.cursor()
        if title is None and artist is None:
            raise ValueError()
        elif artist is None:
            temp_c.execute("SELECT track_id FROM track_song WHERE title = ?", (title,))
        elif title is None:
            temp_c.execute("SELECT track_id FROM track_song WHERE artist = ?", (artist,))
        else:
            temp_c.execute("SELECT track_id FROM track_song WHERE title = ? AND artist = ?", (title, artist))
        yield from (track_id for (track_id,) in temp_c)

    def get_artists(self, title):
        temp_c = self.conn.cursor()
        yield from (artist for (artist,) in temp_c.execute("SELECT artist FROM track_song WHERE title = ?", (title,)))

