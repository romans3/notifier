"""
helpermodule.py
Modulo di utilità centralizzato per tutto il sistema di notifiche.
"""

import re

# ---------------------------------------------------------
# STRING CLEANING
# ---------------------------------------------------------

def replace_regular(text: str, substitutions: list) -> str:
    """Applica sostituzioni regex in modo sicuro."""
    text = "" if text is None else str(text)
    for old, new in substitutions:
        regex = re.compile(old)
        text = re.sub(regex, new, text.strip())
    return text


def replace_language(lang: str) -> str:
    """Ritorna solo le prime due lettere della lingua."""
    if not lang:
        return "it"
    return str(lang)[:2]


def remove_tags(text: str) -> str:
    """Rimuove tag HTML."""
    text = "" if text is None else str(text)
    regex = re.compile(r"<.*?>")
    return re.sub(regex, "", text.strip())


def has_numbers(string: str):
    """Rileva numeri lunghi (anni, codici, ecc.)."""
    if not string:
        return False
    numbers = re.compile(r"\d{4,}|\d{3,}\.\d")
    return numbers.search(string)


# ---------------------------------------------------------
# SAFE ACCESSORS
# ---------------------------------------------------------

def safe_get(data: dict, key: str, default=None):
    """Accesso sicuro a un dict."""
    if isinstance(data, dict) and key in data:
        return data[key]
    return default


def safe_bool(value) -> bool:
    """Interpreta un valore come booleano."""
    if value is None:
        return False
    return str(value).lower() in ["true", "on", "yes", "1"]


def safe_list(value):
    """Ritorna sempre una lista."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return str(value).split(",")


# ---------------------------------------------------------
# DEVICE LIST NORMALIZATION
# ---------------------------------------------------------

def split_device_list(value):
    """Normalizza media_player in lista."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [v.strip() for v in str(value).split(",") if v.strip()]


# ---------------------------------------------------------
# GOOGLE PAYLOAD NORMALIZATION (ESTESA)
# ---------------------------------------------------------

def normalize_google_payload(google: dict, default_player: str, default_volume: float, tts_period_volume: float = None) -> dict:
    """
    Normalizza il payload Google per GH_Manager.
    Garantisce che tutti i campi siano presenti e validi.
    """

    if not isinstance(google, dict):
        google = {}

    # message
    message = safe_get(google, "message_tts") or safe_get(google, "message") or " "
    message = str(message).strip() or " "

    # language
    language = replace_language(safe_get(google, "language", "it"))

    # volume base
    if tts_period_volume is not None:
        volume = float(tts_period_volume)
    else:
        volume = float(safe_get(google, "volume", default_volume))

    # media player
    media_player = split_device_list(safe_get(google, "media_player", default_player))

    # audio / media_content_id
    media_id = safe_get(google, "media_content_id") or safe_get(google, "audio") or ""
    media_type = safe_get(google, "media_content_type", "music")

    # ---------------------------------------------------------
    # NUOVE OPZIONI AVANZATE (SOFT MODE)
    # ---------------------------------------------------------
    options = {
        "only_audio": safe_bool(google.get("only_audio")),
        "only_tts": safe_bool(google.get("only_tts")),
        "audio_first": safe_bool(google.get("audio_first", True)),
        "audio_volume": google.get("audio_volume"),
        "tts_volume": google.get("tts_volume"),
        "delay_after_audio": google.get("delay_after_audio", 0),
        "interrupt": safe_bool(google.get("interrupt", True)),
        "resume": safe_bool(google.get("resume", True)),
    }

    return {
        "message": message,
        "language": language,
        "volume": volume,
        "media_player": media_player,
        "media_content_id": media_id,
        "media_content_type": media_type,
        "options": options
    }
