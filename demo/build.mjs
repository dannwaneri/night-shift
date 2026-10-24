// Builds demo/out/night-shift-demo.mp4 from the recorder's frames: real frame times, the Gemma reading part
// sped up (and labelled), captions burned in at the recorded step times, title and end cards. Usage: node demo/build-video.mjs
import { readFileSync, writeFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { createRequire } from "node:module";
const ffmpeg = createRequire("C:/Users/DELL/tools/testreel/package.json")("ffmpeg-static");
const OUT = "demo/out";
const frames = JSON.parse(readFileSync(`${OUT}/frames.json`, "utf8"));
const m = JSON.parse(readFileSync(`${OUT}/marks.json`, "utf8"));
const SPEED = 1, CARD = 5;   // names took ~5 s each in the recording, so real speed; title/end cards 4 s each

// Map recorded time -> output time (reading..names_done runs SPEED x faster), then shift by the title card.
const slow0 = m.end, slow1 = m.end;
const map = (t) => CARD + (t <= slow0 ? t : t <= slow1 ? slow0 + (t - slow0) / SPEED : slow0 + (slow1 - slow0) / SPEED + (t - slow1));

// Concat list with each frame's real duration (frames only arrive when the screen changes).
const vis = frames.filter((f) => f.t >= 0);
let list = "";
// The recorder stores full paths; older recorders stored paths relative to the working folder.
const absf = (f) => (/^[A-Za-z]:[\\/]/.test(f) ? f : process.cwd() + "/" + f).replace(/\\/g, "/");
for (let i = 0; i < vis.length; i++) {
  const t1 = i + 1 < vis.length ? vis[i + 1].t : m.end + 1.5;
  const d = Math.max(0.001, map(t1) - map(vis[i].t));
  list += `file '${absf(vis[i].f)}'\nduration ${d.toFixed(3)}\n`;
}
list += `file '${absf(vis.at(-1).f)}'\n`;
writeFileSync(`${OUT}/list.txt`, list);
const mainEnd = map(m.end + 1.5);

// Captions (ASS). Text from demo/captions.md, times from the recorded marks.
const ts = (s) => { const h = Math.floor(s / 3600), mi = Math.floor(s / 60) % 60, se = (s % 60).toFixed(2).padStart(5, "0"); return `${h}:${String(mi).padStart(2, "0")}:${se}`; };
const caps = [
  [0, CARD, "Title", "NIGHT SHIFT\\N{\\fs40}my saved tech videos, turned into notes while the light is on"],
  [map(m.run), map(m.run) + 13, "Cap", "Overnight, two open models on my CPU laptop turn my saved tech videos into notes.\\NWhisper writes out the speech. Gemma 4 E2B writes the note."],
  [map(m.run) + 13, map(m.notes), "Cap", "It only works while the laptop is plugged in. When light goes, it waits.\\NReal log from Port Harcourt: outages of 7 h 27 min and 9 h 58 min."],
  [map(m.notes), map(m.screen), "Cap", "Every note is checked by code: the quote must be word for word,\\Nand every name must be in the post or in the video."],
  [map(m.screen), map(m.fix), "Cap", "A silent demo has no speech, so Gemma reads 4 frames of the screen.\\N22 of my 56 notes exist only because of this."],
  [map(m.fix), map(m.search), "Cap", "Whisper heard \"Olamar\". Gemma found \"Ollama\" in the post,\\Nand code applied the fix only after checking it."],
  [map(m.search), mainEnd, "Cap", "Search my notes for \"ollama\": 2 videos.\\NA plain search of the transcripts finds none."],
  [mainEnd, mainEnd + CARD, "Title", "{\\fs44}97 saved videos · 56 notes · 10 checked once\\N\\N{\\fs34}Gemma 4 E2B + Whisper, local, CPU only · Port Harcourt"],
];
const ass = `[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Segoe UI,38,&H00FFFFFF,&H00FFFFFF,&H00000000,&HC0201810,0,0,0,0,100,100,0,0,3,18,0,2,120,120,28,1
Style: Tag,Segoe UI,34,&H0000D7FF,&H00FFFFFF,&H00000000,&HC0201810,1,0,0,0,100,100,0,0,3,12,0,9,60,60,40,1
Style: Title,Segoe UI,72,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,0,0,5,120,120,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
${caps.map(([a, b, st, tx]) => `Dialogue: 0,${ts(a)},${ts(b)},${st},,0,0,0,,${tx}`).join("\n")}
`;
writeFileSync(`${OUT}/captions.ass`, "\ufeff" + ass);

// Video: dark card, then the frames scaled to 1080 high and centred, then a dark card; captions on top.
const total = mainEnd + CARD;
const vf = [
  `[1:v]scale=-2:860:flags=lanczos,setsar=1,fps=25[app]`,
  `[0:v][app]overlay=x=(W-w)/2:y=14:enable='between(t,${CARD},${mainEnd.toFixed(3)})':eof_action=pass[v0]`,
  `[v0]subtitles=${OUT}/captions.ass[v]`,
].join(";");
execFileSync(ffmpeg, ["-y", "-hide_banner", "-loglevel", "error",
  "-f", "lavfi", "-i", `color=c=0x101826:s=1920x1080:r=25:d=${total.toFixed(3)}`,
  "-f", "concat", "-safe", "0", "-itsoffset", String(CARD), "-i", `${OUT}/list.txt`,
  "-filter_complex", vf, "-map", "[v]", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "25", "-movflags", "+faststart",
  `${OUT}/night-shift-demo.mp4`], { stdio: "inherit" });
console.log("built", `${OUT}/night-shift-demo.mp4`, `${total.toFixed(1)} s`);
