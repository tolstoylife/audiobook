#!/usr/bin/env python3
"""
Build the mastered, per-section read-along audio of "A Great Iniquity".

Pipeline and findings: README.md (this folder) and ../../docs/audiobook-pipeline.md.
  - voice bm_daniel, synthesized PER SENTENCE via `synthesize`
    (NOT `infinite` — its streaming step mangled long-sentence endings; an A/B
     on ch02 confirmed `synthesize` lands sentence endings cleanly)
  - sentence / paragraph / chapter pauses, mastered, one .m4a per section
    (no whole-book M4B mux — see the ponytail note above main())

Reads segments.<version>.json from the reader bundle (SEG_JSON env var, or
the-great-sin's segments.en-1905.json by default). Resumable: re-running
skips sentences whose WAV already exists.

  python3 build_audiobook.py [voice]
Requires: kokoro-tts-tool, ffmpeg, ffprobe.
"""
import subprocess, os, re, sys, json, wave
import numpy as np

ARGS     = [a for a in sys.argv[1:] if not a.startswith("--")]
VOICE    = ARGS[0] if ARGS else "bm_daniel"
SENT_GAP = 0.45   # pause between sentences within a paragraph
PARA_GAP = 0.85   # pause between paragraphs (most end on a George quote — Johan wanted longer)
CHAP_GAP = 2.0    # pause between Parts (research: section breaks ~2–2.5s; clearly > paragraph)
# Kokoro bakes a fixed ~0.14s pause at commas/dashes inside a sentence and exposes
# no dial for it. To lengthen those we post-process each synth wav: find the quiet
# runs *inside* the sentence and splice a little more silence into each (Option B).
PAUSE_PAD = 0.02  # extra silence added at each internal comma/clause pause (s) — tune by ear
MIN_INTERNAL_SIL = 0.06  # a quiet run this long counts as a pause worth padding (s)
SIL_DBFS  = -35.0 # amplitude below this (rel. int16 full scale) is "silence" (measured: stable band)
BITRATE  = "128k"
SR       = 24000  # Kokoro's native rate
CACHE    = f"wav_full_{VOICE}"         # base; main() appends /<work> — raw synth wavs, never mutated
PADDED   = f"wav_full_{VOICE}_pad"     # base; main() appends /<work> — padded clips + scratch (regenerable)
MASTER   = "highpass=f=70,deesser=i=0.4,loudnorm=I=-19:TP=-2:LRA=7"

# The text-shaping rules (flow fixes, pronunciation respellings, sentence split,
# spoken headers) used to live here. They now live in reader/speech.py + reader/
# segment.py so the segmenter owns them and segments.json carries final speech text.
# This build reads segments.json and only does audio: synth + master + time.

# ── Pure clip + timeline logic (the only arithmetic worth a test) ──────────────
def iter_clips(seg):
    """Flatten one version's segments.json into ordered synth clips.
    Heading first per section, then each sentence. gap_after = PARA_GAP for the
    last sentence in a paragraph, else SENT_GAP. The CHAP_GAP between sections is
    silence the builder inserts between section files, not a clip's gap."""
    clips = []
    for sec in seg["sections"]:
        clips.append({"id": sec["id"], "speech": sec["headingSpeech"],
                      "gap_after": SENT_GAP, "section": sec["id"],
                      "is_section_start": True})
        for para in sec["paragraphs"]:
            sents = para["sentences"]
            for i, s in enumerate(sents):
                clips.append({"id": s["id"], "speech": s["speech"],
                              "gap_after": PARA_GAP if i == len(sents) - 1 else SENT_GAP,
                              "section": sec["id"], "is_section_start": False})
    return clips

def build_timeline(clips, duration_of):
    """Per-section relative begin/end. Each section's audio file restarts at 0;
    the gap *after* a clip is silence that lives inside that section's file."""
    out = {}
    cur_section = None
    cum = 0.0
    for c in clips:
        if c["section"] != cur_section:
            cur_section, cum = c["section"], 0.0
        begin = round(cum, 3)
        end = round(cum + duration_of(c["id"]), 3)
        out[c["id"]] = {"section": c["section"], "begin": begin, "end": end}
        cum = end + c["gap_after"]
    return {"clips": out}

# ── Internal-pause padding (Option B): the other arithmetic worth a test ───────
def splice_pads(x, sr):
    """Return int16 samples `x` with PAUSE_PAD of silence added inside each internal
    (non-edge) quiet run >= MIN_INTERNAL_SIL. Reads nothing, mutates nothing — pure,
    so a re-run always rebuilds from the raw clip and can never double-pad. Edge
    silence is left alone; it belongs to the between-clip gaps the builder adds."""
    frame = int(0.010 * sr)                       # 10 ms envelope window
    nf = len(x) // frame
    if nf == 0 or PAUSE_PAD <= 0:
        return x
    env = np.abs(x[:nf * frame].reshape(nf, frame).astype(np.int32)).max(axis=1)
    silent = env < 32767 * 10 ** (SIL_DBFS / 20)
    minf = max(1, round(MIN_INTERNAL_SIL * sr / frame))
    pad = np.zeros(round(PAUSE_PAD * sr), dtype=x.dtype)
    parts, prev, i = [], 0, 0
    while i < nf:
        if not silent[i]:
            i += 1; continue
        j = i
        while j < nf and silent[j]:
            j += 1
        if i > 0 and j < nf and (j - i) >= minf:  # internal, long enough → pad its middle
            mid = ((i + j) // 2) * frame
            parts.append(x[prev:mid]); parts.append(pad); prev = mid
        i = j
    parts.append(x[prev:])
    return np.concatenate(parts)

def pad_clip(raw_wav, out_wav):
    """Rebuild out_wav from raw_wav with internal pauses lengthened (always from raw)."""
    w = wave.open(raw_wav, "rb"); sr, n = w.getframerate(), w.getnframes()
    x = np.frombuffer(w.readframes(n), dtype=np.int16); w.close()
    out = np.ascontiguousarray(splice_pads(x, sr))
    ww = wave.open(out_wav, "wb")
    ww.setnchannels(1); ww.setsampwidth(2); ww.setframerate(sr)
    ww.writeframes(out.tobytes()); ww.close()

def _selftest():
    sr = 24000
    tone = (np.sin(np.arange(int(0.5 * sr)) * 0.2) * 8000).astype(np.int16)
    gap  = np.zeros(int(0.10 * sr), dtype=np.int16)               # 100 ms internal pause
    internal = np.concatenate([tone, gap, tone])
    assert len(splice_pads(internal, sr)) - len(internal) == round(PAUSE_PAD * sr), "one internal pad expected"
    edged = np.concatenate([np.zeros(int(0.2 * sr), dtype=np.int16), tone,
                            np.zeros(int(0.2 * sr), dtype=np.int16)])
    assert len(splice_pads(edged, sr)) == len(edged), "edge silence must not be padded"
    tiny = np.concatenate([tone, np.zeros(int(0.03 * sr), dtype=np.int16), tone])  # 30ms < min
    assert len(splice_pads(tiny, sr)) == len(tiny), "sub-threshold gap must not be padded"
    long = "a" * 350 + " — " + "b" * 350 + ", " + "c" * 100
    assert [len(p) for p in chunk(long)] == [352, 351, 100], "long text splits after the dash and the comma"
    print(f"selftest ok: internal +{round(PAUSE_PAD*1000)}ms, edges & <{round(MIN_INTERNAL_SIL*1000)}ms untouched")

# ── I/O helpers (untested side-effects, same as before) ────────────────────────
def run(cmd, **kw): subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)
def dur(path):
    return float(subprocess.check_output(
        ["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0", path], text=True).strip())
def make_sil(path, sec):
    if not os.path.exists(path):
        run(["ffmpeg","-y","-f","lavfi","-i",f"anullsrc=r={SR}:cl=mono","-t",str(sec),"-c:a","pcm_s16le", path])

# ponytail: merge_short (gluing 2–4 word clips into a neighbour for cadence) is
# dropped — it changed sentence count, which would break the 1 sentence = 1 SMIL
# <par> read-along mapping. Add back as an audio-only speechGroup field in
# segments.json if Chapter I's short dialogue lines read poorly. Known ceiling:
# a 2–4 word clip synthesized alone can rise instead of fall.
# ponytail: the whole-book .m4b mux is dropped here too — the read-along proof
# needs per-section .m4a + timing.json, and the standalone .m4b is independent of
# that contract. Rebuild it from the per-section concat lists if wanted.

TOOL_PY = os.path.expanduser("~/.local/share/uv/tools/kokoro-tts-tool/bin/python")
FR_SYNTH = ("import sys, soundfile as sf; from kokoro_tts_tool.engine import KokoroEngine; e = KokoroEngine(); e.load(); "
            "s, sr = e._engine.create(sys.argv[1], voice=sys.argv[3], speed=1.0, lang='fr-fr'); sf.write(sys.argv[2], s, sr)")

MAX_CHARS = 400   # ⚠ Kokoro crashes past ~510 phonemes (~400 characters of English); longer sentences are voiced in pieces

def chunk(text):
    """Split text over MAX_CHARS at the latest dash, semicolon, colon or comma that fits."""
    if len(text) <= MAX_CHARS:
        return [text]
    for sep in (" — ", "; ", ": ", ", "):
        cut = text.rfind(sep, 0, MAX_CHARS)
        if cut > 0:
            cut += len(sep.rstrip())
            return [text[:cut]] + chunk(text[cut:].strip())
    return [text]

def synth_clip(clip):
    """Synthesize one clip's speech to a normalized mono wav, cached by segment ID."""
    wav = f"{CACHE}/{clip['id']}.wav"
    if not os.path.exists(wav):
        print(f">> synth {clip['id']}: {clip['speech'][:50]!r}")
        pieces = []   # (text, is_french); odd re.split parts are French (reader/speech.py marks them)
        for i, text in enumerate(re.split(r"‹fr›(.*?)‹/fr›", clip["speech"])):
            pieces += [(t, True)] if i % 2 else [(t, False) for t in chunk(text)]
        pieces = [(t.strip(), fr) for t, fr in pieces if t.strip()]
        if len(pieces) == 1 and not pieces[0][1]:
            run(["kokoro-tts-tool","synthesize","--stdin","--output",wav,"--voice",VOICE], input=pieces[0][0] + "\n")
        else:
            files = []
            for i, (text, fr) in enumerate(pieces):
                f = f"{wav}.{i}.wav"
                if fr:   # ⚠ the CLI picks pronunciation rules from the voice name, so French goes straight to the engine
                    run([TOOL_PY, "-c", FR_SYNTH, text, f, VOICE])
                else:
                    run(["kokoro-tts-tool","synthesize","--stdin","--output",f,"--voice",VOICE], input=text + "\n")
                files.append(f)
            lst = wav + ".txt"
            open(lst, "w").write("".join(f"file '{os.path.abspath(f)}'\n" for f in files))
            run(["ffmpeg","-y","-f","concat","-safe","0","-i",lst,"-c","copy",wav])
            for f in files + [lst]: os.remove(f)
        norm = wav + ".n.wav"
        run(["ffmpeg","-y","-i",wav,"-ar",str(SR),"-ac","1","-c:a","pcm_s16le", norm])
        os.replace(norm, wav)
    return wav

def main():
    # The reader bundle's build/ folder is the contract: segments.json comes in,
    # timing.json + per-section audio land beside it (so audio → <bundle>/build/audio/).
    seg_path = os.environ.get("SEG_JSON",
        "../../docs/reader/non-fiction/essays-and-criticism/the-great-sin/build/segments.en-1905.json")
    out_dir   = os.path.dirname(os.path.abspath(seg_path))   # the bundle's build/ dir
    audio_dir = f"{out_dir}/audio"
    timing_path = f"{out_dir}/timing.{json.load(open(seg_path, encoding='utf-8'))['version']}.json"

    seg = json.load(open(seg_path, encoding="utf-8"))
    # ⚠ cache per work AND edition: every work and every translation numbers its sentences p-1-1-s1…, so a shared folder would splice one edition's voice into another.
    key = f"{seg['work']}.{seg['version']}"
    global CACHE, PADDED
    CACHE, PADDED = f"{CACHE}/{key}", f"{PADDED}/{key}"
    clips = iter_clips(seg)
    os.makedirs(CACHE, exist_ok=True)
    os.makedirs(PADDED, exist_ok=True)
    os.makedirs(audio_dir, exist_ok=True)

    # 1) synth every clip (raw cache), then rebuild each with internal pauses padded.
    #    Padding is fast + always from raw, so it re-runs cleanly after a PAUSE_PAD tweak.
    for c in clips:
        synth_clip(c)
        pad_clip(f"{CACHE}/{c['id']}.wav", f"{PADDED}/{c['id']}.wav")
    # 2) measure the *padded* clips so read-along timing matches what actually plays
    timing = build_timeline(clips, duration_of=lambda cid: dur(f"{PADDED}/{cid}.wav"))

    # 3) per-section mastered audio: concat padded clip wavs + their gap silences
    sil = {}
    for g in {SENT_GAP, PARA_GAP, CHAP_GAP}:
        sil[g] = f"{PADDED}/_sil_{int(g*1000)}.wav"; make_sil(sil[g], g)

    timing["audio"] = {}
    by_section = {}
    for c in clips:
        by_section.setdefault(c["section"], []).append(c)

    for sec_id, sec_clips in by_section.items():
        listfile = f"{PADDED}/_concat_{sec_id}.txt"
        with open(listfile, "w") as f:
            for c in sec_clips:
                f.write(f"file '{os.path.abspath(PADDED)}/{c['id']}.wav'\n")
                if c["gap_after"] > 0:
                    f.write(f"file '{os.path.abspath(sil[c['gap_after']])}'\n")
        out_audio = f"{audio_dir}/{key}.{sec_id}.m4a"
        run(["ffmpeg","-y","-f","concat","-safe","0","-i",listfile,
             "-af",MASTER,"-ar","44100","-c:a","aac","-b:a",BITRATE,
             "-movflags","+faststart", out_audio])
        timing["audio"][sec_id] = f"audio/{key}.{sec_id}.m4a"

    json.dump(timing, open(timing_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f">> wrote {timing_path} ({len(timing['clips'])} clips, {len(timing['audio'])} sections)")

if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        main()
