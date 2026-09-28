# Practice Picks

Guitar practice song recommender. Enter artists you like. Last.fm finds artists who sound similar, then Claude picks the songs from them that suit your level, with chords, capo, key, strumming pattern, and what each song teaches.

## Setup

```
pip install -r requirements.txt
copy .env.example .env
```

Fill in `.env`:
- `LASTFM_API_KEY`: free at https://www.last.fm/api/account/create (the callback URL field can be left blank)
- `ANTHROPIC_API_KEY` (optional, paid): from https://console.anthropic.com/settings/keys. Leave it blank for free mode, which shows the most popular songs from similar artists, without chords or level sorting.

## Run

```
python app.py
```

Open http://localhost:5000.

## How it works

1. `lastfm.py` gets each input artist's similar artists and ranks them. Artists similar to more than one of your picks rank higher. It then collects the top tracks of the top 10.
2. `recommender.py` sends those ~60 candidates to Claude (`claude-opus-5`, structured JSON output), which picks up to 12 that work for your level and orders them from easiest to hardest.
3. `public/index.html` shows the picks as cards, with links to find the tab and a video lesson.

With Anthropic credentials set, each search makes one Claude call, which costs a few cents. Without them, step 2 is skipped (free mode).

## Deploy to Vercel

Import the GitHub repo at https://vercel.com/new (Vercel detects the Flask app in `app.py`), and add `LASTFM_API_KEY` under Settings → Environment Variables.
