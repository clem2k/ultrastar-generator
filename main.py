import sys
import os
import json
from config import logger
from ultrastar import process_song

def main():
    arg_count = len(sys.argv)
    
    # ---------------------------
    # Batch Mode: No extra arguments.
    # ---------------------------
    if arg_count == 1:
        # In batch mode, the song list is read from a JSON file.
        songs_filepath = "./songs.json"
        if not os.path.isfile(songs_filepath):
            logger.error(f"File {songs_filepath} not found.")
            sys.exit(1)
        try:
            # Open and load the songs list from the JSON file.
            with open(songs_filepath, "r", encoding="utf-8") as file:
                songs_list = json.load(file)
        except Exception as error:
            logger.error(f"Error reading {songs_filepath}: {error}")
            sys.exit(1)
        
        # Process each song in the list.
        for song in songs_list:
            artist = song.get("artist")
            title = song.get("title")
            language = song.get("language")
            mp3_path = song.get("file")
            logger.debug(f"Song: {artist} - {title}")
            logger.debug(f"Language: {language}")
            logger.debug(f"MP3 file: {mp3_path}")
            
            # Both artist and title are mandatory for processing.
            if not artist or not title:
                logger.error("Invalid song: 'artist' and 'title' are required.")
                continue
            
            logger.debug(f"Processing song: {artist} - {title}")
            
            if not mp3_path or not os.path.isfile(mp3_path):
                logger.error(f"MP3 file not found for {artist} - {title}.")
                # Skip to the next song.
                continue
            else:
                # Process the song: this function generates the UltraStar file.
                process_song(mp3_path, artist, title, language)
                # remove temp mp3 file
                try:
                    os.remove(mp3_path)
                except Exception as error:
                    logger.error(f"Error removing {mp3_path}: {error}")
    
    # ---------------------------
    # Single MP3 Mode: One argument provided.
    # ---------------------------
    elif arg_count == 2:
        # The user provided the full path to a single MP3 file.
        mp3_path = sys.argv[1]
        if not os.path.isfile(mp3_path):
            logger.error(f"MP3 file not found: {mp3_path}")
            sys.exit(1)
        process_song(mp3_path)
        
    # ---------------------------
    # Incorrect Usage
    # ---------------------------
    else:
        # If an incorrect number of arguments is provided, output a usage error message.
        logger.error("Usage: python main.py <mp3_file_path> OR python main.py (batch mode with songs.json)")
        sys.exit(1)

if __name__ == "__main__":
    main()
