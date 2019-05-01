"""
Home base for managing the databases of song data
"""
# Imports
import sqlite3 as sq3
import lastfm_api
import time

# Constants
non_uniques = [
]


class converge_db:
    def __init__(self):
        self.db_name = 'converge.db'
        self.db_schema = 'converge.schema'
        self.conn = sq3.connect(self.db_name)
        self.c = self.conn.cursor()
        self.create_tables()
        self.next_simple_id = self.c.execute("SELECT MAX(simple_id) FROM simple_song_id").fetchone()[0]
        if self.next_simple_id is None:
            self.next_simple_id = 1
        else:
            self.next_simple_id = self.next_simple_id + 1

    def read_schema(self):
        with open(self.db_schema) as f:
            lines = '\n'.join(f).split(';')
            lines = (line.strip() for line in lines)
            lines = (line for line in lines if line and not line.startswith('//'))
            return lines

    def create_tables(self):
        for cmd in self.read_schema():
            self.c.execute(cmd)
        self.conn.commit()

    def _validate_pairs(self):
        from legacy_importer import TrackReader
        TR = TrackReader()
        all_songs = list(set(TR.c.execute("SELECT title, artist FROM track_song")))
        # print(len(all_songs))
        # data_to_add = list()
        for (i, (title, artist)) in enumerate(all_songs):
            if i % 7611 == 0:
                print("{0} / 100".format(i / 7611))
            track_ids = TR.c.execute("SELECT track_id FROM track_song WHERE title = ? AND artist = ?", (title, artist))
            self.c.execute("INSERT INTO simple_song_id(simple_id, title, artist) VALUES(?, ?, ?)", (i, title, artist))
            for (tid,) in track_ids:
                self.c.execute("INSERT INTO simple_track_id(track_id, simple_id) VALUES(?, ?)", (tid, i))
        self.conn.commit()

    def all_song_data(self):
        temp_cursor = self.conn.cursor()
        temp_cursor.execute("SELECT title, artist FROM simple_song_id")
        yield from temp_cursor

    def get_track_ids(self, title, artist):
        temp_cursor = self.conn.cursor()
        temp_cursor.execute(
            """
            SELECT track_id
            FROM simple_song_id AS A
            INNER JOIN
            simple_track_id AS B
            ON A.simple_id = B.simple_id
            WHERE title = ? AND artist = ?
            """, (title, artist)
        )
        list(tid for (tid,) in temp_cursor)

    def get_simple_from_title_artist(self, title, artist=None):
        if artist is not None:
            self.c.execute("SELECT simple_id FROM simple_song_id WHERE title = ? AND artist = ?", (title, artist))
            result = list(sid for (sid,) in self.c)
        else:
            self.c.execute("SELECT simple_id FROM simple_song_id WHERE title = ?", (title,))
            result = set(sid for (sid,) in self.c)
        if not result:
            return None
        return list(result)

    def get_simple_from_track(self, tid):
        self.c.execute("SELECT simple_id FROM simple_track_id WHERE track_id = ?", (tid,))
        result = self.c.fetchone()
        if result is None:
            return result
        return result[0]

    def _merge_similars(self):
        # Create a similarity table for the simple_ids
        self.c.execute("DROP TABLE IF EXISTS simple_similars")
        self.c.execute("""
            CREATE TABLE simple_similars(
                simple_id_orig INT NOT NULL,
                simple_id_other INT NOT NULL,
                similarity REAL NOT NULL
            )
        """)
        temp_cursor = self.conn.cursor()
        from legacy_importer import db
        similarity_database = db()
        last_simple_id = None
        cur_tids = list()
        # First get the highest simple_id value
        for (track_id, simple_id) in temp_cursor.execute("SELECT track_id, simple_id FROM simple_track_id ORDER BY simple_id"):
            # Get the tids for each simple_id
            # Guaranteed to not have any duplicates (each simple id is partition of track_ids)
            if simple_id != last_simple_id:
                # Get all of the similars, but fix the duplicate track_ids
                similar_ratings = dict()
                for self_tid in cur_tids:
                    for (similar_tid, rating) in similarity_database.get_similars(self_tid):
                        similar_simple_id = self.get_simple_from_track(similar_tid)
                        if (similar_simple_id is not None):
                            if similar_simple_id not in similar_ratings.keys():
                                # Let's not worry about mismatches. Assume they're all the same
                                # if similar_ratings[similar_simple_id] != rating:
                                #     print("A mismatch!!")
                                #     print("Orig song {1}")
                                similar_ratings[similar_simple_id] = rating
                # Add all of these to the simple database, then clear the saved material
                for (other_simple_id, other_rating) in similar_ratings.items():
                    self.c.execute("INSERT INTO simple_similars(simple_id_orig, simple_id_other, similarity) VALUES(?, ?, ?)", (last_simple_id, other_simple_id, other_rating))
                last_simple_id = simple_id
                cur_tids = list()
                if last_simple_id % 7661 == 0:
                    print("{0}/100 complete".format(last_simple_id / 7661))
            cur_tids.append(track_id)
        self.conn.commit()

    def get_sorted_similars(self, title, artist):
        """
        Gets all the title, artist, similarity for a title sorted by similarity
        """
        orig_sid = self.get_simple_from_title_artist(title, artist)
        if not orig_sid:
            raise ValueError()
        orig_sid = list(orig_sid)
        if len(orig_sid) > 1 and artist is not None:
            raise ValueError("Multiple simple ids for title {0}, artist {1}, with sids {2}".format(title, artist, orig_sid))
        orig_sid = orig_sid[0]
        self.c.execute("""
        SELECT title, artist, similarity
        FROM simple_similars
        INNER JOIN simple_song_id
        ON simple_id_other = simple_id
        WHERE simple_id_orig = ?
        AND simple_id_other IS NOT NULL
        ORDER BY similarity DESC
        """, (orig_sid,))
        # return self.c.fetchall()
        # Just get good values
        return [(t, a, sim) for (t, a, sim) in self.c if sim]

    def add_from_lastfm(self, title, artist, *, commit=False):
        """
        Grabs the song similarity information from last_fm and uses it to update the database
        Returns the list of similar songs to use (if it doesn't call, it doesn't worry about it either)
        """
        created, sid = self.insert_or_ignore_title_artist(title, artist)
        # Have to let this non-commit go by first
        if self.c.execute("SELECT simple_id_orig FROM simple_similars WHERE simple_id_orig = ?", (sid,)).fetchone():
            print("Already added song {0} by {1}".format(title, artist))
            return list()
        # if commit:
        print("Adding song {0} by {1}".format(title, artist))
        j = lastfm_api.track_similars(title, artist)
        # fixed_attributes = j['similartracks'].get('@attr', dict())
        # title = fixed_attributes.get(title, title)
        # artist = fixed_attributes.get(artist, artist)
        all_similar_details = j['similartracks'].get('track', list())
        if commit:
            print("Recieved {0} similar songs".format(len(all_similar_details)))
        if len(all_similar_details) == 0:
            self.c.execute("INSERT INTO simple_similars(simple_id_orig) VALUES(?)", (sid,))
        for track_dict in all_similar_details:
            other_title, other_artist, other_sim = lastfm_api.read_sim_track_json(track_dict)
            # Check to see if song exists
            other_created, other_sid = self.insert_or_ignore_title_artist(other_title, other_artist)
            self.c.execute("INSERT INTO simple_similars(simple_id_orig, simple_id_other, similarity) VALUES(?, ?, ?)", (sid, other_sid, other_sim))
        if commit:
            self.conn.commit()
        return all_similar_details

    def add_all_sim_lastfm(self, title, artist):
        for (i, (other_title, other_artist, other_sim)) in enumerate(map(lastfm_api.read_sim_track_json, self.add_from_lastfm(title, artist))):
            # For now, make sure we don't call the service too many times/second
            if i % 5 == 0:
                print("{0}% complete ".format(i*2))
            self.add_from_lastfm(other_title, other_artist)
        self.conn.commit()

    def insert_or_ignore_title_artist(self, title, artist):
        self.c.execute("SELECT simple_id FROM simple_song_id WHERE title = ? AND artist = ?", (title, artist))
        result = self.c.fetchone()
        if result is None:
            new_sid = self.next_simple_id
            self.c.execute("INSERT INTO simple_song_id(simple_id, title, artist) VALUES(?, ?, ?)", (new_sid, title, artist))
            self.next_simple_id += 1
            return (True, new_sid)
        return (False, result[0])

    def find_non_unique(self):
        temp_cur = self.conn.cursor()
        temp_cur.execute("SELECT simple_id_orig, simple_id_other FROM simple_similars GROUP BY simple_id_orig, simple_id_other HAVING COUNT(*) > 1")
        for (id1, id2) in temp_cur:
            print(id1, id2)

    def fix_non_uniques(self):
        correct_values = list()
        for (simple_id_orig, simple_id_other) in non_uniques:
            self.c.execute("SELECT * FROM simple_similars WHERE simple_id_orig = ? AND simple_id_other = ? ORDER BY rowid DESC", (simple_id_orig, simple_id_other))
            correct_values.append(self.c.fetchone())
            self.c.execute("DELETE FROM simple_similars WHERE simple_id_orig = ? AND simple_id_other = ?", (simple_id_orig, simple_id_orig))
        for (simple_id_orig, simple_id_other, similarity) in correct_values:
            self.c.execute("INSERT INTO simple_similars(simple_id_orig, simple_id_other, similarity) VALUES(?, ?, ?)", (simple_id_orig, simple_id_other, similarity))
        self.conn.commit()

    def fix_and_get_sorted_similars(self, title, artist):
        self.add_all_sim_lastfm(title, artist)
        return self.get_sorted_similars(title, artist)


def _add_popular(C):
    for (title, artist, match) in lastfm_api.get_popular():
        time.sleep(1)
        C.add_all_sim_lastfm(title, artist)



if __name__ == '__main__':
    C = converge_db()
    _add_popular(C)
    # C.fix_non_uniques()
