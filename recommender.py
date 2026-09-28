"""Uses Claude to pick the candidate songs that suit guitar practice at a given level."""

import json

import anthropic

MODEL = "claude-opus-5"

LEVELS = {
    "beginner": "open chords (G, C, D, Em, Am, E, A, Dm), capo allowed, simple "
                "strumming; at most one barre or 7th chord per song",
    "intermediate": "barre chords, 7ths/maj7/9ths, basic fingerpicking and "
                    "syncopated strumming",
    "advanced": "jazz/neo-soul voicings, extended chords, fast changes, "
                "funk rhythm, riffs and solos",
}

SYSTEM = """You help guitarists find songs to practice. You get a list of \
candidate songs (from artists similar to ones the player likes) and the \
player's skill level. Pick the songs that are the best practice material \
for that level and that work on a single acoustic or electric guitar.

For each pick, give the chords as commonly played in guitar arrangements \
(with a capo if that's how most people play it, so a beginner avoids \
barre chords), the key, a strumming or picking pattern in simple \
notation like "D - D U - U D U", and the one skill the song teaches. \
Only include songs you actually know; skip any you are unsure about \
rather than guessing chords. Order the list from easiest to hardest."""

SONG_SCHEMA = {
    "type": "object",
    "properties": {
        "songs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "artist": {"type": "string"},
                    "difficulty": {
                        "type": "integer",
                        "description": "1 (first-week beginner) to 5 (advanced)",
                    },
                    "key": {"type": "string"},
                    "capo": {"type": "integer", "description": "0 for no capo"},
                    "chords": {"type": "array", "items": {"type": "string"}},
                    "pattern": {"type": "string"},
                    "skill": {
                        "type": "string",
                        "description": "The main thing this song trains, e.g. 'G to C changes'",
                    },
                    "why": {
                        "type": "string",
                        "description": "One sentence on why it fits the player's taste and level",
                    },
                },
                "required": ["title", "artist", "difficulty", "key", "capo",
                             "chords", "pattern", "skill", "why"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["songs"],
    "additionalProperties": False,
}


class RecommendError(Exception):
    pass


def pick_songs(client, liked, candidates, level, count=12):
    lines = "\n".join(
        f"- {c['title']} by {c['artist']} (similar to {', '.join(c['similar_to'])})"
        for c in candidates
    )
    prompt = (f"Artists I like: {', '.join(liked)}\n"
              f"My level: {level} ({LEVELS[level]})\n\n"
              f"Candidate songs:\n{lines}\n\n"
              f"Pick up to {count} songs for me to practice.")

    try:
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            thinking={"type": "adaptive"},
            output_config={
                "effort": "medium",
                "format": {"type": "json_schema", "schema": SONG_SCHEMA},
            },
            system=SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.AuthenticationError:
        raise RecommendError("Anthropic API key is invalid. Check ANTHROPIC_API_KEY in .env.")
    except anthropic.RateLimitError:
        raise RecommendError("Rate limited by the Anthropic API. Try again in a minute.")
    except anthropic.APIConnectionError:
        raise RecommendError("Couldn't reach the Anthropic API. Check your connection.")
    except anthropic.APIStatusError as e:
        raise RecommendError(f"Anthropic API error ({e.status_code}): {e.message}")

    if response.stop_reason == "refusal":
        raise RecommendError("Claude declined this request.")
    if response.stop_reason == "max_tokens":
        raise RecommendError("Response was cut off. Try fewer artists.")

    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text)["songs"]
