"""Works out a song's chords from a Songsterr tab.

Songsterr stores each guitar part as notes (string + fret per beat). For each
measure this adds up how long each pitch class sounds, then names the chord
whose tones best cover them, preferring the lowest note as the root. A chord
name the tab's author wrote on a beat always wins over detection.

Frets in Songsterr data are relative to the capo, so the chords come out as
the shapes you play with the capo on, which is what a chord sheet shows.
"""

import re

NOTE_NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
NATURALS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

# Suffix -> semitones above the root. Simpler chords come first and win ties.
CHORD_TYPES = [
    ("", (0, 4, 7)), ("m", (0, 3, 7)), ("5", (0, 7)),
    ("7", (0, 4, 7, 10)), ("maj7", (0, 4, 7, 11)), ("m7", (0, 3, 7, 10)),
    ("sus2", (0, 2, 7)), ("sus4", (0, 5, 7)), ("add9", (0, 2, 4, 7)),
    ("dim", (0, 3, 6)),
]
# Bonus for everyday chords, so a G with a passing A stays G rather than
# becoming Gadd9: sheets for practice should show the simple name.
COMMON = {"": 0.1, "m": 0.08, "5": 0.0, "7": 0.04}
MISSING_PENALTY = 0.5
BASS_BONUS = 0.1
# Share of a half-measure's notes that must belong to the last labelled chord
# for that label to carry over into an unlabelled half.
CARRY_FIT = 0.75


def _beat_pitches(beat, tuning):
    """MIDI pitches a beat plays, skipping rests and muted notes."""
    if beat.get("rest"):
        return []
    return [tuning[n["string"]] + n["fret"] for n in beat.get("notes", [])
            if "fret" in n and not n.get("rest") and not n.get("dead")
            and n.get("string", 99) < len(tuning)]


def _is_open_strum(beat):
    """A strum of 4+ open strings: usually the hand leaving one chord shape
    for the next, not part of either chord."""
    frets = [n.get("fret") for n in beat.get("notes", []) if "fret" in n]
    return len(frets) >= 4 and all(f == 0 for f in frets)


def _halves(measure):
    """Splits a measure's beats (first voice) into its first and second half
    by time, so a measure that changes chord midway gets both chords."""
    voices = measure.get("voices") or [{}]
    beats = voices[0].get("beats", [])
    total = sum(n / d for n, d in (b.get("duration", [1, 4]) for b in beats))
    first, second, elapsed = [], [], 0.0
    for beat in beats:
        (first if elapsed < total / 2 - 1e-9 else second).append(beat)
        num, den = beat.get("duration", [1, 4])
        elapsed += num / den
    return first, second


def _pitch_weights(beats, tuning):
    """{pitch class: total sounding time} and the bass note (the lowest note
    of the first sounding beat)."""
    beats = [b for b in beats if _beat_pitches(b, tuning)]
    if not all(_is_open_strum(b) for b in beats):
        beats = [b for b in beats if not _is_open_strum(b)]
    weights, bass = {}, None
    for beat in beats:
        pitches = _beat_pitches(beat, tuning)
        num, den = beat.get("duration", [1, 4])
        for pitch in pitches:
            weights[pitch % 12] = weights.get(pitch % 12, 0) + num / den
        if bass is None:
            bass = min(pitches)
    return weights, bass


def name_chord(weights, bass=None):
    """Best chord name for {pitch class: weight}, or None if too few notes."""
    total = sum(weights.values())
    if total == 0 or len(weights) < 2:
        return None
    best, best_score = None, 0.0
    for root in range(12):
        for suffix, intervals in CHORD_TYPES:
            tones = {(root + i) % 12 for i in intervals}
            if root not in weights:
                continue
            covered = sum(w for pc, w in weights.items() if pc in tones) / total
            missing = sum(1 for t in tones if t not in weights) / len(tones)
            score = covered - MISSING_PENALTY * missing + COMMON.get(suffix, 0)
            if bass is not None and root == bass % 12:
                score += BASS_BONUS
            if score > best_score:
                best, best_score = NOTE_NAMES[root] + suffix, score
    return best if best_score >= 0.6 else None


def chord_tones(name):
    """Pitch classes of a chord name like 'Em7' or 'D/A', or None if unknown.
    Unknown suffixes fall back to the major or minor triad."""
    match = re.match(r"([A-G])([#b]?)([^/]*)", name or "")
    if not match:
        return None
    letter, accidental, suffix = match.groups()
    root = (NATURALS[letter] + {"#": 1, "b": -1}.get(accidental, 0)) % 12
    intervals = dict(CHORD_TYPES).get(suffix)
    if intervals is None:
        intervals = (0, 3, 7) if suffix.startswith("m") and not suffix.startswith("maj") else (0, 4, 7)
    return {(root + i) % 12 for i in intervals}


def labels(beats):
    """Chord names the tab's author wrote on these beats, with ♭/♯ spelled b/#."""
    return [b["chord"]["text"].strip().replace("♭", "b").replace("♯", "#")
            for b in beats if (b.get("chord") or {}).get("text", "").strip()]


def _half_chord(beats, tuning, carried):
    """Chord for half a measure: the author's label if the half has one,
    else the last label if the notes still fit it, else detected."""
    written = labels(beats)
    if written:
        return written[0]
        return labels[0]
    weights, bass = _pitch_weights(beats, tuning)
    if carried and weights:
        tones = chord_tones(carried) or set()
        fit = sum(w for pc, w in weights.items() if pc in tones) / sum(weights.values())
        if fit >= CARRY_FIT:
            return carried
    return name_chord(weights, bass)


def measure_chords(part):
    """A list of chord names (0-2) per measure of a Songsterr part.

    An author's label also covers the halves after it, the way chord sheets
    work, as long as the notes there still fit it.
    """
    tuning = part.get("tuning") or [64, 59, 55, 50, 45, 40]
    result, carried = [], None
    for measure in part.get("measures", []):
        chords = []
        for beats in _halves(measure):
            chord = _half_chord(beats, tuning, carried)
            written = labels(beats)
            if written:
                carried = written[-1]
            if chord and (not chords or chords[-1] != chord):
                chords.append(chord)
        result.append(chords)
    return result


# Shapes a beginner can play without barring.
OPEN_SHAPES = {
    "C", "D", "E", "G", "A", "Am", "Em", "Dm",
    "C7", "D7", "E7", "G7", "A7", "B7", "Am7", "Em7", "Dm7",
    "Cmaj7", "Dmaj7", "Fmaj7", "Gmaj7", "Amaj7",
    "Dsus2", "Dsus4", "Asus2", "Asus4", "Esus4", "Cadd9",
    "D5", "E5", "G5", "A5",
}


def transpose(name, semitones):
    """Moves a chord name by semitones, e.g. ('Eb/G', -1) -> 'D/F#'. Also
    re-spells roots consistently (A# -> Bb). Unparseable names pass through."""
    def move(note):
        match = re.fullmatch(r"([A-G])([#b]?)(.*)", note)
        if not match:
            return note
        letter, accidental, rest = match.groups()
        pc = NATURALS[letter] + {"#": 1, "b": -1}.get(accidental, 0) + semitones
        return NOTE_NAMES[pc % 12] + rest
    head, _, bass = name.partition("/")
    return move(head) + ("/" + move(bass) if bass else "")


def with_easiest_capo(sheet, capo=0, max_capo=7):
    """Re-voices a chord sheet at the capo position (from `capo` up to
    `max_capo`) where the most of its chords are open shapes. Ties go to
    the lower capo. Adds "capo" and "capo_suggested" to the sheet."""
    def open_count(shift):
        return sum(transpose(ch, -shift).split("/")[0] in OPEN_SHAPES for ch in sheet["chords"])

    shift = max(range(0, max_capo - capo + 1), key=lambda s: (open_count(s), -s))
    if open_count(shift) <= open_count(0):
        shift = 0
    return {
        "chords": [transpose(ch, -shift) for ch in sheet["chords"]],
        "sections": [dict(s, chords=[transpose(ch, -shift) for ch in s["chords"]])
                     for s in sheet["sections"]],
        "capo": capo + shift,
        "capo_suggested": shift > 0,
    }


def _repeats(chords):
    """['G', 'D', 'G', 'D'] -> (['G', 'D'], 2): the shortest pattern the list
    is an exact repeat of. A list that doesn't repeat comes back as (chords, 1)."""
    for size in range(1, len(chords) // 2 + 1):
        pattern = chords[:size]
        if len(chords) % size == 0 and all(
                chord == pattern[i % size] for i, chord in enumerate(chords)):
            return pattern, len(chords) // size
    return chords, 1


def chord_sheet(part):
    """Groups a part's chords by its section markers.

    Returns {"chords": [every chord, in order of first use],
             "sections": [{"name": "Verse 1", "chords": ["C", "G"], "times": 2}]}.
    Repeated chords in a row are merged, a progression played several times
    over is shown once with `times`, and sections with the same name and
    progression as an earlier one are skipped.
    """
    per_measure = measure_chords(part)
    has_markers = any(m.get("marker") for m in part.get("measures", []))
    sections, current = [], {"name": "Intro" if has_markers else "Whole song", "chords": []}
    for measure, chords in zip(part.get("measures", []), per_measure):
        marker = (measure.get("marker") or {}).get("text")
        if marker:
            if current["chords"]:
                sections.append(current)
            current = {"name": marker.strip(), "chords": []}
        for chord in chords:
            if not current["chords"] or current["chords"][-1] != chord:
                current["chords"].append(chord)
    if current["chords"]:
        sections.append(current)

    seen, unique_sections = set(), []
    for section in sections:
        key = (section["name"].rstrip(" 0123456789"), tuple(section["chords"]))
        if key not in seen:
            seen.add(key)
            pattern, times = _repeats(section["chords"])
            unique_sections.append({"name": section["name"], "chords": pattern, "times": times})

    used = []
    for chords in per_measure:
        for chord in chords:
            if chord not in used:
                used.append(chord)
    return {"chords": used, "sections": unique_sections}
