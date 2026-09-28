"""Last.fm client: finds artists similar to the ones you like and their top tracks."""

import requests

API_URL = "https://ws.audioscrobbler.com/2.0/"


class LastfmError(Exception):
    pass


class Lastfm:
    def __init__(self, api_key):
        self.api_key = api_key
        self.session = requests.Session()

    def _get(self, method, **params):
        resp = self.session.get(
            API_URL,
            params={"method": method, "api_key": self.api_key, "format": "json",
                    "autocorrect": 1, **params},
            timeout=15,
        )
        data = resp.json()
        if "error" in data:
            raise LastfmError(data.get("message", f"Last.fm error {data['error']}"))
        return data

    def similar_artists(self, artist, limit=15):
        """Returns [(name, match 0..1)] for artists similar to `artist`."""
        data = self._get("artist.getsimilar", artist=artist, limit=limit)
        return [(a["name"], float(a["match"]))
                for a in data["similarartists"]["artist"]]

    def top_tracks(self, artist, limit=6):
        data = self._get("artist.gettoptracks", artist=artist, limit=limit)
        return [t["name"] for t in data["toptracks"]["track"]]


def rank_similar(similar_by_input, exclude, max_artists=10):
    """Merges each input artist's similar-artist list into one ranking.

    Artists similar to several of your inputs rank above artists similar to
    just one; ties break on summed match score. Returns
    [(name, [input artists it's similar to])].
    """
    excluded = {name.lower() for name in exclude}
    scores = {}
    for source, similar in similar_by_input.items():
        for name, match in similar:
            if name.lower() in excluded:
                continue
            entry = scores.setdefault(name, {"score": 0.0, "sources": []})
            entry["score"] += match
            entry["sources"].append(source)
    ranked = sorted(scores.items(),
                    key=lambda kv: (len(kv[1]["sources"]), kv[1]["score"]),
                    reverse=True)
    return [(name, entry["sources"]) for name, entry in ranked[:max_artists]]


def gather_candidates(client, artists, include_own=False,
                      max_artists=10, tracks_per_artist=6):
    """Returns candidate songs as dicts: {title, artist, similar_to}.

    Unknown input artists are skipped and reported back in `not_found`.
    """
    similar_by_input, not_found = {}, []
    for artist in artists:
        try:
            similar_by_input[artist] = client.similar_artists(artist)
        except LastfmError:
            not_found.append(artist)

    candidates = []
    if include_own:
        for artist in similar_by_input:
            for title in client.top_tracks(artist, tracks_per_artist):
                candidates.append({"title": title, "artist": artist,
                                   "similar_to": [artist]})

    for name, sources in rank_similar(similar_by_input, artists, max_artists):
        try:
            titles = client.top_tracks(name, tracks_per_artist)
        except LastfmError:
            continue
        for title in titles:
            candidates.append({"title": title, "artist": name,
                               "similar_to": sources})
    return candidates, not_found


def spread_picks(candidates, count=12):
    """Picks `count` songs round-robin across artists (each artist's top song
    first), so no single artist fills the list. Keeps artist ranking order."""
    by_artist = {}
    for c in candidates:
        by_artist.setdefault(c["artist"], []).append(c)
    queues = list(by_artist.values())
    picks = []
    while queues and len(picks) < count:
        for queue in queues:
            if len(picks) < count:
                picks.append(queue.pop(0))
        queues = [q for q in queues if q]
    return picks
