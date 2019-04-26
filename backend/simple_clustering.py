import db_reader
import numpy as np
from sklearn.cluster import SpectralClustering
import json
import math
from itertools import islice

converge_db = db_reader.converge_db()

def get_similarity_matrix_by_title_artist(title, artist):
    print("Gathering similar songs")
    all_data = converge_db.get_sorted_similars(title, artist)
    print("Found {0} similar songs".format(len(all_data)))
    all_data = (((title, artist), rating) for (title, artist, rating) in all_data)
    similars, ratings = zip(*all_data)
    similar_indexes = dict((value, i) for (i, value) in enumerate(similars))

    print("Creating the similarity matrix")
    # Create the default values
    similarity_matrix = [[0 if i==j else 0.5 for j in range(len(similars))] for i in range(len(similars))]
    for (i, (sim_title, sim_artist)) in enumerate(similars):
        # print("On song {0}/{1}".format(i+1, len(similars)))
        for (other_title, other_artist, other_similarity) in filter(lambda tas: tuple(tas[:2]) in similar_indexes.keys(), converge_db.get_sorted_similars(sim_title, sim_artist)):
            similarity_matrix[i][similar_indexes[(other_title, other_artist)]] = 1 - other_similarity
    print("Finished creating similarity matrix")
    return np.matrix(similarity_matrix), similars, ratings

def n_clustering(title, artist, num_clusters=5, top_size=20):
    # Collect all of the data
    sim_matrix, similars, ratings = get_similarity_matrix_by_title_artist(title, artist)

    # Determine which cluster to place things in
    clustering_results = SpectralClustering(num_clusters).fit_predict(sim_matrix)

    # Place songs into their respective clusters
    clusters = [list() for _ in range(num_clusters)]
    for (i, ((title, artist), cluster_num)) in enumerate(zip(similars, clustering_results), 1):
        # print("On song {0}/{1}".format(i, len(similars)))
        clusters[cluster_num].append((title, artist))
    print("Finished clustering")

    rating_by_song_data = {song_data: rating for (song_data, rating) in zip(similars, ratings)}

    # Clusters should already be sorted by similarity to original
    # Truncate large cluster size
    clusters = [cluster[:top_size] for cluster in clusters]
    # Get the average distance from the song to the center
    clusters = [(cluster, sum((1 - rating_by_song_data[song_data]) for song_data in cluster)/len(cluster)) for cluster in clusters]
    return clusters

json_filepath = ('jsons/', '.json')
title_artist_separator = ' '
def create_json(title, artist, num_clusters = 5, top_size = 20):
    clustering = n_clustering(title, artist, num_clusters, top_size=top_size)
    # Create the json representation
    json_obj = list()
    for (i, (cluster, center_distance)) in enumerate(clustering):
        titles, artists = zip(*cluster)
        # Evenly space clusters for now
        angle = math.pi * 2 * i/len(clustering)
        cluster_dict = {
            "songs": titles,
            "artists": artists,
            "centerDistance": center_distance,
            "angle": angle
        }
        json_obj.append(cluster_dict)
    title = title.lower()
    with open("{0}{1}{2}{3}{4}".format(json_filepath[0], title.replace('/', ''), title_artist_separator, artist.replace('/', ''), json_filepath[1]), 'w') as f:
        json.dump(json_obj, f)

if __name__ == "__main__":
    # TODO:
    # Pull the
    # Create angles using the amount of simlarity between clusters
        # Map the difference to a low and high amount
        # IE: create a similarity matrix of values between each two clusters
        # Set a highest and lowest amount based on the min and max of pairwise similarity between clusters
    # Include target_similarity
    # Set the gap of the angles to be where the legend is
    # Enable using real data w/ API
    # Chain to grab more values
    all_songs = converge_db.all_song_data()
    # print(sum(1 for _ in filter(lambda song_data: len(converge_db.get_sorted_similars(*song_data)) >= 30, all_songs)))
    for (i, song_data) in enumerate(filter(lambda song_data: len(converge_db.get_sorted_similars(*song_data)) >= 30, all_songs), 1):
        print(song_data)
        create_json(*song_data)
        print("FINISHED {0}".format(i))
    # converge_db.c.execute("SELECT title, artist FROM simple_song_id WHERE artist = ?", ("Kesha",))
    # for (title, artist) in converge_db.c:
    #     print(title, artist)
    #     num_similar = len(converge_db.get_sorted_similars(title, artist))
    #     if num_similar >= 10:
    #         create_json(title, artist)
    # print("{0} songs clusters".format(i))
    # print("Getting songs::")
    # num_songs = 10
    # for (title, artist) in islice(converge_db.all_song_data(), num_songs):
    #     print("Title: {0}".format(title))
    #     print("Artist: {0}".format(artist))
    #     create_json(title, artist)