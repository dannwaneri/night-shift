# night-shift

I save tech videos on X and never watch them again. My bookmark tool (bookmark-cli, a local SQLite copy of my
bookmarks) only reads text, and this month 3 of every 4 things I saved were videos.

So a night shift does it. Every night at 23:00, and only while the laptop is plugged in, it turns my saved tech
videos into short notes I can search. It runs entirely on my laptop (CPU only), in Port Harcourt, Nigeria, where the
grid power ("light") often goes off for hours: when the laptop drops to battery, it stops and waits, and carries on
when light comes back.

## What does the work

| step | done by |
|---|---|
| pick saved videos with tech words in the post, 3 minutes or less | code (keywords, yt-dlp reads the length) |
| write out the speech | **Whisper small** (open, CPU) |
| write the note: kind, tools, main claim, numbers, word-for-word quote | **Gemma 4 E2B** via Ollama (open weights, CPU) |
| silent videos: read 4 frames of the screen | **Gemma 4 E2B** (image input) |
| fix product names Whisper misheard ("Olamar" → "Ollama"), using the post | **Gemma 4 E2B** finds them, code checks and applies them |
| check every answer before it is saved | code (`guard()`, `screen_guard()`), one retry, then "not read" |
| pause on battery, resume when plugged in | code (`wait_for_power()`, psutil) |

The guard: a quote must be word for word in the transcript; every tool must be in the post, the transcript or on
screen; every number must have been said or written; a name fix must be in the transcript, in the post, and look
alike (letter similarity ≥ 0.6). For screen notes there is no transcript to check, so code only removes: repeated
items, more than 8 items, items over 12 words, and "tools" not on screen or in the post.

## Results (my own 97 saved tech videos, 22–24 Oct 2026)

- 22 longer than 3 minutes (skipped), 3 blocked by X, 72 short: 42 with speech, 30 silent
- **56 notes**: 34 from speech, **22 read from the screen** (these exist only because Gemma reads images)
- 8 speech notes refused because the quote was not word for word
- 10 notes checked by me against the real videos: 9 correct on the first pass (the miss was a wrong name fix, which
  led to the letter-similarity rule)
- medians on an Intel i5 CPU: Whisper 23 s, Gemma note 16 s, Gemma screen reading 38 s per video
- real power cuts it waited through: 2 min, 7 h 27 min, 9 h 58 min

Also tried and dropped: ranking text bookmarks with Gemma (`test_pick.py`, `eval_set2.py`). On a held-out set of
50 I labelled by hand, keyword matching beat Gemma (5/8 vs 4/8 in the top 5); sorting by likes found 0/8.

## Run it

Needs: Python 3, [Ollama] with `gemma4:e2b-it-qat`, `pip install openai-whisper yt-dlp psutil`, ffmpeg on the path
(the code points at a local ffmpeg-static copy; change `FFMPEG_DIR`), and a bookmark database in the shape bookmark-cli
writes (`~/.bookmark-cli/bookmarks.db`, table `bookmarks` with `text`, `url`, `media_json`, `source`).

```
python videoshift.py --limit 30 --until 07:00   # one night shift
python videoshift.py search ollama               # search the notes
python videoshift.py --redo-silent               # silent videos: read the screen
python review.py 10                               # a page to check 10 notes once against the videos
```

`run_nightly.bat` is what the Windows scheduled task runs at 23:00. Notes, transcripts and frames stay in `out/`,
which is not in this repo.

Limits: it can tell "plugged in" from "on battery", not grid power from a generator. Whisper small mishears some
names and does badly on music and on some non-English speech. Screen notes can only be checked by a person.

[Ollama]: https://ollama.com

## License

MIT
