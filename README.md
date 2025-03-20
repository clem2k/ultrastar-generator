# UltraStar Generator

UltraStar Generator is a modest little tool designed to convert your MP3 files into karaoke text files that are compatible with UltraStar and similar systems. It extracts song metadata if present and processes vocal recognition, voice/instrumental separation, pitch and timing. Some generated files can be enjoyed right away, while others provide a helpful starting point for a bit of manual editing. Give it a try and brighten up your karaoke nights!

> *"Rock your songs one beat at a time!"*

## Overview

UltraStar Generator takes an audio file (or a list of songs) and produces a corresponding UltraStar file with synchronized lyrics and notes. The project supports:
- **Batch Mode:** Process a list of songs defined in a JSON file.
- **Single MP3 Mode:** Process one MP3 file provided as a command-line argument.

The tool leverages state-of-the-art libraries for transcription, pitch detection, and audio processing to generate precise karaoke files with minimal fuss.

## Features

**IMPORTANT:**
Original MP3 files are moved into the ultrastar zip file.
If you want ultrastar to recognize file, just unzip into the data folder.

- **Automatic Transcription:** Uses transcription tools to extract lyrics and timing with high accuracy. WhisperX is used for transcription. See <https://github.com/m-bain/whisperX> for more information.
- **Pitch Extraction:** Analyzes audio with CREPE to map pitches for each word. See <https://pypi.org/project/crepe/> for more information.
- **Vocal Separation (Optional):** Uses Demucs to isolate vocals when enabled. See <https://pypi.org/project/demucs/> for more information.
- **Metadata Extraction:** Reads MP3 tags and fetches additional music info. User must have API key for TheAudioDB. See <https://www.theaudiodb.com/> for more information.
- **Cover & Video Handling:** Extracts embedded cover images.
- **UltraStar File Generation:** Produces UltraStar files complete with mandatory headers (#TITLE, #ARTIST, #BPM, #GAP) and correctly aligned notes. Rap notes are not supported yet.
- **Batch Processing:** Supports batch processing of multiple songs defined in a JSON file. JSON file must contain at least artist, title, file path and language fields.
- **Customizable Settings:** Configure output folder, image size, pitch analysis, and more using environment variables.
- **Debug Mode:** Enables detailed logging and retains temporary files for debugging purposes.

### Batch json format

```json
[
    {
        "artist": "Artist Name",
        "title": "Song Title",
        "language": "en",
        "file": "path/to/song.mp3"
    },
    {
        "artist": "Artist Name",
        "title": "Song Title",
        "language": "en",
        "file": "path/to/song.mp3"
    }
]
```
**Note: json file path must be songs.json**


## Requirements

Make sure you have Python installed along with the required packages. The project depends on:

- mutagen
- pillow
- python-dotenv
- torch, torchvision, torchaudio
- whisperx
- yt-dlp **OPTIONAL**
- ffmpeg, ffmpeg-python
- moviepy
- librosa
- numpy
- demucs
- pydub
- crepe
- tensorflow

Install them using:

```bash
pip install -r require.txt
```

*Note: Some components may require additional system dependencies (like FFmpeg).*

## Installation

1. **Clone the Repository:**

   ```bash
   git clone https://github.com/clem2k/ultrastar-generator.git
   ```

2. **Install Dependencies:**

   ```bash
   pip install -r require.txt
   ```

3. **Configure Environment Variables:**

   Create a `.env` file in the folder ultrastar-generator and set variables such as:
   
   ```env
   DEBUG=false
   LOG_FILE=./ultrastar_generator.log
   OUTPUT_FOLDER=./out
   CACHE_FOLDER=./cache
   MAX_WORDS_PER_PHRASE=7 
   GAP_THRESHOLD=4
   FRACTION=0.25
   IMAGE_WIDTH=1980
   IMAGE_HEIGHT=1980
   WHISPER_MODEL=large-v3-turbo
   WHISPER_ALIGN=WAV2VEC2_ASR_LARGE_LV60K_960H
   WHISPER_BATCH_SIZE=4
   WHISPER_DEVICE=cpu
   WHISPER_COMPUTE_TYPE=float32
   WHISPER_MIN_GAP_SILENCE=2
   SPLEETER=true
   SPLEETER_MODEL=htdemucs_ft
   MUSIC_API_KEY = MY_AUDIO_DB_API_KEY
   MUSIC_API_HOST = https://theaudiodb.com/api/v1/json/
   ```

   Adjust these settings as needed.

## Usage

UltraStar Generator offers three modes of operation:

1. **Batch Mode (Default):**  
   Create a `songs.json` file with an array of song objects containing at least `artist`, `title`, `language`, and `file` path. Then run:

   ```bash
   python main.py
   ```


2. **Single MP3 Mode:**  
   Process a single MP3 file by providing its full path:

   ```bash
   python main.py path/to/song.mp3
   ```

3. **Graphical interface:**  
   Run the GUI version of the program by running:

   ```bash
   python gui.py
   ```

The UltraStar file (.txt) is generated in the output folder along with any supplementary files (cover, background, etc.). Clean-up of temporary files is performed automatically (unless debug mode is active).

## How It Works

1. **Configuration:**  
   Settings are loaded from environment variables using `python-dotenv` (see [config.py](config.py)).

2. **Processing Pipeline:**  
   - The **main** function (in [main.py](main.py)) directs the execution flow based on the provided arguments.
   - The **mp3** module handles tag extraction, and audio conversion.
   - The **pitcher** module performs pitch analysis using CREPE.
   - The **ultrastar** module brings everything together by generating the UltraStar file with correct formatting and timing.
   - **Optional Vocal Separation:** Enable Spleeter/demucs for better vocal extraction.

3. **UltraStar File Generation:**  
   The final UltraStar file includes a header with metadata and the body with lyric notes calculated based on BPM and GAP values, following UltraStar synchronization rules.

## Legal Disclaimer

**IMPORTANT:**  
The user is solely responsible for ensuring that they possess the legal rights to convert or obtain the music. The user must have appropriate rights or permissions to use the music files processed by this application. Furthermore, the user agrees not to distribute, share, or publish any files generated by UltraStar Generator. Under no circumstances will the developer (clem2k) be held responsible for any misuse or unauthorized distribution of the generated files. If any dispute
arises, the user will be held solely responsible for any legal consequences.

## License

This project is licensed under an adapted MIT License. For more details, please see the LICENSE file.

*Based on the MIT License (source: [SPDX MIT](https://spdx.org/licenses/MIT.html)).*

## Contributing

Feel free to fork the repository and submit pull requests. Any improvements or bug fixes are welcome.

## Contact

For questions or feedback **clem2k** on github.
