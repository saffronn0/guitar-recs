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
3. `songsterr.py` looks up each song on Songsterr (free, no key) for a direct tab link, the difficulty of its most-played guitar part, and its tuning. In free mode, that difficulty is what matches songs to your level.
4. `chords.py` turns that tab into a chord sheet, section by section. It uses the chord names the tab's author wrote where there are any, and otherwise works them out from the notes in each half-measure. Checked against 550 author-labelled chords from 9 songs, it gets the chord right 92% of the time, ignoring extensions like 7ths (81% exactly). It then suggests the capo that turns the most chords into open shapes, e.g. This Love as Am, Dm7, G7, C with capo 3.
5. `public/index.html` shows the picks as cards, with links to the Songsterr tab, a chord sheet search and a video lesson.

Songsterr's search endpoint is unofficial, so if it changes or is down, songs just show without tab info.

With Anthropic credentials set, each search makes one Claude call, which costs a few cents. Without them, step 2 is skipped (free mode).

## Deploy to Vercel

Import the GitHub repo at https://vercel.com/new (Vercel detects the Flask app in `app.py`), and add `LASTFM_API_KEY` under Settings → Environment Variables.
