import os
import json
import numpy as np
from pydub import AudioSegment  # Used to convert MP3 files to WAV format
import crepe  # CREPE is used for pitch estimation from audio signals
from scipy.io import wavfile  # Used to read WAV files
from config import CACHE_FOLDER

# =============================================================================
# Pitch Cache Creation Function
# =============================================================================
def _create_pitch_cache(mp3_file, cache_id):
    """
    Converts the given MP3 file into a WAV file, then estimates the pitch over the entire 
    duration using CREPE. The result is cached as a JSON file (averaging the pitch per second).
    
    UltraStar Rule Reference:
      - In UltraStar files, each note has an associated pitch (an integer representing the 
        number of half-tones relative to C4, where C4 is 0). This function is used to generate
        a pitch cache to later map words to a pitch.
    
    Args:
        mp3_file (str): Path to the original MP3 file.
        cache_id (str): A unique identifier for caching purposes.
        
    Returns:
        list: A list of dictionaries. Each dictionary represents one second of audio with keys:
              "start": beginning of the second (in seconds),
              "end": end of the second,
              "frequency": average frequency (in Hz) detected for that second.
    """
    # Build the path for the cache file for pitch information.
    crepe_cache_path = os.path.join(CACHE_FOLDER, f"crepe_{cache_id}.json")
    
    # If the cache file already exists, load and return it.
    if os.path.exists(crepe_cache_path):
        with open(crepe_cache_path, "r") as f:
            pitch_cache = json.load(f)
        return pitch_cache
    else:
        # Create a WAV version of the MP3. UltraStar timing and pitch processing typically 
        # require a WAV file for accurate analysis.
        wav_file = mp3_file.replace(".mp3", ".wav")
        audio_segment = AudioSegment.from_mp3(mp3_file)
        audio_segment.export(wav_file, format="wav")
        
        # Read the WAV file: sample_rate is in Hz, audio_data is a NumPy array.
        sample_rate, audio_data = wavfile.read(wav_file)
        # Use CREPE to predict pitch. The function returns time values, frequency values,
        # a confidence score, and an activation signal.
        time_vals, freq_vals, confidence, activation = crepe.predict(audio_data, sample_rate, viterbi=True)
        time_vals = np.array(time_vals)
        freq_vals = np.array(freq_vals)
        
        # Determine total duration in whole seconds (rounding up).
        total_seconds = int(np.ceil(time_vals[-1]))
        pitch_cache = []
        
        # For each second, compute the average frequency detected.
        for sec in range(total_seconds):
            indices = np.where((time_vals >= sec) & (time_vals < sec + 1))[0]
            if indices.size > 0:
                avg_freq = float(np.mean(freq_vals[indices]))
            else:
                avg_freq = 0.0
            pitch_cache.append({
                "start": sec,
                "end": sec + 1,
                "frequency": avg_freq
            })
        
        # Save the cache to a JSON file for later use.
        with open(crepe_cache_path, "w") as f:
            json.dump(pitch_cache, f)
        
        return pitch_cache

# =============================================================================
# Frequency to Ultrastar Pitch Conversion Function
# =============================================================================
def _convert_frequency_to_ultrastar(frequency):
    """
    Converts a given frequency in Hertz to the corresponding UltraStar pitch.
    
    UltraStar's pitch rule:
      - The pitch is represented as an integer number of semitones relative to C4 (which is 261.63 Hz).
      - The conversion formula is:
            ultrastar_pitch = round(12 * log2(frequency / 261.63))
      - The result is then clamped to the interval [-60, 67] to adhere to UltraStar specifications.
    
    Args:
        frequency (float): Frequency in Hertz.
        
    Returns:
        int: The corresponding UltraStar pitch.
    """
    if frequency <= 0:
        return 0
    ratio = frequency / 261.63  # Ratio relative to middle C (C4)
    semitones = 12 * np.log2(ratio)  # Calculate semitones difference using log base 2
    ultrastar_pitch = int(round(semitones))
    # Clamp the pitch to the allowed range as per UltraStar rules.
    ultrastar_pitch = max(-60, min(ultrastar_pitch, 67))
    return ultrastar_pitch

# =============================================================================
# Mapping Words to Pitch using the Pitch Cache
# =============================================================================
def _map_words_to_pitch(words, pitch_cache):
    """
    Associates each word (from transcription) with its corresponding UltraStar pitch using the pitch cache.
    
    For each word, it uses the integer part (second) of the word's start time to look up the average 
    frequency for that second in the pitch cache, then converts that frequency to an UltraStar pitch.
    
    UltraStar Rule Reference:
      - In UltraStar, the pitch assigned to a note is an integer representing the number of semitones 
        offset from C4. This function maps timing information to such a pitch.
    
    Args:
        words (list or dict): A list of word segments, each segment containing start time, end time, and text.
        pitch_cache (list): A list of dictionaries with keys "start", "end", and "frequency" (from _create_pitch_cache).
    
    Returns:
        list: A list of dictionaries where each dictionary includes the start time, end time, word text, 
              and its corresponding UltraStar pitch.
    """
    word_pitch_mapping = []
    
    # Check if words is a dict containing "srtWords"; otherwise, assume words is a list.
    if isinstance(words, dict) and "srtWords" in words:
        words_list = words["srtWords"]
    else:
        words_list = words
    
    # Build a lookup dictionary for pitch: key is the starting second, value is the frequency.
    pitch_lookup = {entry["start"]: entry["frequency"] for entry in pitch_cache}
    
    # For each word segment, determine the pitch.
    for word_entry in words_list:
        word_start = word_entry[0]
        word_end = word_entry[1]
        word_text = word_entry[2]
        # Use the integer part of the word's start time (in seconds) to look up frequency.
        second = int(word_start)
        frequency = pitch_lookup.get(second, 0.0)
        ultrastar_pitch = _convert_frequency_to_ultrastar(frequency)
        word_pitch_mapping.append({
            "start": word_start,
            "end": word_end,
            "word": word_text,
            "pitch": ultrastar_pitch
        })
    
    return word_pitch_mapping

# =============================================================================
# Main Pitch Processing Function
# =============================================================================
def process_pitch(words, mp3_file, cache_id):
    """
    Processes the audio file and associates each transcribed word with its UltraStar pitch.
    
    It first checks if a pitch cache already exists (cached mapping of words to pitch). If not,
    it generates the pitch cache using CREPE, maps words to pitch, caches the result, and returns it.
    
    UltraStar Rule Reference:
      - Each lyric note in an UltraStar file requires a pitch (as an integer offset from C4).
    
    Args:
        words: Transcribed words with timing information.
        mp3_file (str): Path to the mp3 file.
        cache_id (str): Unique identifier for caching.
        
    Returns:
        list: A list of dictionaries with each word's start, end, text, and associated UltraStar pitch.
    """
    pitch_cache_path = os.path.join(CACHE_FOLDER, f"pitch_{cache_id}.json")
    
    # Check if a pitch mapping cache already exists.
    if os.path.exists(pitch_cache_path):
        with open(pitch_cache_path, "r") as f:
            word_pitch_mapping = json.load(f)
        return word_pitch_mapping
    else:
        # Create the pitch cache (average frequency per second) using CREPE.
        pitch_cache = _create_pitch_cache(mp3_file, cache_id)
        # Map the transcribed words to their respective pitch values.
        word_pitch_mapping = _map_words_to_pitch(words, pitch_cache)
        
        # Save the word-to-pitch mapping to cache.
        with open(pitch_cache_path, "w") as f:
            json.dump(word_pitch_mapping, f, indent=2)
        
        return word_pitch_mapping
