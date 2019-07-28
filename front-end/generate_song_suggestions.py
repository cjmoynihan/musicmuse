#!/usr/bin/env python3
"""
A simple script that updates SongsSuggestions.js
Since as I add songs the listing doesn't update
"""

# imports
from path import Path

# constants
cluster_directory = 'songjson'
cluster_ext = 'json'
ss_filename = 'js/SongsSuggestions.js'

def get_children(dir_name):
    """Gets every file in dir that ends with the extension"""
    dir = Path(dir_name)
    yield from dir.files(f'*.{cluster_ext}')

def get_file_names(dir_name):
    """Gets the names of every file in the listing, minus the file extension"""
    print("Collecting songs")
    for child in get_children(dir_name):
        # Remove the front of the path
        child = str(child.basename())
        # Truncate the file extension
        child = child[:-(len(cluster_ext)+1)]
        # Escape quotation characters
        child = child.replace('"', '\\"')
        yield f'"{child}"'

def write_song_suggestions():
    """Writes all the found songs to the cache for the javascript"""
    filenames = sorted(get_file_names(cluster_directory))
    print("Writing songs")
    with open(ss_filename, 'w') as f:
        f.write('var songsSuggestions = [{0}];'.format(', '.join(filenames)))

if __name__ == '__main__':
    write_song_suggestions()
