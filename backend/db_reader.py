"""
Home base for managing the databases of song data
"""
import sqlite3 as sq3

dbfile = 'lastfm_similars.db'

example_tracks = [
    "TRAWOYD128F4215DDD",
    "TRLMKTL128F429D8D5"
]
example_track = example_tracks[0]

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

class converge_db:
    def __init__(self):
        self.db_name = 'converge.db'
        self.db_schema = 'converge.schema'
        self.conn = sq3.connect(self.db_name)
        self.c = self.conn.cursor()
        self.create_tables()

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
        # sorted
        # temp_cursor.execute("SELECT title, artist FROM simple_song_id ORDER BY artist, title")
        # return list(temp_cursor.fetchall())
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
        list((tid for (tid,) in temp_cursor))

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
        ORDER BY similarity DESC
        """, (orig_sid,))
        # return self.c.fetchall()
        # Just get good values
        return [(t, a, sim) for (t, a, sim) in self.c if sim]

    # def check_all(self):
    #     orig_sim_db = db()
    #     # all_tids =

if __name__ == '__main__':
    C = converge_db()

    # print(sum(1 for _ in C.c.execute("SELECT track_id FROM simple_track_id")))
    # 839122 lines
    # ~ 766100 simple_ids
    # ~ 75000 dups

    # C.merge_similars()
    # exit()
    # sid = C.get_simple_id("Born To Be Wild")[0]
    # print(sid)
    # C.c.execute("SELECT * FROM simple_similars")
    # for item in C.c:
    #     print(item)
    # Get the similarities for this, by title
    # C.c.execute("SELECT title, artist, similarity FROM simple_similars INNER JOIN simple_song_id ON simple_id_other = simple_id WHERE simple_id_orig = ?", (sid,))
    # print("\n".join("Similarity {0} on {1} by {2}".format(round(similarity, 4)*100, title, artist) for (title, artist, similarity) in C.c))

    # all_songs = list(C.all_song_data())
    # print(len(all_songs))
    # print(len(set(all_songs)))

    # Want to see if simple_song_id is a unique identifier

    # C.validate_pairs()
    # exit()

    # Dup analysis
    # TR = TrackReader()
    # pop_song = TR.get_song('TRAWOYD128F4215DDD')[0]
    # print(pop_song)
    # track_ids = list(TR.get_track_ids(*pop_song))
    # # print(list(track_ids))
    # print('\n'.join(track_ids))
    # # Do some cross anaylsis to see what the duplicates are
    # print("Now checking all dups")
    # D = db()
    # all_similars = list()
    # best_match = set()
    # # First organize each track_ids similars into the same batch
    # for track_id in track_ids:
    #     print(track_id, TR.get_song(track_id)[0])
    #     similars = D.get_similars(track_id)
    #     if len(set(similars)) > len(best_match):
    #         best_match = similars
    #     all_similars.extend(similars)
    # # Determine if there is any clashing across the various (id, rating) pairs
    # tid_values = dict()
    # for (tid, value) in all_similars:
    #     tid_values[tid] = tid_values.get(tid, list())
    #     tid_values[tid].append(value)
    # good_count = 0
    # for (tid, values) in tid_values.items():
    #     if not len(set(values)) == 1:
    #         print(tid, values)
    #     else:
    #         good_count+=1
    # # The number of clashed pairs
    # print("Good: {0}, bad: {1}".format(good_count, len(tid_values) - good_count))
    #
    # # Check to see if the biggest is the superset of the other sets
    # best_match = set(best_match)
    # not_in_best = set(all_similars).difference(best_match)
    # print(len(not_in_best), not_in_best)


    # D.c.execute("SELECT target FROM similars_src WHERE tid=?", (example_track,))
    # print(D.c.fetchone()[0])
    # print(D.get_similars(example_track,))
    # D.c.execute("SELECT COUNT(target) FROM similars_src")
    # print(D.c.fetchone())