"""Guitar practice recommender web app. Run: python app.py, then open http://localhost:5000"""

import os

import anthropic
from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory

from lastfm import Lastfm, gather_candidates, spread_picks
from recommender import LEVELS, RecommendError, pick_songs

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
        return jsonify(songs=spread_picks(candidates), not_found=not_found, detailed=False)

    liked = [a for a in artists if a not in not_found]
    try:
        songs = pick_songs(anthropic.Anthropic(), liked, candidates, level)
    except RecommendError as e:
        return jsonify(error=str(e)), 502

    return jsonify(songs=songs, not_found=not_found, detailed=True)


def claude_configured():
    """Claude picks and chords are optional; without credentials the app
    falls back to Last.fm's most popular songs (free)."""
    return any(os.environ.get(v) for v in
               ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_FEDERATION_RULE_ID"))


if __name__ == "__main__":
    app.run(debug=True)
