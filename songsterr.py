"""Songsterr lookup: finds a song's guitar tab, its difficulty and tuning.

Uses the JSON search endpoint behind songsterr.com. It's free and needs no
key, but it's unofficial, so a failed lookup just means "no tab found".
"""

import re
from concurrent.futures import ThreadPoolExecutor

import requests

SEARCH_URL = "https://www.songsterr.com/api/songs"

# Songsterr rates each track's difficulty; observed range is about 1 (easy
# strumming) to 8 (shred). These bands overlap so edge songs fit either level.
LEVEL_DIFFICULTY = {"beginner": (1, 3), "intermediate": (3, 5), "advanced": (5, 99)}

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
NAMED_TUNINGS = {
    (64, 59, 55, 50, 45, 40): "Standard",
    (63, 58, 54, 49, 44, 39): "Half step down",
    (62, 57, 53, 48, 43, 38): "Whole step down",
    (64, 59, 55, 50, 45, 38): "Drop D",
    (62, 57, 55, 50, 45, 38): "DADGAD",
}


def _norm(text):
    return re.sub(r"[^a-z0-9]", "", text.lower())


def tuning_name(midi_notes):
    """[64, 59, 55, 50, 45, 40] (high to low) -> 'Standard'; unnamed -> 'D A D G B E'."""
    if tuple(midi_notes) in NAMED_TUNINGS:
        return NAMED_TUNINGS[tuple(midi_notes)]
    return " ".join(NOTE_NAMES[n % 12] for n in reversed(midi_notes))


def _match(results, artist, title):
    """Best result by this artist whose title matches; exact titles beat
    variants like '(Acoustic)', then more-viewed guitar parts win."""
    want_artist, want_title = _norm(artist), _norm(title)
    best, best_key = None, None
    for song in results:
        if song.get("isJunk"):
            continue
        got_artist, got_title = _norm(song["artist"]), _norm(song["title"])
        if not (want_artist in got_artist or got_artist in want_artist):
            continue
        if not got_title.startswith(want_title):
            continue
        guitars = [t for t in song["tracks"] if "guitar" in t["instrument"].lower()
                   and "bass" not in t["instrument"].lower()]
        if not guitars:
            continue
        track = max(guitars, key=lambda t: t.get("views", 0))
        key = (got_title == want_title, track.get("views", 0))
        if best_key is None or key > best_key:
            best, best_key = (song, track), key
    return best


def find_tab(session, artist, title):
    """Returns {url, difficulty, tuning, instrument, has_chords} or None."""
    try:
        resp = session.get(SEARCH_URL, params={"pattern": f"{artist} {title}", "size": 8},
                           timeout=10)
        resp.raise_for_status()
        found = _match(resp.json(), artist, title)
    except (requests.RequestException, ValueError, KeyError):
        return None
    if not found:
        return None
    song, track = found
    slug = re.sub(r"[^a-z0-9]+", "-", f"{song['artist']} {song['title']}".lower()).strip("-")
    return {
        "url": f"https://www.songsterr.com/a/wsa/{slug}-tab-s{song['songId']}",
        "difficulty": track.get("difficulty"),
        "tuning": tuning_name(track["tuning"]) if track.get("tuning") else None,
        "instrument": track["instrument"],
        "has_chords": bool(song.get("hasChords")),
    }


def add_tabs(songs, workers=3):
    """Sets song["tab"] (dict or None) on each song. Keep `workers` low:
    Songsterr drops connections when too many open at once."""
    session = requests.Session()
    with ThreadPoolExecutor(workers) as pool:
        tabs = pool.map(lambda s: find_tab(session, s["artist"], s["title"]), songs)
        for song, tab in zip(songs, tabs):
            song["tab"] = tab
    return songs


def fits_level(song, level):
    low, high = LEVEL_DIFFICULTY[level]
    tab = song.get("tab")
    return bool(tab and tab["difficulty"] is not None and low <= tab["difficulty"] <= high)
