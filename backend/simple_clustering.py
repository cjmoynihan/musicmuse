#!/Users/cj/anaconda3/bin/python
"""
A file for managing all the clustering aspects
----------------
Other features to add:
* Use two-hops functions
* Use approximation rule if not enough similars:
    * Grab songs similar to similars
    * Grab other songs of the same artist
* Have to figure out how to deal with reverse similarity:
    * If 90% of fringe song like popular song, but 5% of popular song like fringe song,
        * then num_pop * .05 = num_fringe*.9 -> num_fringe = 1/18 * num_pop, num_pop = 18*num_fringe
    * Could extrapolate relative size to original and normalize all similarities to number of people that like both
        * Given that a->b describes the likelihood of b given a
        * Given o is the original song, and a and b are two similar songs
        * Find k for |a| * k = |b|
        * if a->b:
            * |a| * (a->b) / (b->a) = |b|
        * else:
            * |a| * (a->o) / (o->a) * (o->b) / (b->o) = |b|
* Create spotify playlist
    * Play all the songs in a cluster without needing to click each
    * Add them to the user
* Automatically determine the number of clusters. Maybe use elbow or eigengap methods?
    * Deterine the 'rating' of a cluster
"""

# Imports
import db_reader
import lastfm_api
import numpy as np
from sklearn.cluster import SpectralClustering
import json
import math
from itertools import islice, permutations, chain
import os
import sys

# Constants
converge_db = db_reader.converge_db()
color_similarity_threshold = 0.9
# The angles of the clusters are rotated to give the legend the largest possible gap
legend_position = 7/4 * math.pi
# Depending on how the cosine similarity is calculated, could map similarity to range (0, 1) or (0.5, 1)
no_data_similarity = 0
# no_data_similarity = 0.5


def get_similarity_matrix_by_title_artist(title, artist, *, sim_limit=50):
    # print("Gathering similar songs")
    all_data = converge_db.get_sorted_similars(title, artist)
    # print("Found {0} similar songs".format(len(all_data)))
    if len(all_data) < 5:
        print("Not enough, aborting")
        raise ValueError()
    if sim_limit and len(all_data) > sim_limit:
        print("Reducing size to {0}".format(sim_limit))
        all_data = all_data[:sim_limit]
    all_data = (((title, artist), rating) for (title, artist, rating) in all_data)
    similars, ratings = zip(*all_data)
    similar_indexes = dict((value, i) for (i, value) in enumerate(similars))

    # print("Creating the similarity matrix")
    # Create the default values
    similarity_matrix = [
        [0 if i == j else no_data_similarity for j in range(len(similars))]
        for i in range(len(similars))
    ]
    for (i, (sim_title, sim_artist)) in enumerate(similars):
        # print("On song {0}/{1}".format(i+1, len(similars)))
        for (other_title, other_artist, other_similarity) in filter(lambda tas: tuple(tas[:2]) in similar_indexes.keys(), converge_db.get_sorted_similars(sim_title, sim_artist)):
            similarity_matrix[i][similar_indexes[(other_title, other_artist)]] = 1 - other_similarity
    # print("Finished creating similarity matrix")
    # print("Similarity matrix size: {0} by {1}".format(len(similarity_matrix), len(similarity_matrix[0])))
    return np.matrix(similarity_matrix), similars, ratings


def n_clustering(sim_matrix, similar_song_data, similar_ratings, *, num_clusters=None, top_size=20):
    """
    sim_matrix is a matrix of similarities between the songs
    similar_song_data is an iterator of (title, artist) values
    similar_ratings is an iterator of similarity ratings
    """
    if num_clusters is None:
        num_clusters = 5
        # num_clusters = predict_k(sim_matrix)
        # print("CHOSE {0} CLUSTERS".format(num_clusters))

    # Determine which cluster to place things in
    clustering_results = SpectralClustering(num_clusters).fit_predict(sim_matrix)

    # Place songs into their respective clusters
    clusters = [list() for _ in range(num_clusters)]
    for (i, ((title, artist), cluster_num)) in enumerate(zip(similar_song_data, clustering_results), 1):
        clusters[cluster_num].append((title, artist))
    # print("Finished clustering")

    rating_by_song_data = {song_data: rating for (song_data, rating) in zip(similar_song_data, similar_ratings)}

    # Clusters should already be sorted by similarity to original
    # Truncate large cluster size
    clusters = [cluster[:top_size] for cluster in clusters]
    # Get the average distance from the song to the center
    center_distance = [sum((1 - rating_by_song_data[song_data]) for song_data in cluster)/len(cluster) for cluster in clusters]
    clusters, center_distance = zip(*sorted(zip(clusters, center_distance), key=lambda x: x[1]))
    # Get the cluster to cluster distance
    # print("Calculating cluster co-similarity")
    cluster_similarity = np.matrix([[(None if i == j else 0.5) for j in range(len(clusters))] for i in range(len(clusters))])
    song_indexes = {song_data: i for (i, song_data) in enumerate(similar_song_data)}
    for cluster1_ndx, cluster1 in enumerate(clusters):
        # for cluster2_ndx, cluster2 in enumerate(clusters[cluster1_ndx+1:], cluster1_ndx+1):
        for cluster2_ndx, cluster2 in enumerate(clusters):
            if cluster1_ndx == cluster2_ndx:
                continue
            # song to song similarity = sim_matrix[song1][song2]
            running_total = 0
            # DEBUG
            for song1 in cluster1:
                song1_ndx = song_indexes[song1]
                for song2 in cluster2:
                    song2_ndx = song_indexes[song2]
                    running_total += sim_matrix[song1_ndx, song2_ndx]
            # END DEBUG
            cluster_sim = running_total
            cluster_sim /= len(cluster1) * len(cluster2)
            # cluster_sim = sum(sim_matrix[song_indexes[song1]][song_indexes[song2]] for song2 in cluster2 for song1 in cluster1) / (len(cluster1) * len(cluster2))
            cluster_similarity[cluster1_ndx, cluster2_ndx] = cluster_sim
            # cluster_similarity[cluster2_ndx][cluster1_ndx] = cluster_sim
    # print("Finished calculating co-similarity")
    # Combine the responses
    return list(zip(clusters, center_distance)), cluster_similarity

def cluster_by_title_artist(title, artist, *, num_clusters=None, top_size=20):
    # Collect the data
    sim_matrix, similars, ratings = get_similarity_matrix_by_title_artist(title, artist)
    if num_clusters is not None:
        return n_clustering(sim_matrix, similars, ratings, num_clusters=num_clusters, top_size=top_size)
    else:
        return n_clustering(sim_matrix, similars, ratings, top_size=top_size)

def get_angles_from_clusters(clusters, center_distances, cosimilarity):
    """
    Assign every cluster an angle based on the clusters
    Similar clusters should be grouped together
    If their similarity is 0.5, they should be evenly spaced
    If their similarity is high, instead push everything away then adjust for their co-similarity
    If their similarity is low, instead super group together
    """
    # Give priority to the ones that are farther away
    # Remember, 0 = far and dissimilar here, 1 = close and similar here
    # print("Assigning angles and colors")
    cluster_ordering = sorted(range(len(center_distances)), key=lambda i: center_distances[i])
    for ndx_1 in cluster_ordering:
        for ndx_2 in cluster_ordering[ndx_1+1:]:
            cosimilarity[ndx_2, ndx_1] = cosimilarity[ndx_1, ndx_2]
    # Something like 0.5 means evenly spaced
    # 0 is very similar, no space between
    # 1 is not very similar, push back


    # Determine the ordering
    # Not sure how to do non-trivial method
    def ordering_pushback(ordering):
        for ndx1, ndx2 in chain(zip(ordering, ordering[1:]), ((ordering[-1], ordering[0]),)):
            yield (cosimilarity[ndx1, ndx2] or 0 + 0.10)

    def score_ordering(ordering):
        return sum(ordering_pushback(ordering))

    best_ordering = list(min(permutations(range(len(clusters))), key=score_ordering))

    # Create angles and colors
    angles = list()
    colors = list()
    angles.append(0)
    prev_color = [0, 0]
    colors.append(prev_color)
    # Pushback is the amount of relative spacing between nodes
    pushbacks = list(ordering_pushback(best_ordering))
    # Use the sum of all relative spacing to determine the allowed spacing
    total_pushback = sum(pushbacks)
    # print("Indv. pushbacks", pushbacks)
    # print("Total pushback", total_pushback)
    # pushbacks = [min(pushback, total_pushback / 15) for pushback in pushbacks]
    # total_pushback = sum(pushbacks)
    for pushback in pushbacks[:-1]:
        # Each node is pushed equal to its relative spacing * (2pi / relative space reserved)
        angles.append(angles[-1] + pushback * 2 * math.pi / total_pushback)
        # Even if nodes are close, only color them if they're similar enough
        if pushback <= (1 - color_similarity_threshold):
            prev_color = [prev_color[0], prev_color[1]+1]
            colors.append(prev_color)
        else:
            prev_color = [prev_color[0]+1, 0]
            colors.append(prev_color)
    # Now have to fix dark colors assigned to big circles
    color_dict = dict()
    for (i, (order, (color, _))) in enumerate(zip(best_ordering, colors)):
        color_dict.setdefault(color, list())
        color_dict[color].append((len(clusters[order]), i))
    # Assign low numbers to smaller, and high numbers to big
    for color in color_dict.keys():
        # Sort by size
        color_dict[color].sort()
        # Fix the original colors list
        for (hue, (_, orig_index)) in enumerate(color_dict[color]):
            colors[orig_index][1] = hue

    # Do some math to rotate all clusters such that the largest gap is placed where the legend is...
    # biggest_gap = (gap_size, position)
    biggest_gap = max((angle2 - angle1, angle1) for (angle1, angle2) in zip(angles, (angles[1:] + [angles[0]])))
    current_gap_position = biggest_gap[1] + (biggest_gap[0] / 2)
    rotation_amount = legend_position - current_gap_position
    angles = [((angle + rotation_amount) % (2 * math.pi)) for angle in angles]
    print("Done assigning angles and colors")
    return best_ordering, angles, colors

def fix_ordering(ordering, items):
    items = list(enumerate(items))
    items.sort(key=lambda i_item: ordering[i_item[0]])
    return [item for (i, item) in items]

basic_json_filepath = ('jsons/', '.json')
title_artist_separator = ' '
def create_json(title, artist, *, num_clusters = None, top_size = 20, fake_out=False):
    if num_clusters is not None:
        clustering, cluster_sims = cluster_by_title_artist(title, artist, num_clusters=num_clusters, top_size=top_size)
    else:
        clustering, cluster_sims = cluster_by_title_artist(title, artist, top_size=top_size)
    clusters, center_distances = zip(*clustering)
    ordering, angles, colors = get_angles_from_clusters(clusters, center_distances, cluster_sims)
    clustering = fix_ordering(ordering, clustering)
    print("Cluster sizes:")
    cluster_sizes = sorted(len(cluster) for (cluster, distance) in clustering)
    print(', '.join(map(str, cluster_sizes)))
    # Create the json representation
    json_obj = list()
    for (i, ((cluster, center_distance), angle, color)) in enumerate(zip(clustering, angles, colors)):
        titles, artists = zip(*cluster)
        cluster_dict = {
            "songs": titles,
            "artists": artists,
            "centerDistance": center_distance,
            "angle": angle,
            "color": color
        }
        json_obj.append(cluster_dict)
    if not fake_out:
        for json_filepath in (basic_json_filepath, ('../front-end/songjson/', '.json')):
            with open("{0}{1}{2}{3}{4}".format(json_filepath[0], title.replace('/', ''), title_artist_separator, artist.replace('/', ''), json_filepath[1]), 'w') as f:
                json.dump(json_obj, f)
        print("Finished json: {0} {1}".format(title, artist))

def test_jsons():
    os.makedirs("jsons")
    all_songs = converge_db.all_song_data()
    num_jsons = 10
    all_songs = (song_data for song_data in all_songs if len(converge_db.get_sorted_similars(*song_data)) >= 10)
    all_songs = islice(all_songs, num_jsons)
    for song_data in all_songs:
        print("Creating {0} by {1}".format(*song_data))
        create_json(*song_data)

def test_clustering():
    pop_song_data = [
        ('Green, Green Grass of Home', 'Porter Wagoner'),
        ("Your Heart's Not in it", 'Janie Fricke'),
        ('Dancing in the Street', 'Martha and The Vandellas'),
        ('I Love You a Thousand Ways', 'Lefty Frizzell'),
        ('Sorrow On the Rocks', 'Porter Wagoner'),
        ('Give Myself a Party', 'Don Gibson'),
        ("Truck Drivin' Son Of A Gun", 'Dave Dudley'),
        ('The Cold Hard Facts of Life', 'Porter Wagoner'),
        ('16th Avenue', 'Lacy J. Dalton'),
    ]
    best_pick = None
    for song_pick in pop_song_data:
    # song_pick = pop_song_data[0]
        clustering, cluster_sims = cluster_by_title_artist(*song_pick)
        print(cluster_sims)
        print(clustering)
        clusters, center_distances = zip(*clustering)
        ordering, angles, colors = get_angles_from_clusters(clusters, center_distances, cluster_sims)
        clustering = fix_ordering(ordering, clustering)
        print(angles)
        print(colors)
        if best_pick is None:
            best_pick = (min(len(c) for (c, d) in clustering), song_pick)
        else:
            result = min(len(c) for (c,d) in clustering)
            if result > best_pick[0]:
                best_pick = (result, song_pick)
    print("BEST PICK: {0}".format(best_pick[1]))
    print("WITH SMALL CLUSTER {0}".format(best_pick[0]))

def add_all_songs():
    for (title, artist) in converge_db.all_song_data():
        try:
            create_json(title, artist)
        except ValueError:
            pass

def json_all_modern():
    first_modern_data = next(iter(lastfm_api.get_popular()))
    modern_title, modern_artist, modern_match = first_modern_data
    converge_db.c.execute("SELECT simple_id FROM simple_song_id WHERE title = ? AND artist = ?", (modern_title, modern_artist))
    # Get the first new addition to the database
    first_modern_sid = converge_db.c.fetchone()[0]
    # Every sid after is a new sid
    temp_cursor = converge_db.conn.cursor()
    # Ignore the sids that we have no similars for
    temp_cursor.execute("SELECT simple_id_orig FROM simple_similars WHERE simple_id_orig > ?", (first_modern_sid - 1,))
    for new_sid in temp_cursor:
        title, artist = converge_db.c.execute("SELECT title, artist FROM simple_song_id WHERE simple_id = ?", new_sid).fetchone()
        create_json(title, artist)


def make_json_from_anywhere(title, artist, *, num_clusters=None, top_size=None):
    title, artist = title.lower(), artist.lower()
    converge_db.add_all_sim_lastfm(title, artist)
    create_json(title, artist, num_clusters=num_clusters, top_size=top_size)


def add_many_songs(artist, *, num_songs=1, num_clusters=5, top_size=None):
    """
    Adds the top songs by the artist until it has clustered num_songs songs, or reached all available songs by artist
    """
    i = 0
    for (title, *_) in lastfm_api.get_top_songs(artist):
        if i == num_songs:
            print("Finished creating songs")
            break
        try:
            make_json_from_anywhere(title, artist, num_clusters=num_clusters, top_size=top_size)
            i += 1
        except ValueError:
            print("Not enough data to add song {0} by {1}".format(title, artist))

if __name__ == "__main__":
    if len(sys.argv) >= 3:
        if sys.argv[2].isdigit():
            filename, artist, num_songs, *_ = sys.argv
            num_songs = int(num_songs)
            add_many_songs(artist, num_songs=num_songs)
        else:
            filename, title, artist, *_ = sys.argv
            make_json_from_anywhere(title, artist)
    elif len(sys.argv) == 2:
        filename, artist = sys.argv
        add_many_songs(artist)
    else:
        # make_json_from_anywhere("Africa", "toto")
        print(list(lastfm_api.get_top_songs("journey")))
        # add_many_songs("journey")

