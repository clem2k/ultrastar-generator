import os
import shlex
import subprocess
import json
import librosa
import requests
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, APIC, ID3NoHeaderError
from mutagen import File as MutagenFile
import demucs.separate
import whisperx
from config import CACHE_FOLDER, MUSIC_API_KEY, WHISPER_ALIGN, WHISPER_BATCH_SIZE, WHISPER_COMPUTE_TYPE, WHISPER_DEVICE, WHISPER_MODEL, logger, API_BASE, debug

# =============================================================================
# MP3 Tag and Image Handling Functions
# =============================================================================
def save_image(mp3_file: str, image_file: str) -> None:
    """
    Saves a cover image to the MP3 file's ID3 tags.
    
    UltraStar files often include a cover image (#COVER tag) which is embedded 
    into the MP3. This function reads the image data from the given image_file 
    and embeds it in the MP3 using the APIC frame.
    
    Args:
        mp3_file (str): Path to the mp3 file.
        image_file (str): Path to the image file (JPEG expected).
    """
    with open(image_file, 'rb') as img:
        img_data = img.read()
    try:
        audio = ID3(mp3_file)
    except ID3NoHeaderError:
        audio = ID3()
    # Add the APIC frame to embed the cover image.
    audio.add(APIC(
        encoding=3,       # 3 means UTF-8 encoding.
        mime='image/jpeg',# MIME type for JPEG images.
        type=3,           # Type 3 indicates the cover (front) image.
        desc='Cover',
        data=img_data
    ))
    audio.save(mp3_file)

def read_tags(mp3_path: str):
    """
    Reads MP3 tags using EasyID3.
    
    Returns a dictionary-like object containing the tags.
    """
    try:
        return EasyID3(mp3_path)
    except Exception:
        return EasyID3()

def save_tags(mp3_path: str, tags) -> None:
    """
    Saves the provided tags to the MP3 file.
    
    Args:
        mp3_path (str): Path to the mp3 file.
        tags: Tag object (e.g., EasyID3) to be saved.
    """
    tags.save(mp3_path)

def extract_image(mp3_path: str, image_path: str) -> bool:
    """
    Extracts the cover image from an MP3 file and saves it to image_path.
    
    It uses the Mutagen library to locate the APIC or PIC frame.
    
    UltraStar Rule Reference:
      - The cover image is used for the #COVER tag in UltraStar files.
    
    Args:
        mp3_path (str): Path to the mp3 file.
        image_path (str): Destination path for the extracted image.
    
    Returns:
        bool: True if an image was extracted and saved successfully; False otherwise.
    """
    try:
        audio = MutagenFile(mp3_path, easy=False)
        if audio is not None and audio.tags is not None:
            # Look for frames with ID 'APIC' (or legacy 'PIC') which contain image data.
            apic_frames = [tag for tag in audio.tags.values() if getattr(tag, 'FrameID', '') in ('APIC', 'PIC')]
            if apic_frames:
                with open(image_path, "wb") as f:
                    f.write(apic_frames[0].data)
                return True
        return False
    except Exception:
        return False

def fill_artist_title(mp3_file, artist, title):
    """
    Fill the 'artist' and 'title' tags of the given MP3 file.
    """
    try:
        audio = EasyID3(mp3_file)
    except ID3NoHeaderError:
        # If the file doesn't have ID3 tags, create them
        audio = EasyID3()
        audio.save(mp3_file)
        audio = EasyID3(mp3_file)
    
    # Update the tags
    audio['artist'] = artist
    audio['title'] = title
    audio.save(mp3_file)

# =============================================================================
# Audio Analysis Functions
# =============================================================================
def detect_bpm(mp3_path: str) -> int:
    """
    Detects the BPM (beats per minute) of the given mp3 file.
    
    Uses librosa to load the audio and perform beat tracking.
    
    UltraStar Rule Reference:
      - The BPM header (#BPM) is crucial for timing calculations in UltraStar files.
      - In older formats, BPM is often 4x the actual BPM.
    
    Args:
        mp3_path (str): Path to the mp3 file.
        
    Returns:
        int: The detected BPM (rounded to the nearest integer).
    """
    y, sr = librosa.load(mp3_path)
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)

    return int(tempo[0]) 

def get_duration(mp3_path: str = "") -> float:
    """
    Retrieves the duration of the mp3 file in seconds.
    
    Uses ffmpeg to probe the mp3 file and extract the 'duration' property.
    
    Args:
        mp3_path (str): Path to the mp3 file.
        
    Returns:
        float: Duration of the mp3 in seconds.
    """
    import ffmpeg
    if not mp3_path or not os.path.exists(mp3_path):
        return 0
    duration = ffmpeg.probe(mp3_path)['format']['duration']
    return float(duration)

def spleet(mp3_path: str, model: str = "htdemucs_ft", out_dir: str = None) -> str:
    """
    Separates vocals from the instrumental parts in the mp3 file using Demucs.
    
    UltraStar tools sometimes require separate vocal and instrumental files 
    (#VOCALS and #INSTRUMENTAL). This function calls Demucs to perform the separation.
    
    Args:
        mp3_path (str): Path to the original mp3 file.
        model (str): The Demucs model to use.
        out_dir (str): The directory where output files will be stored.
        
    Returns:
        str: Path to the output folder containing the separated stems.
    """
    if debug:
        logger.warning(f"model downgrade to 'htdemucs' for spleet")
        model = "htdemucs"
        
    if out_dir is None:
        out_dir = os.path.dirname(os.path.abspath(mp3_path))
    # Construct the command-line arguments for Demucs.
    # The command uses "--mp3" to output mp3 files, "--two-stems vocals" to separate vocals from non-vocals.
    demucs_cmd = f'--mp3 --two-stems vocals -n "{model}" --out "{out_dir}" "{mp3_path}"'
    logger.debug(f"Demucs command: {demucs_cmd}")
    args = shlex.split(demucs_cmd)
    logger.debug(f"Executing Demucs with arguments: {args}")
    demucs.separate.main(args)
    base_name = os.path.splitext(os.path.basename(mp3_path))[0]
    output_folder = os.path.join(out_dir, model, base_name)
    return output_folder

# =============================================================================
# Music API and Cache Functions
# =============================================================================
def _get_album_(album_id: str, id: str = "") -> dict:
    """
    Retrieves album information from an external API and caches the result.
    
    This function uses the album_id to query an API endpoint, caches the JSON 
    response locally, and returns a dictionary with album details such as title, cover, genre, etc.
    
    Args:
        album_id (str): Album identifier.
        id (str): An additional identifier for caching.
        
    Returns:
        dict: Album information, or None if not found.
    """
    if not album_id:
        return None
    os.makedirs(CACHE_FOLDER, exist_ok=True)
    cache_file = os.path.join(CACHE_FOLDER, f"album_{id}.json")
    if os.path.exists(cache_file):
        logger.debug(f"Loading album information from cache: {album_id}")
        with open(cache_file, "r", encoding="utf-8") as file:
            return json.load(file)
    logger.debug(f"Searching album information for ID {album_id}")
    url = f"{API_BASE}/album.php?m={album_id}"
    headers = {}
    response = requests.get(url, headers=headers)
    data = response.json()
    if data.get("album") is None:
        logger.debug(f"No album found for ID {album_id}.")
        return None
    album_data = data["album"][0]
    album_info = {
        "id": album_data.get("idAlbum"),
        "title": album_data.get("strAlbum"),
        "cover": album_data.get("strAlbumThumb"),
        "genre": album_data.get("strGenre"),
        "release_year": album_data.get("intYearReleased"),
        "language": album_data.get("strLocation")
    }
    with open(cache_file, "w", encoding="utf-8") as file:
        json.dump(album_info, file, ensure_ascii=False, indent=4)
    return album_info

def get_music_info(artist: str, title: str, id: str = "") -> dict:
    """
    Retrieves music information for a given song using an external API.
    
    It caches the result locally to avoid repeated API calls. Information such as 
    artist, title, album, genre, release year, and language is returned.
    
    Args:
        artist (str): Artist name.
        title (str): Song title.
        id (str): Identifier used for caching.
        
    Returns:
        dict: A dictionary containing music metadata.
    """
    if MUSIC_API_KEY == "" or MUSIC_API_KEY is None or MUSIC_API_KEY == "MY_AUDIO_DB_API_KEY":
        logger.info("No API key found. Please set MUSIC_API_KEY in the environment.")
        logger.info("To get an api key, visit https://www.theaudiodb.com/api_guide.php")
        return {
            "artist": artist,
            "title": title,
            "album": None,
            "genre": None,
            "year": None,
            "decade": None,
            "language": None,
            "cover": None,
            "description": None
        }
        
    os.makedirs(CACHE_FOLDER, exist_ok=True)
    cache_key = f"song_{id}"
    cache_file = os.path.join(CACHE_FOLDER, f"{cache_key}.json")
    if os.path.exists(cache_file):
        logger.debug(f"Loading music info from cache: {artist} - {title}")
        with open(cache_file, "r", encoding="utf-8") as file:
            return json.load(file)
    logger.debug(f"Searching music info for {artist} - {title}")
    url = f"{API_BASE}searchtrack.php?s={artist}&t={title}"
    headers = {}
    response = requests.get(url, headers=headers)
    data = response.json()
    result = {}
    if data.get("track") is None:
        logger.error(f"No music found for {artist} - {title}.")
        result = {
            "artist": artist,
            "title": title,
            "album": None,
            "genre": None,
            "year": None,
            "decade": None,
            "language": None,
            "cover": None,
            "description": None
        }
    else:
        track = data["track"][0]
        album = _get_album_(track.get("idAlbum"), id)
        logger.debug(f"Music found: {artist} - {title}")
        release_date = album.get("release_year") if album else None
        year = release_date[:4] if release_date else None
        decade = None
        if year:
            y = int(year)
            decade = y - (y % 10)
        result = {
            "artist": track.get("strArtist"),
            "title": track.get("strTrack"),
            "album": album.get("title") if album else None,
            "genre": album.get("genre") if album else None,
            "year": year,
            "decade": decade,
            "language": album.get("language") if album else None,
            "cover": album.get("cover") if album else None,
            "description": track.get("strDescriptionEN")
        }
    with open(cache_file, "w", encoding="utf-8") as file:
        json.dump(result, file, ensure_ascii=False, indent=4)
    return result

# =============================================================================
# Transcription Functions using WhisperX
# =============================================================================
def transcribe_audio(mp3_path, artist, title, id, model=WHISPER_MODEL, batch_size=WHISPER_BATCH_SIZE, align=WHISPER_ALIGN, language=None):
    """
    Transcribes the given audio file (mp3) into timed words using the WhisperX model.
    
    The transcription result includes word segments with start and end times and is cached.
    
    UltraStar Rule Reference:
      - The transcription provides the timing (in seconds) for each word,
        which is later converted into beat numbers for the UltraStar file.
    
    Args:
        mp3_path (str): Path to the mp3 file to transcribe.
        artist (str): Artist name.
        title (str): Song title.
        id (str): Unique identifier for caching.
        model (str): The WhisperX model to use.
        batch_size (int): Batch size for transcription.
        align (bool): Flag to perform alignment.
        language (str): Language code (if known).
        
    Returns:
        tuple: A tuple containing the list of word segments (srtWords) and the detected language.
    """
    os.makedirs(CACHE_FOLDER, exist_ok=True)
    cache_key = f"words_{id}"
    cache_file = os.path.join(CACHE_FOLDER, f"{cache_key}.json")
    if os.path.exists(cache_file):
        logger.debug(f"Chargement de la transcription depuis le cache : {artist} - {title}")
        with open(cache_file, "r", encoding="utf-8") as file:
            data = json.load(file)
            return data["srtWords"], data["detected_language"]
    try:
        logger.debug("Chargement du modèle WhisperX...")
        # Load the WhisperX model; if a language is specified, pass it as a parameter.
        if language:
            # switch model to large
            logger.debug("Chargement du modèle avec la langue spécifiée : " + language)
            model_instance = whisperx.load_model(model, device=WHISPER_DEVICE, compute_type=WHISPER_COMPUTE_TYPE, language=language)
        else:
            logger.debug("Chargement du modèle principal...")
            model_instance = whisperx.load_model(model, device=WHISPER_DEVICE, compute_type=WHISPER_COMPUTE_TYPE)
        
        logger.debug("Modèle principal chargé.")
        logger.debug("Chargement de l'audio : " + mp3_path)
        audio = whisperx.load_audio(mp3_path)
        logger.debug("Audio chargé.")
        result = model_instance.transcribe(audio, batch_size=batch_size)
        logger.debug("Transcription initiale réalisée.")
        detected_language = result["language"] if language is None else language
        # Load alignment model for WhisperX to get precise word timings.
        model_a, metadata = whisperx.load_align_model(language_code=detected_language, device=WHISPER_DEVICE)
        logger.debug("Modèle d'alignement chargé.")
        result_aligned = whisperx.align(result["segments"], model_a, metadata, audio, WHISPER_DEVICE, return_char_alignments=False)
        logger.debug("Alignement réalisé.")
        srtWords = []
        # Process each word segment, ensuring that start, end, and word are valid.
        for seg in result_aligned["word_segments"]:
            if seg.get("start") is None or seg.get("end") is None or seg.get("word") is None:
                logger.debug("Segment vide détecté : " + str(seg))
                continue
            word = str(seg["word"])
            if not word:
                logger.debug("Mot vide détecté : " + str(seg))
                continue
            start = seg["start"]
            end = seg["end"]
            logger.debug(f"Segment trouvé : {start} - {end} - {word}")
            srtWords.append([start, end, word])
        logger.debug("Segments de mots générés.")
        with open(cache_file, "w", encoding="utf-8") as file:
            json.dump({"srtWords": srtWords, "detected_language": detected_language}, file, ensure_ascii=False, indent=4)
        return srtWords, detected_language
    except Exception as e:
        logger.error("Erreur lors de la transcription avec WhisperX : " + str(e))
        logger.error("Modele : " + model)
        logger.error("Batch size : " + str(batch_size))
        logger.error("Alignement : " + str(align))
        logger.error("Langue : " + str(language))
        return [], None
        
