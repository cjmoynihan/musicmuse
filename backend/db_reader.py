"""
Handles the processing for storing and retrieving song data
"""
# Imports
import sqlite3 as sq3
import lastfm_api
import time

# Constants


class converge_db:
    def __init__(self):
        self.db_name = 'converge.db'
        self.db_schema = 'converge.schema'
        self.conn = sq3.connect(self.db_name)
        self.c = self.conn.cursor()
        self.create_tables()
        self.next_simple_id = self.c.execute("SELECT MAX(simple_id) FROM simple_song_id").fetchone()[0]
        if self.next_simple_id is None:
            self.next_simple_id = 0
        self.next_simple_id += 1

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

    def all_song_data(self):
        """
        Get all (title, artist) pairs
        """
        temp_cursor = self.conn.cursor()
        temp_cursor.execute("SELECT title, artist FROM simple_song_id")
        yield from temp_cursor

    def get_simple_from_title_artist(self, title, artist=None):
        """
        Queries the database for a title (and artist)
        """
        if artist is not None:
            self.c.execute("SELECT simple_id FROM simple_song_id WHERE title = ? AND artist = ?", (title, artist))
            result = list(sid for (sid,) in self.c)
        else:
            self.c.execute("SELECT simple_id FROM simple_song_id WHERE title = ?", (title,))
            result = set(sid for (sid,) in self.c)
        if not result:
            return None
        return list(result)

    def get_sorted_similars(self, title, artist, *, fix_and_filter=False):
        """
        Gets all (title, artist, similarity) for a (title, artist) sorted by similarity (highest -> lowest)
        If fix_unsearched is true, fix all of the songs for which there similars haven't yet been looked up
        If filter_sparse is true, only return the (title, artists) which have links to or from the other (title, artists)
        """
        simple_ids = self.get_simple_from_title_artist(title, artist)
        if not simple_ids:
            raise ValueError("There are no songs stored for (title, artist):\n({0}, {1})".format(title, artist))
        simple_ids = list(simple_ids)

        # Might as well do a duplicate check here
        if len(simple_ids) > 1 and artist is not None:
            raise RuntimeWarning("There are multiple simple_ids for (title, artist):\n({0}, {1})".format(title, artist))
        simple_id = simple_ids[0]

        if fix_and_filter:
            # Make sure everything has been added to the database
            self.c.execute("""
            SELECT title, artist, similarity, simple_id_other
            FROM simple_similars
            INNER JOIN simple_song_id
            ON simple_id_other = simple_id
            WHERE simple_id_orig = ?
            AND simple_id_other IS NOT NULL
            ORDER BY similarity DESC
            """, (simple_id,))
            fetched_results = self.c.fetchall()
            similar_data = set((title, artist) for (title, artist, *_) in self.c)
            return [
                (other_title, other_artist, similarity)
                for (other_title, other_artist, similarity, *_) in fetched_results
                if similarity and any((title, artist) in similar_data for (title, artist, *_) in self.add_from_lastfm(other_title, other_artist, commit=True))
            ]

        # simple_id_other -> NULL for cases where there are no similar songs
        # This is to prevent constant lookups for songs that have already been discovered
        self.c.execute("""
        SELECT title, artist, similarity
        FROM simple_similars
        INNER JOIN simple_song_id
        ON simple_id_other = simple_id
        WHERE simple_id_orig = ?
        AND simple_id_other IS NOT NULL
        ORDER BY similarity DESC
        """, (simple_id,))

        return [(other_title, other_artist, similarity) for (other_title, other_artist, similarity) in self.c if similarity]

    def add_from_lastfm(self, title, artist, *, commit=False):
        """
        Grabs the song similarity information from last_fm and uses it to update the database
        Returns the list of similar songs to use (if it doesn't call, it doesn't worry about it either)
        """
        created, sid = self.insert_or_ignore_title_artist(title, artist)
        # Have to let this non-commit go by first
        similars = self.c.execute("""
            SELECT title, artist, similarity
            FROM simple_similars
            LEFT JOIN simple_song_id
            ON simple_id_other = simple_id
            WHERE simple_id_orig = ?
        """, (sid,)).fetchall()
        if similars:
            return similars
        # if self.c.execute("SELECT simple_id_orig FROM simple_similars WHERE simple_id_orig = ?", (sid,)).fetchone():
        #     # print("Already added song {0} by {1}".format(title, artist))
        #     return list()
        print("Adding song {0} by {1}".format(title, artist))
        j = lastfm_api.track_similars(title, artist, last_call=True)
        # fixed_attributes = j['similartracks'].get('@attr', dict())
        # title = fixed_attributes.get(title, title)
        # artist = fixed_attributes.get(artist, artist)
        all_similar_details = j['similartracks'].get('track', list())
        if commit:
            print("Recieved {0} similar songs".format(len(all_similar_details)))
        if len(all_similar_details) == 0:
            self.c.execute("INSERT INTO simple_similars(simple_id_orig) VALUES(?)", (sid,))
        all_similar_details = [lastfm_api.read_sim_track_json(track_dict) for track_dict in all_similar_details]
        for other_title, other_artist, other_sim in all_similar_details:
            # Check to see if song exists
            other_created, other_sid = self.insert_or_ignore_title_artist(other_title, other_artist)
            self.c.execute("INSERT INTO simple_similars(simple_id_orig, simple_id_other, similarity) VALUES(?, ?, ?)", (sid, other_sid, other_sim))
        if commit:
            self.conn.commit()
        return all_similar_details

    def add_all_sim_lastfm(self, title, artist, *, stop_at=50):
        """
        Adds a song and up to 50 of its children to the similarity pool
        """
        for (i, (other_title, other_artist, other_sim)) in enumerate(self.add_from_lastfm(title, artist)):
            # For now, make sure we don't call the service too many times/second
            # Originally showed % complete on each song
            print(f"Adding songs related to {other_title}, {other_artist}")
            if i == stop_at:
                break
            self.add_from_lastfm(other_title, other_artist)
        self.conn.commit()

    def insert_or_ignore_title_artist(self, title, artist):
        title, artist = title.lower(), artist.lower()
        self.c.execute("SELECT simple_id FROM simple_song_id WHERE title = ? AND artist = ?", (title, artist))
        result = self.c.fetchone()
        if result is None:
            new_sid = self.next_simple_id
            self.c.execute("INSERT INTO simple_song_id(simple_id, title, artist) VALUES(?, ?, ?)", (new_sid, title, artist))
            self.next_simple_id += 1
            return True, new_sid
        return False, result[0]

    def find_non_unique(self):
        temp_cur = self.conn.cursor()
        temp_cur.execute("SELECT simple_id_orig, simple_id_other FROM simple_similars GROUP BY simple_id_orig, simple_id_other HAVING COUNT(*) > 1")
        yield from temp_cur

    def fix_non_uniques(self):
        correct_values = list()
        for (simple_id_orig, simple_id_other) in self.find_non_unique():
            self.c.execute("SELECT * FROM simple_similars WHERE simple_id_orig = ? AND simple_id_other = ? ORDER BY rowid DESC", (simple_id_orig, simple_id_other))
            correct_values.append(self.c.fetchone())
            self.c.execute("DELETE FROM simple_similars WHERE simple_id_orig = ? AND simple_id_other = ?", (simple_id_orig, simple_id_orig))
        for (simple_id_orig, simple_id_other, similarity) in correct_values:
            self.c.execute("INSERT INTO simple_similars(simple_id_orig, simple_id_other, similarity) VALUES(?, ?, ?)", (simple_id_orig, simple_id_other, similarity))
        self.conn.commit()

    def fix_and_get_sorted_similars(self, title, artist):
        self.add_all_sim_lastfm(title, artist)
        return self.get_sorted_similars(title, artist)

    def two_hops_sid(self, sid):
        """
        Gets the lower bound for (a->c) given (a->b, b->c)
        Assumes that (a->b)*4 = (b->a) implies that |a| = |b| * 4
        """
        temp_cursor = self.conn.cursor()
        # Want to join (a->b) table, (c->b) table, then (c, title, artist)
        # Then group by (c) and get MAX(a->b sim + c->b sim - 1)
        temp_cursor.execute("""
            SELECT title, artist, MAX(
                (parent_grand.similarity + parent_child.similarity - 1)
                * (grand_parent.similarity)
                / (parent_grand.similarity)
            )
            FROM simple_similars AS parent_grand
            INNER JOIN simple_similars AS parent_child
            ON parent_grand.simple_id_orig = parent_child.simple_id_orig
            INNER JOIN simple_similars AS grand_parent
            ON parent_grand.simple_id_orig = grand_parent.simple_id_other
            AND parent_grand.simple_id_other = grand_parent.simple_id_orig
            INNER JOIN simple_song_id
            ON parent_child.simple_id_other = simple_song_id.simple_id
            WHERE parent_grand.simple_id_other = ?
            AND parent_grand.simple_id_other != parent_child.simple_id_other
            GROUP BY parent_child.simple_id_other
        """, (sid,))
        yield from ((title, artist, similarity) for (title, artist, similarity) in temp_cursor)

    # def get_two_hops(self, sid):
    #     """
    #     Get's all two-hops, which is to say given (a->b similarity, and b->c similarity) implies a->c similarity
    #     Assumes the lower-bound probability for a->c, which is (Pr(a->b) + Pr(b->c) - 1)
    #         The upper-bound is min(Pr(a->b), Pr(b->c)), and if they're independent, it is exactly Pr(a->b) * Pr(b->c)
    #         Note that these are all the same if Pr(a->b) = 1, or Pr(b->c) = 1
    #     """
    #     # Collect all the grandchildren
    #     temp_cursor = self.conn.cursor()
    #     temp_cursor.execute("""
    #         SELECT title, artist, MAX(grand_parent.similarity + parent_child.similarity - 1)
    #         FROM simple_similars AS grand_parent
    #         INNER JOIN simple_similars AS parent_child
    #         ON grand_parent.simple_id_other = parent_child.simple_id_orig
    #         INNER JOIN simple_song_id
    #         ON parent_child.simple_id_other = simple_song_id.simple_id
    #         WHERE grand_parent.simple_id_orig = ?
    #         AND grand_parent.simple_id_orig != parent_child.simple_id_other
    #         GROUP BY parent_child.simple_id_other
    #     """, (sid,))
    #     yield from ((title, artist, sim) for (title, artist, sim) in temp_cursor if sim > 0)
    #
    # def get_three_hops(self, sid):
    #     # Collect all the great-grandchildren
    #     temp_cursor = self.conn.cursor()
    #     temp_cursor.execute("""
    #         SELECT title, artist, MAX(great_grand_parent.similarity + grand_parent.similarity + parent_child.similarity - 2)
    #         FROM simple_similars AS great_grand_parent
    #         INNER JOIN simple_similars AS grand_parent
    #         ON great_grand_parent.simple_id_other = grand_parent.simple_id_orig
    #         INNER JOIN simple_similars AS parent_child
    #         ON grand_parent.simple_id_other = parent_child.simple_id_orig
    #         INNER JOIN simple_song_id
    #         ON parent_child.simple_id_other = simple_song_id.simple_id
    #         WHERE great_grand_parent.simple_id_orig = ?
    #         AND great_grand_parent.simple_id_orig != grand_parent.simple_id_other
    #         AND great_grand_parent.simple_id_orig != parent_child.simple_id_other
    #         AND grand_parent.simple_id_orig != parent_child.simple_id_other
    #         GROUP BY parent_child.simple_id_other
    #     """, (sid,))
    #     yield from ((title, artist, sim) for (title, artist, sim) in temp_cursor if sim > 0)


def _add_popular(C):
    for (title, artist, match) in lastfm_api.get_popular():
        time.sleep(1)
        C.add_all_sim_lastfm(title, artist)



if __name__ == '__main__':
    C = converge_db()
    sid = C.get_simple_from_title_artist("Africa", "Toto")
    sid = sid[0]
    one_hops = list(C.get_sorted_similars("Africa", "Toto"))
    two_hops = list(C.two_hops_sid(sid))
    print(two_hops)

# ----------------------
# Confirming double hop original
# ----------------------
#     two_hops = list(C.get_two_hops(sid))
#     three_hops = list(C.get_three_hops(sid))
#     # print(one_hops)
#     # print(two_hops)
#     # print(sorted(two_hops, key=lambda x: 1-x[2]))
#     fixed_two_hops = [
#         (title, artist, sim)
#         for (title, artist, sim)
#         in two_hops
#         if (title.lower(), artist.lower()) not in
#         set(
#             (orig_title.lower(), orig_artist.lower())
#             for (orig_title, orig_artist, orig_sim)
#             in one_hops
#         )
#     ]
#     fixed_three_hops = [
#         (title, artist, sim)
#         for (title, artist, sim)
#         in three_hops
#         if (title.lower(), artist.lower()) not in
#         set(
#             (orig_title.lower(), orig_artist.lower())
#             for (orig_title, orig_artist, orig_sim)
#             in one_hops
#         ).union(
#             set(
#                 (two_title.lower(), two_artist.lower())
#                 for (two_title, two_artist, two_sim)
#                 in fixed_two_hops
#             )
#         )
#     ]
#     one_hops.sort(key=lambda x: 1-x[2])
#     fixed_two_hops.sort(key=lambda x: 1-x[2])
#     fixed_three_hops.sort(key=lambda x: 1-x[2])
#     print("Orig number: {0}".format(len(one_hops)))
#     print("Potential two additions: {0}".format(len(fixed_two_hops)))
#     print("Potential three additions: {0}".format(len(fixed_three_hops)))
#     from collections import deque
#     deques = [deque(hops) for hops in (one_hops, fixed_two_hops, fixed_three_hops)]
#     # d_one, d_two, d_three = map(deque, (one_hops, fixed_two_hops, fixed_three_hops))
#     best_list = list()
#     for i in range(100):
#         best_list.append(max(deques, key=lambda x: x[0][-1]).popleft())
#
#     num_two = len(fixed_two_hops) - len(deques[1])
#     num_three = len(fixed_three_hops) - len(deques[2])
#     num_one = len(one_hops) - num_two - num_three
#     print("Original", len(one_hops))
#     print("Remaining", num_one)
#     print("From two", num_two)
#     print("From three", num_three)
#     print()
#     print("Songs from two:")
#     for i in range(num_two):
#         print(fixed_two_hops[i])
#     print()
#     print("Songs from three:")
#     for i in range(num_three):
#         print(fixed_three_hops[i])

