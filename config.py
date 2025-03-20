import os
from dotenv import load_dotenv
import logging

# Load environment variables from the .env file
load_dotenv()

# global configuration variables
APP_TITLE = os.getenv("APP_TITLE", "UltraStar Generator")
APP_VERSION = os.getenv("APP_VERSION", "v1.0.0")
OUTPUT_FOLDER = os.getenv("OUTPUT_FOLDER", "output")
CACHE_FOLDER = os.getenv("CACHE_FOLDER", "cache")

# Retrieve configuration variables
IMG_TARGET_WIDTH = int(os.getenv("IMAGE_WIDTH", "1024"))
IMG_TARGET_HEIGHT = int(os.getenv("IMAGE_HEIGHT", "768"))

DEBUG_STR = os.getenv("DEBUG", "true").lower()
debug = DEBUG_STR in ("true", "1", "yes")
LOG_FILE = os.getenv("LOG_FILE", "ultrastar_generator.log")

# Configuration for WhisperX
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "large-v3-turbo")
WHISPER_ALIGN = os.getenv("WHISPER_ALIGN", "WAV2VEC2_ASR_LARGE_LV60K_960H")
WHISPER_BATCH_SIZE = int(os.getenv("WHISPER_BATCH_SIZE", "4"))
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cuda")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "float32")
WHISPER_MIN_GAP_SILENCE = float(os.getenv("WHISPER_MIN_GAP_SILENCE", "0.5"))

# Configuration for Spleeter
SPLEETER = os.getenv("SPLEETER", "false").lower() == "true"
SPLEETER_MODEL = os.getenv("SPLEETER_MODEL", "htdemucs")

# Retrieve environment variables for music API configuration
MUSIC_API_HOST = os.environ.get("MUSIC_API_HOST", "").strip()
MUSIC_API_KEY = os.environ.get("MUSIC_API_KEY", "").strip()
MUSIC_GENRE_PICTURE = os.environ.get("MUSIC_GENRE_PICTURE", "")
# Build the base URL for the API (example: "https://api.example.com/API_KEY/")
API_BASE = MUSIC_API_HOST + MUSIC_API_KEY + "/"

# Define the maximum number of words per phrase before forcing an automatic pause
MAX_WORDS_PER_PHRASE = os.environ.get("MAX_WORDS_PER_PHRASE", 7)
# Define the minimum gap (in beats) between the end of one phrase and the start of the next
GAP_THRESHOLD = os.environ.get("GAP_THRESHOLD", 4)
# Define the fraction of the gap where the end-of-phrase marker will be inserted (25% into the gap)
FRACTION = os.environ.get("FRACTION", 0.25)


class ColoredFormatter(logging.Formatter):
    """
    Custom formatter to add ANSI colors to log messages.
    - INFO messages are displayed in green.
    - WARNING messages are displayed in yellow.
    - ERROR messages are displayed in red.
    Other levels remain unchanged.
    """
    COLOR_RESET = "\033[0m"
    COLOR_INFO =  "\033[34m"   # blue
    COLOR_WARNING = "\033[33m"  # yellow
    COLOR_ERROR = "\033[31m"    # red
    COLOR_DEBUG = "\033[32m"     # green

    def format(self, record):
        message = super().format(record)
        if record.levelno == logging.INFO:
            message = f"{self.COLOR_INFO}{message}{self.COLOR_RESET}"
        elif record.levelno == logging.WARNING:
            message = f"{self.COLOR_WARNING}{message}{self.COLOR_RESET}"
        elif record.levelno == logging.ERROR:
            message = f"{self.COLOR_ERROR}{message}{self.COLOR_RESET}"
        elif record.levelno == logging.DEBUG:
            message = f"{self.COLOR_DEBUG}{message}{self.COLOR_RESET}"
        return message

# Créez un logger dédié
logger = logging.getLogger("ultrastar_generator")
if debug:
    logger.setLevel(logging.DEBUG)
else:
    logger.setLevel(logging.ERROR)
    
logger.propagate = False  # Empêche la propagation vers le logger racine

# Création d'un handler pour la console
console_handler = logging.StreamHandler()
formatter = ColoredFormatter("[%(levelname)s] %(message)s")
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# Création d'un handler pour le fichier de log
file_handler = logging.FileHandler(LOG_FILE)
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
logger.addHandler(file_handler)


