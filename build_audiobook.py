#!/usr/bin/env python3
"""
Build the full chaptered, mastered M4B of "A Great Iniquity".

Pipeline and findings: README.md (this folder) and ../../docs/audiobook-pipeline.md.
  - voice bm_daniel, synthesized PER SENTENCE via `synthesize`
    (NOT `infinite` — its streaming step mangled long-sentence endings; an A/B
     on ch02 confirmed `synthesize` lands sentence endings cleanly)
  - sentence / paragraph / chapter pauses, mastered, chapter markers,
    M4B muxed with +faststart (iOS Books refuses the file without it)

Reads chapters_flow/ (flow-preprocessed text). Resumable: re-running skips
sentences whose WAV already exists.

  python3 build_audiobook.py [voice] [--dry]
Requires: kokoro-tts-tool, ffmpeg, ffprobe.
"""
import subprocess, os, re, sys

ARGS     = [a for a in sys.argv[1:] if not a.startswith("--")]
VOICE    = ARGS[0] if ARGS else "bm_daniel"
DRY      = "--dry" in sys.argv
SENT_GAP = 0.45   # pause between sentences within a paragraph
PARA_GAP = 0.85   # pause between paragraphs (most end on a George quote — Johan wanted longer)
CHAP_GAP = 2.0    # pause between Parts (research: section breaks ~2–2.5s; clearly > paragraph)
SHORT_WORDS = 4   # merge sentences this short into a neighbour — a tiny clip synthesized alone rises instead of falling
BITRATE  = "128k"
SR       = 24000  # Kokoro's native rate
OUT      = f"a_great_iniquity_{VOICE}.m4b"
CACHE    = f"wav_full_{VOICE}"
MASTER   = "highpass=f=70,deesser=i=0.4,loudnorm=I=-19:TP=-2:LRA=7"

FILES  = [f"chapters_flow/ch{i:02d}.txt" for i in range(10)]
TITLES = ["Introduction","Part I","Part II","Part III","Part IV",
          "Part V","Part VI","Part VII","Part VIII","Part IX"]  # M4B chapter list (Roman reads better visually)
ROMAN  = {"I":"One","II":"Two","III":"Three","IV":"Four","V":"Five",
          "VI":"Six","VII":"Seven","VIII":"Eight","IX":"Nine"}

# Pronunciation respellings for Kokoro's g2p — source text stays faithful, we fix at synth time.
SUBS = [
    (r"\blive\b", "liv"),                  # Kokoro says /laɪv/ for the verb
    (r"\bLabouchere\b", "Labooshair"),     # the MP Henry Labouchère
    (r"\bRadischeff\b", "Rahdeeshef"),     # Radishchev
    (r"Yasnaya Poliana", "Yasnaya Polyahna"),
    (r"\(Matt[.,] xxiii\. 27, 28\)",
     "Matthew twenty-three, verses twenty-seven and twenty-eight"),  # spoken scripture reference
]
def respell(t):
    for pat, rep in SUBS:
        t = re.sub(pat, rep, t)
    return t

def split_paras(text):
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]

def join_midsentence(paras):
    # ponytail: a paragraph not ending in sentence punctuation was split by a page
    # break, not the author — glue it to the next. Ceiling: assumes real paragraphs
    # end in . ! ? " ) … (true for this text); revisit if a chapter proves otherwise.
    out = []
    for p in paras:
        if out and not out[-1].rstrip().endswith((".", "!", "?", '"', "”", ")", "…")):
            out[-1] += " " + p
        else:
            out.append(p)
    return out

def spoken_header(p):
    m = re.match(r"Part ([IVX]+)\.\s*$", p)               # "Part III." -> "Part Three."
    return f"Part {ROMAN[m.group(1)]}." if m and m.group(1) in ROMAN else p

def split_sents(text):
    text = re.sub(r"(\d)\.(\d)", r"\1<DOT>\2", text)       # protect 1.40
    parts = re.split(r'(?<=[.!?"])\s+(?=["“(A-Z])', text)  # end-punct (+quote) then Cap/quote/paren
    return [p.replace("<DOT>", ".").strip() for p in parts if p.strip()]

def merge_short(units):
    # A 2–4 word clip synthesized alone rises instead of falling. Glue each short unit
    # forward into the next so Kokoro has runway to land the cadence — this also folds
    # "Part One." into the first sentence of the chapter. Last unit merges backward.
    units = list(units)
    i = 0
    while i < len(units) - 1:
        text, gap = units[i]
        if len(text.split()) <= SHORT_WORDS:
            nt, ng = units[i + 1]
            units[i] = (text + " " + nt, ng)   # take the follower's gap; the short clip's own gap dissolves
            del units[i + 1]
        else:
            i += 1
    if len(units) >= 2 and len(units[-1][0].split()) <= SHORT_WORDS:
        (t0, _), (t1, g1) = units[-2], units[-1]
        units[-2:] = [(t0 + " " + t1, g1)]
    return units

def units_for(path):
    paras = join_midsentence(split_paras(open(path).read()))
    paras = [respell(spoken_header(p)) for p in paras]
    units = []  # (text, gap_after)
    for p in paras:
        sents = split_sents(p)
        for si, s in enumerate(sents):
            units.append((s, PARA_GAP if si == len(sents) - 1 else SENT_GAP))
    units = merge_short(units)
    if units:
        units[-1] = (units[-1][0], 0.0)  # chapter gap (or EOF) handles the trailing pause
    return units

if DRY:
    total = 0
    for i, f in enumerate(FILES):
        u = units_for(f); total += len(u)
        print(f"{TITLES[i]:16s} {len(u):3d} sentences   first: {u[0][0][:58]!r}")
    print(f"\n{total} sentences total")
    sys.exit(0)

os.makedirs(CACHE, exist_ok=True)
def run(cmd, **kw): subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)
def dur(path):
    return float(subprocess.check_output(
        ["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0", path], text=True).strip())
def make_sil(path, sec):
    if not os.path.exists(path):
        run(["ffmpeg","-y","-f","lavfi","-i",f"anullsrc=r={SR}:cl=mono","-t",str(sec),"-c:a","pcm_s16le", path])

sil = {}
for g in {SENT_GAP, PARA_GAP, CHAP_GAP}:
    sil[g] = f"{CACHE}/_sil_{int(g*1000)}.wav"; make_sil(sil[g], g)

concat = open(f"{CACHE}/concat.txt", "w")
meta   = open(f"{CACHE}/meta.txt", "w")
meta.write(";FFMETADATA1\ntitle=A Great Iniquity\nartist=Leo Tolstoy\n"
           "album=A Great Iniquity\ngenre=Audiobook\ndate=1905\n\n")
cum = 0.0
def add(path):
    global cum
    concat.write(f"file '{os.path.abspath(path)}'\n"); cum += dur(path)

for i, f in enumerate(FILES):
    if i > 0:
        add(sil[CHAP_GAP])
    chap_start = cum
    units = units_for(f)
    for n, (s, g) in enumerate(units):
        wav = f"{CACHE}/ch{i:02d}_s{n:03d}.wav"
        if not os.path.exists(wav):
            print(f">> {TITLES[i]}  sentence {n+1}/{len(units)}")
            run(["kokoro-tts-tool","synthesize","--stdin","--output",wav,"--voice",VOICE], input=s + "\n")
            norm = wav + ".n.wav"
            run(["ffmpeg","-y","-i",wav,"-ar",str(SR),"-ac","1","-c:a","pcm_s16le", norm]); os.replace(norm, wav)
        add(wav)
        if g > 0:
            add(sil[g])
    meta.write(f"[CHAPTER]\nTIMEBASE=1/1000\nSTART={int(chap_start*1000)}\n"
               f"END={int(cum*1000)}\ntitle={TITLES[i]}\n\n")

concat.close(); meta.close()
print(f">> Muxing + mastering -> {OUT}")
run(["ffmpeg","-y","-f","concat","-safe","0","-i",f"{CACHE}/concat.txt","-i",f"{CACHE}/meta.txt",
     "-map_metadata","1","-af",MASTER,"-ar","44100","-c:a","aac","-b:a",BITRATE,
     "-movflags","+faststart","-f","mp4", OUT])
print(f">> Done: {OUT}  ({cum/60:.1f} min)")
