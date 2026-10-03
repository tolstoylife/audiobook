from build_audiobook import iter_clips, build_timeline

SEG = {
  "version": "en-1905", "sections": [
    {"id": "sec-1", "headingSpeech": "Part One.", "paragraphs": [
      {"id": "p-1-1", "sentences": [
        {"id": "p-1-1-s1", "speech": "First."},
        {"id": "p-1-1-s2", "speech": "Second."}]}]},
    {"id": "sec-2", "headingSpeech": "Part Two.", "paragraphs": [
      {"id": "p-2-1", "sentences": [
        {"id": "p-2-1-s1", "speech": "Third."}]}]}]}

def test_iter_clips_order_and_heading():
    clips = iter_clips(SEG)
    assert [c["id"] for c in clips] == ["sec-1", "p-1-1-s1", "p-1-1-s2", "sec-2", "p-2-1-s1"]
    assert clips[0]["speech"] == "Part One."
    assert clips[0]["is_section_start"] is True
    # last sentence of a paragraph gets the paragraph gap
    assert clips[2]["gap_after"] > clips[1]["gap_after"]

def test_build_timeline_resets_each_section():
    clips = iter_clips(SEG)
    timing = build_timeline(clips, duration_of=lambda _id: 1.0)  # every clip 1.0s
    c = timing["clips"]
    # sec-1: heading 0-1, then PARA_GAP, then s1, then PARA_GAP, then s2
    assert c["sec-1"] == {"section": "sec-1", "begin": 0.0, "end": 1.0}
    assert c["p-1-1-s1"]["begin"] == round(1.0 + 0.85, 3)   # after heading + PARA_GAP
    assert c["p-1-1-s2"]["begin"] > c["p-1-1-s1"]["end"]
    # section 2 audio file resets to 0
    assert c["sec-2"] == {"section": "sec-2", "begin": 0.0, "end": 1.0}
