"""Guitar practice recommender web app. Run: python app.py, then open http://localhost:5000"""

import os

import anthropic
from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory

from lastfm import Lastfm, gather_candidates, spread_picks
from recommender import LEVELS, RecommendError, pick_songs
from songsterr import LEVEL_DIFFICULTY, add_chord_sheets, add_tabs, fits_level

load_dotenv()

app = Flask(__name__, static_folder="public")


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.post("/api/recommend")
def recommend():
    body = request.get_json(silent=True) or {}
    artists = [a.strip() for a in body.get("artists", []) if a.strip()][:5]
    level = body.get("level", "beginner")
    if not artists:
        return jsonify(error="Add at least one artist."), 400
    if level not in LEVELS:
        return jsonify(error=f"Unknown level: {level}"), 400

    lastfm_key = os.environ.get("LASTFM_API_KEY")
    if not lastfm_key:
        return jsonify(error="LASTFM_API_KEY is not set. Add it to .env (see README)."), 500

    candidates, not_found = gather_candidates(
        Lastfm(lastfm_key), artists, include_own=bool(body.get("include_own")))
    if not candidates:
        return jsonify(error="Last.fm couldn't find those artists. Check the spelling."), 404

    if not claude_configured():
        return jsonify(songs=free_picks(candidates, level), not_found=not_found, detailed=False)

    liked = [a for a in artists if a not in not_found]
    try:
        songs = pick_songs(anthropic.Anthropic(), liked, candidates, level)
    except RecommendError as e:
        return jsonify(error=str(e)), 502

    return jsonify(songs=add_chord_sheets(add_tabs(songs)), not_found=not_found, detailed=True)


def free_picks(candidates, level, count=12, batch=6):
    """Without Claude: songs whose Songsterr tab suits the level and has
    readable chords, spread across artists, easiest first. If short, adds
    the songs closest to the level after them."""
    # The same Songsterr song can come from two Last.fm artists (Silk Sonic and
    # Bruno Mars both list Leave The Door Open), so keep one of each.
    tabbed, seen = [], set()
    for c in add_tabs(candidates):
        if c["tab"] and c["tab"]["song_id"] not in seen:
            seen.add(c["tab"]["song_id"])
            tabbed.append(c)
    in_level = spread_picks([c for c in tabbed if fits_level(c, level)], len(tabbed))
    low, high = LEVEL_DIFFICULTY[level]
    rest = sorted((c for c in tabbed if c not in in_level),
                  key=lambda c: max(low - (c["tab"]["difficulty"] or 0),
                                    (c["tab"]["difficulty"] or 0) - high))
    # Load chords a batch at a time, best candidates first, until there are enough.
    queue, picks = in_level + rest, []
    while queue and len(picks) < count:
        chunk, queue = queue[:batch], queue[batch:]
        picks += [c for c in add_chord_sheets(chunk) if c["sheet"]]
    return sorted(picks[:count],
                  key=lambda c: (not fits_level(c, level), c["tab"]["difficulty"] or 0))


def claude_configured():
    """Claude picks and chords are optional; without credentials the app
    falls back to Last.fm + Songsterr (free)."""
    return any(os.environ.get(v) for v in
               ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_FEDERATION_RULE_ID"))


if __name__ == "__main__":
    app.run(debug=True)
