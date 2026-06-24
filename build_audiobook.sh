#!/usr/bin/env bash
# Build a chaptered M4B audiobook of "A Great Iniquity" using Kokoro TTS.
# Run from a folder containing the `chapters/` directory.
# Requires: kokoro-tts-tool, ffmpeg, ffprobe (brew install ffmpeg).
set -euo pipefail

VOICE="${1:-bm_george}"   # override: ./build_audiobook.sh bm_daniel
BITRATE="128k"            # transparent for 24 kHz speech; no point going higher
OUT="a_great_iniquity.m4b"

# Mastering chain applied at mux time — this is what makes it pleasant:
#   highpass     cuts sub-bass rumble/breath thumps
#   deesser      tames harsh "s" sibilance (the main TTS fatigue source)
#   loudnorm     even, consistent loudness (-19 LUFS, audiobook standard)
MASTER="highpass=f=70,deesser=i=0.4,loudnorm=I=-19:TP=-2:LRA=7"

# Chapter files in order, with the spoken titles for the markers.
FILES=(chapters/ch00.txt chapters/ch01.txt chapters/ch02.txt chapters/ch03.txt \
       chapters/ch04.txt chapters/ch05.txt chapters/ch06.txt chapters/ch07.txt \
       chapters/ch08.txt chapters/ch09.txt)
TITLES=("Introduction" "Part I" "Part II" "Part III" "Part IV" "Part V" \
        "Part VI" "Part VII" "Part VIII" "Part IX")

mkdir -p wav
echo ";FFMETADATA1"           >  meta.txt
echo "title=A Great Iniquity" >> meta.txt
echo "artist=Leo Tolstoy"     >> meta.txt
echo "album=A Great Iniquity" >> meta.txt
echo "genre=Audiobook"        >> meta.txt
echo "date=1905"              >> meta.txt
echo ""                       >> meta.txt

: > concat.txt
start_ms=0
for i in "${!FILES[@]}"; do
  wav="wav/ch$(printf '%02d' "$i").wav"
  if [ -f "$wav" ]; then
    echo ">> Skipping ${TITLES[$i]} (already generated: $wav)"
  else
    echo ">> Generating ${TITLES[$i]} -> $wav"
    kokoro-tts-tool infinite --input "${FILES[$i]}" --output "$wav" --voice "$VOICE"
  fi

  # Real duration in ms from ffprobe
  dur=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$wav")
  dur_ms=$(python3 -c "print(int(round($dur*1000)))")
  end_ms=$((start_ms + dur_ms))

  {
    echo "[CHAPTER]"
    echo "TIMEBASE=1/1000"
    echo "START=$start_ms"
    echo "END=$end_ms"
    echo "title=${TITLES[$i]}"
    echo ""
  } >> meta.txt

  echo "file '$PWD/$wav'" >> concat.txt
  start_ms=$end_ms
done

echo ">> Muxing + mastering chaptered audiobook -> $OUT"
ffmpeg -y -f concat -safe 0 -i concat.txt -i meta.txt \
  -map_metadata 1 -af "$MASTER" -ar 44100 \
  -c:a aac -b:a "$BITRATE" -f mp4 "$OUT"

echo ">> Done: $OUT  ($(python3 -c "print(round($end_ms/60000,1))") min)"
echo ">> Cleanup intermediates with:  rm -rf wav concat.txt meta.txt"
