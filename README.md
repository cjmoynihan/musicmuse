# MusicMuse
Visualization for music clusters based on pairwise similarity.
This project takes songs similar to an input song
then groups them based on what songs people tend to listen to together.

* Similarity refers to the % of people that like the first, also like the second.
* Cluster size corresponds to the number of songs in the cluster.
* Cluster distance corresponds to the similarity of the cluster and the query.
* The angular distance between clusters corresponds to their average pairwise similarity.
* Two clusters have the same color if there is a significant overlap in preference across some songs.

A project for CS590V.

## Running the frontend
Note: Running the frontend requires a spotify account

Running the following will start up the server:
```bash
cd front-end
python -m SimpleHTTPServer 8000
```
You can then use your favorite browser to visit `localhost:8000`.

## Add songs through the backend
To add songs using the python script, you must first have a python3 environment with these dependencies:
* numpy
* sklearn
* requests

#### Options for adding new songs:

Each of these options looks up the data if it hasn't yet been stored.
Then does clustering on it and its similar songs

```bash
python_path backend/simple_clustering.py "title" "artist"
```
Does clustering for the song with the name and artist: title, artist

```bash
python_path backend/simple_clustering.py "artist" num_songs
```
Clusters the top num_songs by artist

