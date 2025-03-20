# =============================================================================
# ultrastar.py - Ultrastar File Format Processing Module
#
# This module provides functions and classes to process song files in the 
# UltraStar format. The UltraStar format is a timed text file format used for 
# karaoke songs. Each song file typically consists of a header section with 
# metadata (e.g., #TITLE, #ARTIST, #BPM, #GAP) and a body section with the 
# notes of the song. Each note is represented as a line with the format:
#
#   [NoteType] [StartBeat] [Length] [Pitch] [Text]
#
# For example:
#   : 96 32 21 Hello
#   - 136 
#   : 160 6 17 world
#
# where:
#   - The note type (e.g., ":" for normal note) indicates how the note is 
#     scored. Other types (e.g., "*" for golden note, "F" for freestyle) exist.
#   - The start beat is computed relative to the GAP (delay from audio start).
#   - The length is in beats and is calculated based on BPM.
#   - The pitch represents the note's half-tone offset relative to C4 (where C4 is 0).
#   - The text is the syllable or word to be sung.
#
# This module also includes functionality to insert end-of-phrase markers 
# (lines starting with "-") based on gaps between note lines.
#
# The code below is not meant to be modified. It has been provided by the user,
# and extensive comments have been added to help any non-native English speaker
# (e.g., French, German, etc.) understand the rules and the implementation.
# =============================================================================

from decimal import Decimal
import hashlib
import os
import shutil
from dataclasses import dataclass
from tkinter import Image
import requests
from config import FRACTION, GAP_THRESHOLD, MAX_WORDS_PER_PHRASE, SPLEETER, SPLEETER_MODEL, logger, OUTPUT_FOLDER, debug, IMG_TARGET_HEIGHT, IMG_TARGET_WIDTH
from mp3 import detect_bpm, extract_image, read_tags, save_image, spleet, get_music_info, transcribe_audio, get_duration
from pitcher import process_pitch
import random


# =============================================================================
# Data Classes Definitions
# =============================================================================

@dataclass
class FileInfo:
    """
    Data class representing a file information entry.
    
    Attributes:
        file_code (int): Unique identifier for the file type.
        file_type (str): Type of file (e.g., AUDIO, VIDEO, COVER).
        full_path (str): The full file system path where the file is stored.
        file_name (str): The name of the file only.
    """
    file_code: int       # Unique file identifier code
    file_type: str       # Type of file (e.g., AUDIO, VIDEO, etc.)
    full_path: str       # Full path including directory and file name
    file_name: str       # File name only

@dataclass
class Lyric:
    """
    Data class representing a single lyric line (note) in the UltraStar file.
    
    Attributes:
        note_type (str): The type of note, e.g., ":" for a normal note, "-" for an end-of-phrase marker.
        start_beat (int): The beat number where this note starts (calculated based on BPM and GAP).
        length (int): Duration of the note in beats.
        pitch (int): The pitch of the note as a number of half-tones relative to C4 (C4 = 0).
        text (str): The syllable or word to be displayed and sung.
    """
    note_type: str
    start_beat: int
    length: int
    pitch: int
    text: str

# =============================================================================
# Song Class to encapsulate song data and file infos
# =============================================================================

class Song:
    """
    The Song class encapsulates all metadata and file information related 
    to a song in the UltraStar format.
    
    It collects metadata from the mp3 file, generates a unique ID, creates 
    the necessary output folder, and sets up various properties needed for 
    further processing (e.g., BPM, duration, GAP, lyrics, and pitch values).
    
    The metadata in the header of an UltraStar file should include at least 
    #TITLE, #ARTIST, #BPM and #GAP, and additional tags (e.g., #ALBUM, #GENRE) 
    may also be added.
    """
    def __init__(self, artist: str, title: str, mp3_path: str):
        self.artist = artist
        self.title = title
        self.mp3_path = mp3_path
        self.unique_id = self._generate_unique_id()
        self.output_folder = self._create_output_folder()
        self.file_info_dict = self._generate_file_info_dict()
        self.spleeter_folder = ""
        self.file_to_transcribe = ""
        self.words = None
        self.lyrics = []  # Will be a list of Lyric objects
        self.ultrastar_header = []  # List to hold header lines for the UltraStar file
        self.bpm = 0
        self.duration = 0
        self.gap = 0
        self.pitchs = []  # List to hold pitch information (dictionaries with start, end, pitch)
        
        # Retrieve additional music info such as album, genre, etc.
        result = get_music_info(artist, title, self.unique_id)
        self.album = result.get("album")
        self.genre = result.get("genre")
        self.year = result.get("year")
        self.decade = result.get("decade")
        self.language = result.get("language")
        self.cover = result.get("cover")
        self.description = result.get("description")
        self.local_cover = ""
    
    def _generate_unique_id(self) -> str:
        """
        Generates a unique identifier for the song based on the artist and title.
        
        The UID is calculated using SHA256 hashing on the string "artist - title".
        This UID is later used to name files and folders consistently.
        """
        logger.debug(f"Generating unique id for: {self.artist} - {self.title}")
        uid = f"{self.artist} - {self.title}"
        sha256 = hashlib.sha256()
        sha256.update(uid.encode())
        return sha256.hexdigest()
    
    def _create_output_folder(self) -> str:
        """
        Creates the output folder for the song.
        
        The folder is named using the artist and title. Any '/' characters are 
        replaced by '-' to avoid file system issues.
        """
        artist_folder = self.artist.replace("/", "-")
        title_folder = self.title.replace("/", "-")
        song_folder = f"{artist_folder} - {title_folder}"
        output_folder = os.path.join(OUTPUT_FOLDER, song_folder)
        os.makedirs(OUTPUT_FOLDER, exist_ok=True)
        os.makedirs(output_folder, exist_ok=True)
        logger.debug(f"Output folder path: {output_folder}")
        return output_folder
    
    def _generate_file_info_dict(self) -> dict:
        """
        Generates a dictionary containing FileInfo objects for various file types.
        
        This dictionary maps file types (e.g., "MP3", "VIDEO", "COVER") to their 
        corresponding FileInfo, which includes paths and file names.
        """
        uid = self.unique_id
        file_info_list = [
            FileInfo(1, "WIP_IMG", os.path.join(self.output_folder, f"WIP_{uid}.jpg"), ""),
            FileInfo(2, "WIP_SUBTITLE", os.path.join(self.output_folder, f"{uid}.srt"), f"{uid}.srt"),
            FileInfo(101, "MP3", os.path.join(self.output_folder, f"{uid}.mp3"), f"{uid}.mp3"),
            FileInfo(121, "VOCALS", os.path.join(self.output_folder, f"{uid} [VOC].mp3"), f"{uid} [VOC].mp3"),
            FileInfo(122, "INSTRUMENTAL", os.path.join(self.output_folder, f"{uid} [INSTR].mp3"), f"{uid} [INSTR].mp3"),
            FileInfo(131, "COVER", os.path.join(self.output_folder, f"{uid} [CO].jpg"), f"{uid} [CO].jpg"),
            FileInfo(132, "BACKGROUND", os.path.join(self.output_folder, f"{uid} [BG].jpg"), f"{uid} [BG].jpg"),
        ]
        info_dict = {fi.file_type: fi for fi in file_info_list}
        return info_dict

    @classmethod
    def from_mp3(cls, mp3_path: str, artist: str = None, title: str = None):
        """
        Creates a Song instance from an mp3 file by extracting tags (artist and title).
        
        It uses the function read_tags to extract metadata from the mp3.
        """
        if not artist or not title:        
            logger.debug(f"Extracting tags from: {mp3_path}")
            tags = read_tags(mp3_path)
            artist = tags.get("artist")
            title = tags.get("title")
            if isinstance(artist, list):
                artist = artist[0]
            if isinstance(title, list):
                title = title[0]
            if not artist or not title:
                # ask user to provide artist and title
                logger.warning(f"Unable to extract artist/title from: {mp3_path}")
                artist = input("Please provide the artist name: ")
                title = input("Please provide the song title: ")
            if not artist or not title:
                raise ValueError(f"Unable to extract artist/title from: {mp3_path}")
            return cls(artist, title, mp3_path)
        else:
            return cls(artist, title, mp3_path)
        
# =============================================================================
# Main Processing Function
# =============================================================================

def process_song(mp3_path: str, artist: str = None, title:str = None, language:str = None) -> None:
    """
    Main function to process a song from an mp3 file.
    
    It performs the following steps:
      - Create a Song instance from the mp3.
      - Generate and create necessary output files (audio, video, cover, etc.).
      - Optionally process vocals/instrumental separation using Spleeter.
      - Transcribe audio to extract timing words.
      - Process pitch information.
      - Convert transcribed words into lyric objects.
      - Insert end-of-phrase markers according to UltraStar rules.
      - Update short lyrics to ensure minimum duration.
      - Create the final UltraStar text file with header and lyrics.
    
    If any error occurs, it is logged and raised.
    """
    
    # logger debug all parameters
    logger.debug(f"mp3_path: {mp3_path}")
    logger.debug(f"artist: {artist}")
    logger.debug(f"title: {title}")
    logger.debug(f"language: {language}")

    try:
        logger.debug(f"Processing song: {mp3_path}")
        
        if not artist or not title:
            song = Song.from_mp3(mp3_path)
        else:
            song = Song.from_mp3(mp3_path, artist, title)
        
        for fi in song.file_info_dict.values():
            logger.debug(f"File info: {fi}")
        logger.debug(f"Creating files for: {song.artist} - {song.title}")
        
        # If SPLEETER is enabled, separate vocals and instrumental parts.
        if SPLEETER:
            song.spleeter_folder = _separate_vocals_instrumental(song)
            song.file_to_transcribe = song.spleeter_folder + "/vocals.mp3"
        else:
            logger.debug("Skipping spleeter processing")
            song.spleeter_folder = None
            song.file_to_transcribe = song.mp3_path
        
        # Transcribe audio to get timing information (words and language).
        if not language:
            logger.debug("Transcribing audio without language")
            words, language = transcribe_audio(song.file_to_transcribe, song.artist, song.title, song.unique_id)
        else:
            logger.debug(f"Transcribing audio with language: {language}")
            words, detected_language = transcribe_audio(song.file_to_transcribe, song.artist, song.title, song.unique_id, language=language)
        
        if not words:
            raise ValueError("No words transcribed")
        
        song.words = words
        song.language = language

        _create_files(song)
        song = _update_with_music_info(song)
        # Process pitch using an external function, result stored in song.pitchs.
        song.pitchs = process_pitch(song.words, song.file_to_transcribe, song.unique_id)
        song = _words_to_lyrics(song)
        
        # Insert end-of-phrase markers based on gaps in lyrics.
        song = _end_of_phrase(song)
        # Ensure that every lyric has a minimum duration of 1 beat.
        song = _update_short_lyrics(song)
        lyrics = _lyrics_to_text(song)

        ultrastar_file = _create_ultrastar_file(song, lyrics)
        logger.info(f"Ultrastar file created: {ultrastar_file}")
        
        # remove all .wav files from output folder
        for file in os.listdir(song.output_folder):
            if file.lower().endswith(".wav"):
                _cleanup_file(os.path.join(song.output_folder, file))
        
        # create a zip from the folder
        shutil.make_archive(song.output_folder, 'zip', song.output_folder)
        logger.info(f"Zip file created: {song.output_folder}.zip")
        
        # Clean up temporary files if not in debug mode.
        model = ""
        if not debug:
            _cleanup_folder(song.output_folder)
            if SPLEETER:
                _cleanup_folder(song.spleeter_folder)
                if debug:
                    logger.warning(f"model downgrade to 'htdemucs' for spleet")
                    model = "htdemucs"
                else:
                    model = SPLEETER_MODEL                    
                _cleanup_folder(OUTPUT_FOLDER + "/" + model)
            _cleanup_folder(song.output_folder)
        

        
    except Exception as e:
        logger.error(f"Error processing song: {e}")
        raise

# =============================================================================
# Helper Function for File Creation using Song properties
# =============================================================================

def _create_files(song: Song) -> None:
    """
    Creates necessary files (cover, mp3, video, etc.) for the song using 
    the file_info_dict from the Song object.
    
    This function iterates over each file type and calls the corresponding 
    creation function. It then performs file cleanup if necessary.
    """
    creation_functions = {
        "WIP_IMG": _create_WIP_IMG_file,
        "WIP_SUBTITLE": _create_WIP_SUBTITLE_file,
        "MP3": _create_mp3_file,
        "VOCALS": _create_vocals_file,
        "INSTRUMENTAL": _create_instrumental_file,
        "COVER": _create_cover_file,
        "BACKGROUND": _create_background_file,
    }
    try:
        for file_type, create_func in creation_functions.items():
            if file_type in song.file_info_dict:
                file_info = song.file_info_dict[file_type]
                logger.debug(f"Creating file of type {file_type} at {file_info.full_path}")
                updated_song = create_func(file_info.full_path, song)
                if updated_song is not None:
                    song = updated_song
                else:
                    logger.warning(f"La fonction {create_func.__name__} a renvoyé None, on conserve l'objet song actuel.")
            else:
                logger.error(f"Unknown file type: {file_type}")
    except Exception as e:
        logger.error(f"Error creating files: {e}")
        raise

    try:
        # Clean up temporary files if not in debug mode.
        for key, file_info in song.file_info_dict.items():
            if "WIP" in key:
                _cleanup_file(file_info.full_path)
        if SPLEETER:
            _cleanup_folder(song.spleeter_folder)
            model=""
            if debug:
                logger.warning(f"model downgrade to 'htdemucs' for spleet")
                model = "htdemucs"
            else:
                model = SPLEETER_MODEL                    
            _cleanup_folder(OUTPUT_FOLDER + "/" + model)
        # delete all wav files from output folder
        for file in os.listdir(song.output_folder):
            if file.lower().endswith(".wav"):
                _cleanup_file(os.path.join(song.output_folder, file))
    except Exception as e:
        logger.error(f"Error cleaning up files: {e}")

def _separate_vocals_instrumental(song: Song) -> str:
    """
    Separates the vocals and instrumental from the original mp3 using the 
    Spleeter tool. Returns the folder where the separated files are stored.
    """
    output = spleet(song.mp3_path, SPLEETER_MODEL, OUTPUT_FOLDER)
    logger.debug(f"Spleet output: {output}")
    return output

def _update_with_music_info(song: Song) -> Song:
    """
    Updates the song object with music information such as BPM, duration, 
    and GAP. Then, adds mandatory and optional UltraStar headers.
    
    UltraStar files must have at least #TITLE, #ARTIST, #BPM, and #GAP in the header.
    """
    song.bpm = _get_bpm(song)
    song.duration = _get_duration(song)
    song.gap = _get_gap(song)
    
    song = _add_mandatory_headers(song)
    song = _add_optional_headers(song)
    
    return song

def _add_mandatory_headers(song: Song) -> Song:
    """
    Adds mandatory header lines for an UltraStar file.
    
    These include:
      - #TITLE: The song title.
      - #ARTIST: The artist name.
      - #BPM: The beats per minute.
    
    According to UltraStar rules, these tags are required.
    """
    song.ultrastar_header.append("#TITLE:" + song.title)
    song.ultrastar_header.append("#ARTIST:" + song.artist)
    song.ultrastar_header.append("#BPM:" + str(song.bpm))
    
    return song

def _add_optional_headers(song: Song) -> Song:
    """
    Adds optional header lines for an UltraStar file.
    
    For example, the #GAP tag is crucial to synchronize the lyrics with the audio.
    Other optional headers like #CREATOR, #ALBUM, #GENRE, #YEAR, #DECADE, and 
    #LANGUAGE are added if available.
    """
    song.ultrastar_header.append(f"#GAP:{song.gap}")
    
    user = os.getlogin()
    if user:
        song.ultrastar_header.append(f"#CREATOR:{user}")
    else: 
        song.ultrastar_header.append("#CREATOR:Ultrastar Generator")
    
    if song.album:
        song.ultrastar_header.append(f"#ALBUM:{song.album}")
    if song.genre:
        song.ultrastar_header.append(f"#GENRE:{song.genre}")
    if song.year:
        song.ultrastar_header.append(f"#YEAR:{song.year}")
    if song.decade:
        song.ultrastar_header.append(f"#DECADE:{song.decade}")
    if song.language:
        song.ultrastar_header.append(f"#LANGUAGE:{_convert_language_to_code(song.language)}")
    return song
    
def _convert_language_to_code(language: str) -> str:
    """
    Converts a language abbreviation to its full English name.
    """
    list_of_languages = {
        "en": "english",
        "fr": "french",
        "es": "spanish",
        "de": "german",
        "it": "italian"
        }
    language = language.lower()
    code = list_of_languages.get(language)
    
    if code:
        return code
    else:
        logger.warning(f"Unknown language: {language}")
        raise ValueError(f"Unknown language: {language}")
    
def _header_to_string(song: Song) -> str:
    """
    Converts the list of UltraStar header lines to a single string.
    
    Each header is separated by a newline.
    """
    return "\n".join(song.ultrastar_header)

def _get_duration(song: Song) -> int:
    """
    Retrieves the duration of the mp3 file in milliseconds.
    
    This value can be used to validate the song length.
    """
    return get_duration(song.mp3_path)

def _get_bpm(song: Song) -> int:
    """
    Detects the BPM of the mp3 file and multiplies it by 4.
    
    In older UltraStar formats, the BPM in the file is 4 times the real BPM.
    """
    return detect_bpm(song.mp3_path) * 4

def _get_gap(song: Song) -> int:
    """
    Calculates the GAP (in milliseconds) from the song's transcription.
    
    The GAP represents the time offset between the start of the audio and beat 0.
    If transcription data (words) is available, it uses the first timing value.
    """
 
    if song.words:
        return int(round(song.words[0][0] * 1000))
    return 0

# =============================================================================
# File Creation Functions (using Song instance)
# =============================================================================

def _create_WIP_IMG_file(full_path: str, song: Song) -> None:
    """
    Creates a WIP image file (Work-In-Progress image) for the song.
    
    Attempts to extract the cover image from the mp3 file. If not found, it
    creates a blank image.
    """
    logger.debug(f"Creating WIP image file: {full_path}")
    logger.debug("Trying to extract cover image from mp3 file")
    result = extract_image(song.mp3_path, full_path)
    if not result:
        logger.error("Cover image not found in mp3 file")
        if song.cover:
            response = requests.get(song.cover, stream=True)
            if response.status_code == 200:
                with open(full_path, "wb") as file:
                    for chunk in response.iter_content(chunk_size=1024):
                        if chunk:
                            file.write(chunk)
            logger.debug("Writing cover image to mp3 file")
            save_image(song.mp3_path, full_path)
        else:
            logger.warning("Cover image not found")
            logger.warning("Creating blank image")
            if not os.path.exists(full_path):
                _create_blank_image(full_path)
    
    song.local_cover = full_path
    return song

def _create_WIP_SUBTITLE_file(full_path: str, song: Song) -> None:
    """
    Creates a Work-In-Progress subtitle file.
    
    This is a placeholder function for subtitle generation.
    """
    logger.debug(f"Creating WIP subtitle file: {full_path}")
    return song    

def _create_ultrastar_file(song: Song, lyrics: str) -> str:
    """
    Creates the final UltraStar text file.
    
    The file is composed of the header lines (joined by newline) followed by the
    lyrics (each line representing a note or marker). The file must end with an "E"
    to indicate the end of the song, as required by the UltraStar format.
    """
    full_path = os.path.join(song.output_folder, f"{song.unique_id}.txt")
    logger.debug(f"Creating Ultrastar file: {full_path}")
    header = _header_to_string(song)
    with open(full_path, "w") as file:
        file.write(header)
        file.write("\n")
        logger.debug("Processing lyrics")
        file.write(lyrics)
        file.write("\n")
    return full_path

def _create_mp3_file(full_path: str, song: Song) -> Song:
    """
    Creates a copy of the original mp3 file in the output folder.
    
    Also appends the #MP3 and #AUDIO header tags with the file name.
    """
    logger.debug(f"Creating MP3 file: {full_path}")
    shutil.copy(song.mp3_path, full_path)
    song.ultrastar_header.append("#MP3:" + song.file_info_dict["MP3"].file_name)
    song.ultrastar_header.append("#AUDIO:" + song.file_info_dict["MP3"].file_name)
    return song

def _create_vocals_file(full_path: str, song: Song) -> Song:
    """
    Creates the vocals file from the separated vocals (using Spleeter).
    
    Moves the vocals file from the spleeter folder to the output folder and 
    updates the header with the #VOCALS tag.
    """
    if not SPLEETER:
        logger.debug("Skipping vocals file creation")
        return song 
    logger.debug(f"Creating vocals file: {full_path}")
    source_file = song.spleeter_folder + "/vocals.mp3"
    song.file_to_transcribe = full_path
    if os.path.exists(source_file):
        shutil.move(source_file, full_path)
    else:
        logger.error(f"Vocals file not found: {source_file}")
        raise Exception(f"Vocals file not found: {source_file}")
    song.ultrastar_header.append("#VOCALS:" + song.file_info_dict["VOCALS"].file_name)
    return song

def _create_instrumental_file(full_path: str, song: Song) -> Song:
    """
    Creates the instrumental file from the separated non-vocals (using Spleeter).
    
    Moves the instrumental file from the spleeter folder to the output folder and 
    updates the header with the #INSTRUMENTAL tag.
    """
    if not SPLEETER:
        logger.debug("Skipping instrumental file creation")
        return song
    logger.debug(f"Creating instrumental file: {full_path}")
    source_file = song.spleeter_folder + "/no_vocals.mp3"
    if os.path.exists(source_file):
        shutil.move(source_file, full_path)
    else:
        logger.error(f"Instrumental file not found: {source_file}")
        raise Exception(f"Instrumental file not found: {source_file}")
    song.ultrastar_header.append("#INSTRUMENTAL:" + song.file_info_dict["INSTRUMENTAL"].file_name)
    return song

def _create_cover_file(full_path: str, song: Song) -> Song:
    """
    Creates the cover image file.
    
    Copies the local cover (if available) to the output folder and updates the header
    with the #COVER tag.
    """
    logger.debug(f"Creating cover file: {full_path}")
    if song.local_cover:
        shutil.copy(song.local_cover, full_path)
    else:
        logger.error("Cover image not found")
        _create_blank_image(full_path)
    song.ultrastar_header.append("#COVER:" + song.file_info_dict["COVER"].file_name)
    return song

def _create_background_file(full_path: str, song: Song) -> Song:
    """
    Creates the background image file.
    
    Copies the local cover (or background image) to the output folder and updates the header
    with the #BACKGROUND tag.
    """
    logger.debug(f"Creating background file: {full_path}")
    if song.local_cover:
        shutil.copy(song.local_cover, full_path)
    else:
        logger.error("Background image not found")
        _create_blank_image(full_path)
    song.ultrastar_header.append("#BACKGROUND:" + song.file_info_dict["BACKGROUND"].file_name)
    return song

def _create_blank_image(full_path: str) -> None:
    """
    Creates a blank image file (black) with the given full path.
    """
    logger.debug(f"Creating blank image file: {full_path}")
    img = Image.new("RGB", (IMG_TARGET_HEIGHT, IMG_TARGET_WIDTH), color="black")
    img.save(full_path)

# =============================================================================
# Helper Functions for File Cleanup
# =============================================================================

def _cleanup_file(full_path: str) -> None:
    """
    Removes a file at the given full path unless in debug mode.
    """
    if debug:
        logger.debug(f"DEBUG MODE: Skipping file cleanup: {full_path}")        
    else:
        logger.debug(f"Cleaning file: {full_path}")
        if os.path.exists(full_path):
            os.remove(full_path)

def _cleanup_folder(folder_path: str) -> None:
    """
    Deletes an entire folder recursively.
    """
    logger.debug(f"Cleaning folder: {folder_path}")
    if os.path.exists(folder_path):
        shutil.rmtree(folder_path, ignore_errors=True)

# =============================================================================
# Lyrics Processing Functions
# =============================================================================

def _get_pitch(start: Decimal, end: Decimal, song: Song) -> int:
    """
    Determines the pitch for a lyric note based on its start time.
    
    The pitch is selected from song.pitchs based on whether the note's start falls
    within the range defined by a pitch entry.
    
    UltraStar rules specify that pitch is expressed as the number of half-tones 
    relative to C4 (C4 = 0).
    """
    word_start = float(start)
    for pitch in song.pitchs:
        if pitch["start"] <= word_start < pitch["end"]:
            return pitch["pitch"]
    return 0

def _word_to_lyric(start: Decimal, end: Decimal, word: str, song: Song) -> Lyric:
    """
    Convertit un mot (avec son timing) en objet Lyric en utilisant nos fonctions
    de conversion pour obtenir le start beat et la durée (length).
    """
    note_type = _get_note_type(song)
    # Convertir les temps en float pour nos fonctions
    t_start = float(start)
    t_end = float(end)
    # Appliquer la conversion avec GAP et BPM extraits du song
    start_beat, length = _calculate_start_and_length(t_start, t_end, song.gap, song.bpm)
    
    pitch = _get_pitch(start, end, song)
    
    return Lyric(note_type, start_beat, length, pitch, word)

def _calculate_start_and_length(word_start, word_end, gap, bpm):
    """
    Convertit précisément les timestamps (début et fin) en beats UltraStar.
    - word_start et word_end sont en secondes.
    - gap est en millisecondes.
    - bpm est le BPM affiché dans le fichier (généralement 4 fois le BPM réel).
    
    La formule utilisée :
       tick = temps (en s) × (BPM × 4 / 60)
    """
    ms_per_beat = 60000 / (bpm * 4)  # correction ici : multiplier bpm par 4
    start_beat = int(round(((word_start * 1000) - gap) / ms_per_beat))
    end_beat = int(round(((word_end * 1000) - gap) / ms_per_beat))
    length_in_beats = max(end_beat - start_beat, 1)
    return start_beat, length_in_beats

def _words_to_lyrics(song: Song) -> Song:
    """
    Converts transcribed words (from audio transcription) into Lyric objects.
    
    It iterates over song.words (each element containing a start, end, and text)
    and creates a corresponding Lyric object using _word_to_lyric.
    """
    song.lyrics = []
    for word in song.words:
        start = word[0]
        end = word[1]
        text = _remove_punctuation(word[2])
        lyric = _word_to_lyric(start, end, text, song)
        song.lyrics.append(lyric)
        logger.debug(f"Lyric: {lyric}")
    
    return song

def _remove_punctuation(text: str) -> str:
    """
    Removes punctuation from a given text.
    
    This is used to clean up the text before processing.
    """
    list_of_punctuation = [".", ",", ";", ":", "!", "?", "\"", "(", ")", "[", "]", "{", "}", "-", "_", "–", "—"]
    return "".join([char for char in text if char not in list_of_punctuation])

def _lyrics_to_text(song: Song) -> str:
    """
    Converts the list of Lyric objects into the final UltraStar text format.
    
    For normal notes (note_type ":" or "*"), the line format is:
      [note_type] [start_beat] [length] [pitch] [text]
    
    For marker lines (note_type "-"), only the note type and the start beat are output,
    as specified in the UltraStar format.
    
    The file is terminated with an "E" on a separate line.
    """
    lyrics_text = ""
    for lyric in song.lyrics:
        if lyric.note_type == "-":
            # For marker lines, output only the marker and the start beat.
            lyrics_text += f"{lyric.note_type} {lyric.start_beat}\n"
        else:
            # For normal notes, output start_beat, length, pitch and text.
            lyrics_text += f"{lyric.note_type} {lyric.start_beat} {lyric.length} {lyric.pitch}  {lyric.text}\n"
    lyrics_text += "E\n"
    return lyrics_text

def _end_of_phrase(song: Song) -> Song:
    logger.debug("Inserting end-of-phrase markers")
    
    # Initialize an empty list to accumulate the new set of lyric lines (including markers)
    new_lyrics = []
    # This variable will hold the beat at which the current phrase ends 
    # (i.e., the maximum of start_beat + length for consecutive notes)
    current_phrase_end = None  
    # Compteur du nombre de mots dans la phrase courante
    phrase_word_count = 0

    # Iterate through all lyric lines by their index
    for i in range(len(song.lyrics)):
        # Get the current lyric line (an object of type Lyric)
        line = song.lyrics[i]
        logger.debug(f"Processing line: {line}")
        
        # Check if the current line is a normal note (represented by a colon ":" or golden represented by "*")
        if line.note_type == ":" or line.note_type == "*":
            # Append the current note to the new lyrics list
            new_lyrics.append(line)
            # Calculate the ending beat of this note (start beat + duration in beats)
            note_end = line.start_beat + line.length
            logger.debug(f"Note end: {note_end}")
            
            # Update the current phrase's end:
            # If we haven't set it yet, or if this note ends later than the current phrase end,
            # then update current_phrase_end to the end of this note.
            if current_phrase_end is None or note_end > current_phrase_end:
                current_phrase_end = note_end
                logger.debug(f"Current phrase end: {current_phrase_end}")
            
            # Increment the word count for the current phrase
            phrase_word_count += 1
            logger.debug(f"Phrase word count: {phrase_word_count}")
            
            # Check if the maximum number of words in the phrase is reached
            if phrase_word_count >= int(MAX_WORDS_PER_PHRASE):
                marker_start = current_phrase_end  # Insert marker at the end of the last word
                end_marker = Lyric("-", marker_start, 0, 0, "")
                new_lyrics.append(end_marker)
                logger.debug("----------------- End-of-Phrase Inserted due to max word count -----------------")
                logger.debug(f"Inserted end-of-phrase marker at beat {marker_start}")
                # Reset current phrase tracking
                current_phrase_end = None
                phrase_word_count = 0
            
            # Check if there is a next lyric line in the list
            if i < len(song.lyrics) - 1:
                # Get the next lyric line
                next_line = song.lyrics[i + 1]
                logger.debug(f"Next line: {next_line}")
                # Only consider next lines that are normal notes (":" or "*")
                if next_line.note_type == ":" or next_line.note_type == "*":
                    # Calculate the gap in beats between the current phrase's end and the next note's start
                    gap = next_line.start_beat - current_phrase_end if current_phrase_end is not None else 0
                    logger.debug(f"Gap: {gap}")
                    # If the gap exceeds the threshold, it's considered a phrase break
                    if gap >= int(GAP_THRESHOLD):
                        marker_start = current_phrase_end + int(round(gap * Decimal(FRACTION)))
                        end_marker = Lyric("-", marker_start, 0, 0, "")
                        new_lyrics.append(end_marker)
                        logger.debug("----------------- End-of-Phrase Inserted due to gap threshold -----------------")
                        logger.debug(f"Inserted end-of-phrase marker at beat {marker_start}")
                        # Reset phrase tracking for the next phrase
                        current_phrase_end = None
                        phrase_word_count = 0
        else:
            logger.debug("Non-note line found")
            new_lyrics.append(line)
            # Reset phrase tracking if a non-note is encountered
            current_phrase_end = None
            phrase_word_count = 0

    # Replace the song's lyrics with the new list that includes the end-of-phrase markers
    song.lyrics = new_lyrics
    # Return the updated Song object
    return song

def _update_short_lyrics(song: Song) -> Song:
    """
    Ensures that every lyric has a minimum duration of 1 beat.
    
    UltraStar rules require that the 'length' value of a note (duration) must be 
    at least 1. This function updates any lyric with a length less than 1 to 1.
    
    Args:
        song (Song): Main song object containing the lyrics.
    
    Returns:
        Song: Updated song object with corrected lyric durations.
    """
    logger.debug("Updating short lyrics")
    for i, lyric in enumerate(song.lyrics):
        if lyric.length < 1 and lyric.note_type != "-":
            logger.debug(f"Updating short lyric: {lyric}")
            song.lyrics[i].length = 1
    return song



# =============================================================================
# List of all the note_type (constant)
# : = normal, * = golden, F = free style, R = rap, G = rap golden
# frequency : ":" 85%, "*" = 15%, F, R and G = 0%
# =============================================================================

def _get_note_type(song) -> str:
    """
    Retourne le type de note pour un segment donné en se basant sur la répartition souhaitée
    des notes golden dans la chanson.
    
    Règles :
      - Environ 10% des notes doivent être golden ("*").
      - On ne peut pas avoir plus de 3 golden d'affilée.
      - Les golden ne doivent pas se concentrer en début de chanson.
      - Une fois le pourcentage atteint, seules des notes normales (":") sont utilisées.
      - Les notes de fin de phrase (type "-") ne sont pas modifiées.
    
    Args:
        song (Song): l'objet Song contenant song.words (la liste complète des mots)
                      et song.lyrics (les notes déjà traitées).
    Raises:
        ValueError: si start n'est pas strictement inférieur à end.
    
    Returns:
        str: ":" pour une note normale ou "*" pour une note golden.
    """
    
    # On considère que song.words contient la liste complète des notes prévues.
    total_notes = len(song.words) if song.words else 0
    # On compte dans song.lyrics les notes déjà créées (on ignore les marqueurs "-" éventuels).
    processed_notes = [ly for ly in song.lyrics if ly.note_type in [":", "*"]]
    processed_count = len(processed_notes)
    golden_count = sum(1 for ly in processed_notes if ly.note_type == "*")
    
    golden_target_ratio = 0.10  # 10% de notes golden
    desired_golden_count = total_notes * golden_target_ratio
    
    # Pour éviter d'avoir des golden en début de chanson, on force les notes normales
    # tant que moins de 10% des notes totales ont été traitées.
    if processed_count < total_notes * 0.10:
        return ":"
    
    # Si les 3 dernières notes traitées sont déjà golden, on force une note normale.
    if processed_count >= 3 and all(ly.note_type == "*" for ly in processed_notes[-3:]):
        return ":"
    
    # Calculer la probabilité d'attribuer une note golden
    remaining_notes = total_notes - processed_count
    # Si plus aucune note n'est à traiter, on renvoie normal.
    if remaining_notes <= 0:
        return ":"
    
    # On détermine le nombre de notes golden encore nécessaires pour atteindre le ratio souhaité.
    needed_golden = desired_golden_count - golden_count
    # Si le nombre nécessaire est négatif ou nul, on renforce l'utilisation de notes normales.
    if needed_golden <= 0:
        golden_probability = 0
    else:
        golden_probability = needed_golden / remaining_notes
    
    # Tirage aléatoire pondéré pour choisir entre normal (":") et golden ("*")
    if random.random() < golden_probability:
        return "*"
    else:
        return ":"
    
# =============================================================================
# Main Function Entry Point (Not Meant to be Run Directly)
# =============================================================================
if __name__ == "__main__":
    logger.error("This script is not meant to be run directly.")
    exit(1)
