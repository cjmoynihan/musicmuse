import db_reader
import numpy as np
from sklearn.cluster import SpectralClustering
import json
import math

D = db_reader.db()
TrackReader = db_reader.TrackReader()

def get_similarity_matrix(track_id, sim_limit=None):
    """
    Creates an inverse similarity matrix for use with Spectral Clustering
    k sets a limit on the amount of similar songs being used (max songs)
    """
    print("Gathering similar songs")
    # similars, ratings = zip(*((sim_id, rating) for (sim_id, rating) in D.sorted_similars(track_id)))  # if rating >= .5 ))

    similars, ratings = zip(*((sim_id, rating) for (sim_id, rating) in D.sorted_similars(track_id))) # if rating >= .5 ))
    fixed_similar_ratings = list()
    for similar, rating in zip(similars, ratings):
        song_data = TrackReader.get_song(similar)
        if song_data:
            song_data = song_data[0]
            if not any(song_data == sd for (sd, rating) in fixed_similar_ratings):
                fixed_similar_ratings.append(((song_data[0], song_data[1]), rating))
    similars, ratings = zip(*((next(TrackReader.get_track_ids(*similar)), rating) for similar, rating in fixed_similar_ratings))


    # DEBUG
    # print(similars)
    # tid_data = dict()
    # # Organize the data by tid
    # for tid, rating in zip(similars, ratings):
    #     # Check for dups here
    #     tid_data.setdefault(tid, {"song_data": list(), "ratings": list()})
    #     song_data = TrackReader.get_song(tid)
    #     if not song_data:
    #         song_data = None
    #         print("Tid {0}: No data".format(tid))
    #     else:
    #         # Format the song data
    #         song_data = song_data[0]
    #         title, artist = song_data
    #         print("Tid {0}: {1} by {2}".format(tid, title, artist))
    #     print("Rating {0}".format(rating))
    #     tid_data[tid]["song_data"].append(song_data)
    #     tid_data[tid]["ratings"].append(rating)
    # all_song_data = set(song_data for tid in tid_data.keys() for song_data in tid_data[tid]['song_data'] if song_data is not None)
    # print("All similar song data")
    # print('\n'.join('{0} by {1}'.format(*song_data) for song_data in all_song_data))
    # # Organize the data by song name
    # # Double check that there are no songs that have differing tids or ratings
    # song_checker = dict()
    # for tid in tid_data.keys():
    #     for song_data, rating in zip(tid_data[tid]['song_data'], tid_data[tid]['ratings']):
    #         if song_data is not None:
    #             song_checker.setdefault(song_data, {'tid':list(), 'rating':list()})
    #             song_checker[song_data]['tid'].append(tid)
    #             song_checker[song_data]['rating'].append(rating)
    # print()
    # print("Do all title, songs have the same rating?")
    # for song_data in all_song_data:
    #     num_ratings = len(set(song_checker[song_data]['rating'])) == 1
    #     if num_ratings > 1:
    #         print("Conflicting ratings with song data {0}".format(song_data))
    # print(all(len(set(song_checker[song_data]['rating'])) == 1 for song_data in all_song_data))
    #
    # exit()
    # END DEBUG
    if sim_limit is not None:
        similars = similars[:sim_limit]
    # Just assume they are not likely or unlikely if nothing comes up
    print("Creating similarity matrix")
    # Simply set 0.5 for values that have no information of
    similarity_matrix = [[0 if i == j else 0.5 for j in range(len(similars))] for i in range(len(similars))]
    for i, sim_id in enumerate(similars):
        if (sim_limit is not None) and i >= sim_limit:
            break
        print("On song {0}/{1}".format(i+1, len(similars)))
        for other_track_id, other_similarity in filter(lambda tid: tid in similars, D.sorted_similars(sim_id)):
            # This will set a coefficient between 0 and 1
            # Reverses the coefficient because cosine similarity works the opposite of normal similarity
            similarity_matrix[i][similars.index(other_track_id)] = 1 - other_similarity
    print("Finished creating similarity matrix")
    return similars, np.matrix(similarity_matrix), ratings


def n_clustering(track_id, num_clusters=5, sim_limit=None):
    """
    This method clusters the songs related to track_id into k clusters
    The function maximizes the similarity between songs in the same cluster
    & minimizes dissimilarity between songs in opposite clusters

    :param track_id: The original track as a string
    :param num_clusters: The number of clusters to generate
    :param sim_limit: The maximum songs to cluster, with no limit if None
    :return: A list of k lists, containing each of the tracks in each (the clusters)
    """
    similars, sim_matrix, ratings = get_similarity_matrix(track_id, sim_limit)
    clusters = [list() for _ in range(num_clusters)]
    print("Clustering similars with {0} clusters".format(num_clusters))
    clustering_result = SpectralClustering(num_clusters).fit_predict(sim_matrix)
    for (i, (song, cluster_num)) in enumerate(zip(similars, clustering_result), 1):
        print("On song {0}/{1}".format(i, len(similars)))
        clusters[cluster_num].append(song)
    print("Finished clustering")
    # Possibly add method for separate analysis of individual clusters
    sorted_sim_ratings = sorted(list(zip(similars, ratings)), reverse=True)
    sorted_sim = list(next(zip(*sorted_sim_ratings)))
    sim_rating = {s:r for (s, r) in sorted_sim_ratings}
    for c in clusters:
        c.sort(key=lambda x: next(i for (i, s) in enumerate(sorted_sim) if s == x))
    return [(c, sum(sim_rating[s] for s in c)/len(c)) for c in map(list, clusters)]

def reach_out(track_ids, track_count=200, num_clusters=5):
    """
    An experimental method for creating larger webs from smaller ones
    """
    print("Gathering similar songs")
    similarity_network = set(track_ids)
    newest_track_ids = similarity_network
    while(newest_track_ids and len(similarity_network) < track_count):
        for track_id in newest_track_ids:
            for sim_id, _ in zip(*((sim_id, rating) for (sim_id, rating) in D.sorted_similars(track_id) if rating >= .5 and track_id not in similarity_network)):
                newest_track_ids.add(sim_id)
        newest_track_ids = newest_track_ids.difference(similarity_network)
        similarity_network = similarity_network.union(newest_track_ids)
    similarity_network = list(similarity_network)
    print("Creating similarity matrix")
    # Simply set 0.5 for values that have no information of
    similarity_matrix = [[0 if i == j else 0.5 for j in range(len(similarity_network))] for i in range(len(similarity_network))]
    for i, sim_id in enumerate(similarity_network):
        print("On song {0}/{1}".format(i+1, len(similarity_network)))
        for other_track_id, other_similarity in filter(lambda tid: tid in similarity_network, D.sorted_similars(sim_id)):
            # This will set a coefficient between 0 and 1
            # Reverses the coefficient because cosine similarity works the opposite of normal similarity
            similarity_matrix[i][similarity_network.index(other_track_id)] = 1 - other_similarity
    print("Finished creating similarity matrix")
    similars, sim_matrix = similarity_network, np.matrix(similarity_matrix)

    # Just going to stuff this in here to ease jury rigging
    clusters = [list() for _ in range(num_clusters)]
    print("Clustering similars with {0} clusters".format(num_clusters))
    clustering_result = SpectralClustering(num_clusters).fit_predict(sim_matrix)
    for (i, (song, cluster_num)) in enumerate(zip(similars, clustering_result), 1):
        print("On song {0}/{1}".format(i, len(similars)))
        clusters[cluster_num].append(song)
    print("Finished clustering")
    # Possibly add method for separate analysis of individual clusters
    return [c for c in clusters]


def create_json(track_id, num_clusters = 5, top_size = 20):
    clustering = n_clustering(track_id, num_clusters)
    title, artist = TrackReader.get_song(track_id)[0]
    json_obj = list()
    with open('jsons/' + title + '.txt', 'w') as f:
        for (i, (cluster, distance)) in enumerate(clustering):
            songs, artists = zip(*((TrackReader.get_song(tid)[0] for tid in cluster)))
            songs, artists = list(songs)[:top_size], list(artists)[:top_size]
            center_distance = distance
            # For now just make all of the center_distances
            angle = math.pi * 2 * i/len(clustering)
            print(angle)
            json_obj.append({
                "songs": songs,
                "artists": artists,
                "centerDistance": center_distance,
                "angle": angle
            })
        print('\n'.join(str(len(item["songs"])) for item in json_obj))
        json.dump(json_obj, f)




if __name__ == '__main__':
    pass
    # track_id = "TRAWOYD128F4215DDD"
    # top_size = 20
    # clustering = n_clustering(track_id, 5)
    # title, artist = TrackReader.get_song(track_id)[0]
    # json_obj = list()
    # with open(title + '.txt', 'w') as f:
    #     for (i, (cluster, distance)) in enumerate(clustering):
    #         songs, artists = zip(*((TrackReader.get_song(tid)[0] for tid in cluster)))
    #         songs, artists = list(songs)[:top_size], list(artists)[:top_size]
    #         center_distance = distance
    #         angle = math.pi * 2 * i/len(clustering)
    #         print(angle)
    #         json_obj.append({
    #             "songs": songs,
    #             "artists": artists,
    #             "centerDistance": center_distance,
    #             "angle": angle
    #         })
    #     print('\n'.join(str(len(item["songs"])) for item in json_obj))
    #     json.dump(json_obj, f)


