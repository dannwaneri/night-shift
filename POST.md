---
title: "I never rewatch what I save. A night shift turned 56 of my videos into notes, and waited out a 10-hour power cut to do it."
published: false
tags: devchallenge, hf26challenge, gemma, opensource
---

*This is a submission for the [Hacktoberfest Open-Source AI Challenge Week 3: Slow and Steady](https://dev.to/challenges/hacktoberfest-week3-2026-10-19)*

## What I Built

I save things on X all day and almost never go back to them. A few months ago I built a small tool, bookmark-cli, that syncs my bookmarks to a local database every day so I can search them for writing ideas. It has 12,309 bookmarks in it.

It only reads text. That used to be fine. Over the years about 9% of what I saved was video. This month it was 45 of 60, three out of four. So most of what I save now never reaches the tool I built to use it, and I never rewatch any of it.

I save them because I am fascinated by them, and I might need to copy ideas from them in the future. I am learning distribution.

So I gave the job to the night shift. Every night it looks at my saved videos whose post is about tech, keeps the ones that are 3 minutes or less, and turns each one into a short note I can search: what the video is about, the tools it names, the numbers it gives, and a word-for-word quote as proof.

Two open models do the work:

- Whisper (small) writes out what is said.
- Gemma 4 E2B writes the note. When the video has no speech at all, which is 30 of my 72 short tech videos, Gemma reads four frames of the screen instead. When Whisper mishears a product name, Gemma finds the right spelling in the post.

The best ideas are born out of laziness. I did not want to watch 97 videos. Now I don't have to.

### The slow and steady part

I live in Port Harcourt, Nigeria. Grid power ("light") goes off often and for hours, and a laptop running AI on the CPU empties its battery fast. So the night shift only works while the laptop is plugged in. The moment it drops to battery, it stops, saves its place, and waits. When light comes back, it carries on.

This week it did that for real, three times:

| light went | light came back | waited |
|---|---|---|
| Thu 14:32 | 14:34 | 2 min |
| Thu 14:52 | 22:19 | 7 h 27 min |
| Thu 23:04 | Fri 09:01 | 9 h 58 min |

It never spent my battery on a video. One limit: it can only tell "plugged in" from "on battery", so it cannot tell grid power from my generator.

## Demo

[YOU: YouTube embed, e.g. {% youtube VIDEO_ID %}]

## Code

[YOU: GitHub embed, e.g. {% github dannwaneri/night-shift %}]

## How I Built It

Everything runs on my laptop (Intel i5, no graphics card that the models can use, 16 GB of memory). Nothing is sent to an AI service.

1. Code picks the videos: saved posts with a video and tech words in the text. yt-dlp reads each video's length without downloading it, and anything over 3 minutes is skipped.
2. yt-dlp downloads the audio. Whisper small writes it out on the CPU (median 23 s a video). The audio is deleted after.
3. If there is speech, Gemma 4 E2B (through Ollama) writes the note from the transcript and the post (median 16 s).
4. If there is no speech, code takes four frames from the video, and Gemma reads the screen: what is shown, the words it can read, the tools on screen (median 38 s).
5. Code checks every answer before it is saved. There is one retry, then the note is marked "not read". The model can never loop.

The check is where most of the work went. The model may only copy, not invent:

- The quote must appear word for word in the transcript. Gemma once wrote "And there are some uniquely human things..." where the speaker said "But there are...". That one word was enough to refuse it. Allowing "nearly the same" would also let a dropped "not" through.
- Every tool name must be in the post or in the transcript (or on screen).
- Every number must have been said or written.
- A name fix is applied only if the heard word is in the transcript, the right name is in the post, and the two spellings look alike.

That last rule came from a mistake. I checked the first 10 notes against the real videos and marked all 10 correct. Then I went through Gemma's name fixes one by one and found that 4 of the 8 were wrong. In one, the speaker said "ChatGPT", Whisper wrote "Chan GPT", and Gemma changed it to "Claude" because the post was about Claude. That note was in my 10, so my score was really 9 of 10. Now a fix needs the two spellings to be at least 60% the same letters ("Olamar" and "Ollama" are 83%; "Chan GPT" and "Claude" are 31%).

### Results

| | |
|---|---|
| saved tech videos handled | 97 |
| longer than 3 minutes (skipped) | 22 |
| blocked by X | 3 |
| short videos | 72: 42 with speech, 30 silent |
| notes made | 56: 34 from speech, 22 read from the screen |
| speech notes refused (quote not word for word) | 8 |
| checked against the real video | 10, of which 9 correct on the first pass |

### Where Gemma does the work, and where it didn't

Take Gemma out and 22 of the 56 notes do not exist: those videos have no speech, so Whisper has nothing to give, and only Gemma can read the screen.

The name fixes matter less than I hoped, but they are real. Search my notes for "ollama" and you get two videos. In both transcripts Whisper wrote "Olamar" or "Olama", so a plain search of the transcripts finds nothing. Gemma does not catch every one: "DeepSeat" is still "DeepSeat" where the post says DeepSeek.

Before this, I tried to give Gemma a different job, and I am keeping the result in the post because it shaped what I built. I asked it to pick which of my text bookmarks were worth reading. I labelled 100 bookmarks by hand to test it. On the 50 I kept aside, a plain keyword match on my recent post titles did better than Gemma (5 of my 8 picks in its top 5, against 4 of 8 for Gemma). Sorting by likes found none of them. So keywords do the picking now, and Gemma does what keywords can't: read videos.

## Why Does Open Innovation Matter?

- It runs on what I have. A CPU laptop, no graphics card, no paid API. Whisper and Gemma 4 E2B are small enough to work overnight, and slow is fine when you are asleep.
- It works offline. Once the models are downloaded, the night shift needs the internet only to fetch the videos, and nothing it writes leaves my laptop.
- I could test it properly. With open weights on my own machine I could run the same model hundreds of times, measure it against plain keywords, and drop it where it lost. I would not do that with a paid API billing me per call.

## The Lazy Payoff

In minutes, the honest number is small: the 56 videos with notes add up to 51 minutes. But I was never going to watch them, so before this those 51 minutes were simply lost. Now they are 56 notes I can search.

What it cost me: one check. I watched the 10 sample videos once, about 8 minutes of video, so I never have to watch the rest.

I used it this week, on my own saves. It ran on Thursday and Friday, through the three power cuts above, and from Saturday it starts by itself at 23:00 and does whatever I saved that day while I sleep.

[YOU: add a line in your own words if you want, e.g. the first thing you searched for.]

## Prize Categories

Best Use of Gemma: Gemma 4 E2B runs locally through Ollama on a CPU-only laptop. It writes every note, reads the screen of silent videos (22 of 56 notes exist only because of that), and finds misheard product names, and every answer is checked by code before it is saved.
