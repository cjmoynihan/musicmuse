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
        print(title)
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
            lines = filter(None, lines)
            return lines

    def create_tables(self):
        for cmd in self.read_schema():
            self.c.execute(cmd)
        self.conn.commit()

    def validate_pairs(self):
        TR = TrackReader()
        all_songs = list(set(TR.c.execute("SELECT title, artist FROM track_song")))
        # data_to_add = list()
        for (i, (title, artist)) in enumerate(all_songs):
            if i==5:
                exit()
            track_ids = TR.c.execute("SELECT track_id FROM track_song WHERE title = ? AND artist = ?", (title, artist))
            self.c.execute("INSERT INTO simple_song_id(simple_id, title, artist) VALUES(?, ?, ?)", (i, title, artist))
            for (tid,) in track_ids:
                self.c.execute("INSERT INTO simple_track_id(track_id, simple_id) VALUES(?, ?)", (tid, i))
        self.conn.commit()



if __name__ == '__main__':
    C = converge_db()
    C.validate_pairs()
    exit()

    TR = TrackReader()
    pop_song = TR.get_song('TRAWOYD128F4215DDD')[0]
    print(pop_song)
    track_ids = list(TR.get_track_ids(*pop_song))
    # print(list(track_ids))
    print('\n'.join(track_ids))
    # Do some cross anaylsis to see what the duplicates are
    print("Now checking all dups")
    D = db()
    all_similars = list()
    best_match = set()
    # First organize each track_ids similars into the same batch
    for track_id in track_ids:
        print(track_id, TR.get_song(track_id)[0])
        similars = D.get_similars(track_id)
        if len(set(similars)) > len(best_match):
            best_match = similars
        all_similars.extend(similars)
    # Determine if there is any clashing across the various (id, rating) pairs
    tid_values = dict()
    for (tid, value) in all_similars:
        tid_values[tid] = tid_values.get(tid, list())
        tid_values[tid].append(value)
    good_count = 0
    for (tid, values) in tid_values.items():
        if not len(set(values)) == 1:
            print(tid, values)
        else:
            good_count+=1
    # The number of clashed pairs
    print("Good: {0}, bad: {1}".format(good_count, len(tid_values) - good_count))

    # Check to see if the biggest is the superset of the other sets
    best_match = set(best_match)
    not_in_best = set(all_similars).difference(best_match)
    print(len(not_in_best), not_in_best)


    # D.c.execute("SELECT target FROM similars_src WHERE tid=?", (example_track,))
    # print(D.c.fetchone()[0])
    # print(D.get_similars(example_track,))
    # D.c.execute("SELECT COUNT(target) FROM similars_src")
    # print(D.c.fetchone())