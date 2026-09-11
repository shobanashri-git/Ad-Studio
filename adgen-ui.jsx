import React, { useState, useRef, createContext, useContext } from "react";

// ─────────────────────────────────────────────────────────────────────────
// CONFIG — point at your FastAPI backend (adgen.api:app).
// Set DEMO_MODE=false to hit the real API.
// ─────────────────────────────────────────────────────────────────────────
const API_BASE = "http://localhost:8000";
const DEMO_MODE = false;

const accent = "#e8a13a";

// From the workflows:
const DURATIONS = [3, 4, 5, 6, 7, 8, 9, 10, 12, 15];
const LONGEST_SIDES = [864, 1024, 1216, 1344, 1536];
const RATIOS = ["keep", "1:1", "16:9", "9:16", "2:3"];
// Video size presets (landscape w×h). Portrait transposes each pair.
const VIDEO_SIZES = [
  [608, 352], [736, 416], [864, 480], [960, 544], [1056, 608], [1152, 640],
  [1216, 672], [1280, 736], [1344, 768], [1376, 768], [1504, 832],
  [1664, 928], [1824, 1024], [1920, 1088],
];
const VIDEO_STARRED = new Set(["480x864", "672x1216", "768x1344"]);

// ─────────────────────────────────────────────────────────────────────────
// Asset tray
// ─────────────────────────────────────────────────────────────────────────
const TrayCtx = createContext(null);
const useTray = () => useContext(TrayCtx);
let _aid = 0;
const nextId = () => `a${++_aid}`;

function TrayProvider({ children }) {
  const [assets, setAssets] = useState([]); // {id, kind, url, assetId?, file?, label}
  const add = (a) => { const id = nextId(); setAssets((p) => [{ id, ...a }, ...p]); return id; };
  const remove = (id) => setAssets((p) => p.filter((a) => a.id !== id));
  const clear = () => setAssets([]);
  return <TrayCtx.Provider value={{ assets, add, remove, clear }}>{children}</TrayCtx.Provider>;
}

// ─────────────────────────────────────────────────────────────────────────
// Building blocks
// ─────────────────────────────────────────────────────────────────────────

// Input slot: upload a file OR pick a tray asset of the right kind.
// value: { url, file?, assetId?, kind, label } | null
function AssetSlot({ label, hint, value, onChange, accept = "image" }) {
  const inputRef = useRef(null);
  const [picking, setPicking] = useState(false);
  const { assets } = useTray();
  const candidates = assets.filter((a) => a.kind === accept);
  const preview = value?.url || null;
  const isImg = (value?.kind || accept) === "image";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6, position: "relative" }}>
      <span style={S.slotLabel}>{label}</span>
      <div style={{ ...S.slot, borderColor: value ? accent : "#2a2d33", background: preview ? "#0d0e10" : "#131417" }}>
        {preview ? (
          isImg ? <img src={preview} alt={label} style={S.slotImg} />
                : <div style={S.slotFilled}><span style={S.kindTag}>{value.kind}</span><span style={S.slotMini}>{value.label || "ready"}</span></div>
        ) : <span style={S.slotHint}>{hint || `Upload or pick ${accept}`}</span>}
        <div style={S.slotBtns}>
          <button type="button" style={S.slotBtn} onClick={() => inputRef.current?.click()}>Upload</button>
          <button type="button" style={{ ...S.slotBtn, opacity: candidates.length ? 1 : 0.4 }}
            onClick={() => candidates.length && setPicking((p) => !p)}>
            Tray{candidates.length ? ` (${candidates.length})` : ""}
          </button>
          {value && <button type="button" style={S.slotBtnClear} onClick={(e) => { e.stopPropagation(); onChange(null); }}>✕</button>}
        </div>
        <input ref={inputRef} type="file"
          accept={accept === "image" ? "image/*" : accept === "audio" ? "audio/*" : "video/*"}
          hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) onChange({ url: URL.createObjectURL(f), file: f, kind: accept, label: f.name }); }} />
      </div>
      {picking && candidates.length > 0 && (
        <div style={S.picker}>
          {candidates.map((a) => (
            <button key={a.id} type="button" style={S.pickerItem}
              onClick={() => { onChange({ url: a.url, assetId: a.assetId, kind: a.kind, label: a.label }); setPicking(false); }}>
              {a.kind === "image" ? <img src={a.url} alt={a.label} style={S.pickerImg} /> : <span style={S.pickerKind}>{a.kind}</span>}
              <span style={S.pickerLabel}>{a.label}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function Pill({ active, onClick, children, sub, star }) {
  return (
    <button type="button" onClick={onClick} style={{ ...S.pill, ...(active ? S.pillActive : {}) }}>
      {children}{star && <span style={S.star}>★</span>}
      {sub && <span style={S.pillSub}>{sub}</span>}
    </button>
  );
}

function StatusLine({ status }) {
  if (!status) return null;
  const map = { idle: "#6b7280", running: "#e8a13a", done: "#4ea777", error: "#d0554f" };
  const kind = status.kind || "idle";
  return <div style={{ ...S.status, color: map[kind] }}><span style={{ ...S.dot, background: map[kind] }} /><span style={S.mono}>{status.text}</span></div>;
}

function Panel({ title, blurb, children }) {
  return (
    <section style={S.section}>
      <div style={S.sectionHead}><div><h2 style={S.sectionTitle}>{title}</h2><p style={S.sectionBlurb}>{blurb}</p></div></div>
      {children}
    </section>
  );
}

function Gallery({ items, onSend, label }) {
  if (!items?.length) return null;
  return (
    <div style={S.gallery}>
      {items.map((it, i) => (
        <div key={i} style={S.galleryItem}>
          <img src={absUrl(it.url)} alt="output" style={S.galleryImg} />
          <button style={S.sendOverlay} onClick={() => onSend(it)}>Send to tray</button>
        </div>
      ))}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Panels
// ─────────────────────────────────────────────────────────────────────────

// 1 · Image
function ImagePanel() {
  const { add } = useTray();
  const [prompt, setPrompt] = useState("");
  const [reference, setReference] = useState(null);
  const [orient, setOrient] = useState("portrait");
  const [w, setW] = useState(1080);
  const [h, setH] = useState(1920);
  const [seed, setSeed] = useState("");
  const [steps, setSteps] = useState(20);
  const [cfg, setCfg] = useState(1.0);
  const [showAdv, setShowAdv] = useState(false);
  const [imgs, setImgs] = useState([]);
  const [st, setSt] = useState(null);

  function flip(o) {
    setOrient(o);
    if ((o === "portrait" && w > h) || (o === "landscape" && h > w)) { setW(h); setH(w); }
  }

  async function run() {
    if (!prompt.trim()) return setSt({ kind: "error", text: "Enter a prompt" });
    setSt({ kind: "running", text: "Generating…" }); setImgs([]);
    try {
      const fd = new FormData();
      fd.append("prompt", prompt); fd.append("width", w); fd.append("height", h); fd.append("orient", orient);
      if (seed !== "") fd.append("seed", seed);
      fd.append("steps", steps); fd.append("cfg", cfg);
      appendAsset(fd, "reference", reference);
      const r = await runJob("/image", fd, (s) => setSt({ kind: "running", text: s }));
      setImgs(r.images || []); setSt({ kind: "done", text: `${(r.images || []).length} image(s) ready` });
    } catch (e) { setSt({ kind: "error", text: String(e.message || e) }); }
  }

  return (
    <Panel title="Image" blurb="Generate a still from a prompt — a reference to feed anywhere below. Optionally guide it with a reference image.">
      <div style={S.grid2}>
        <AssetSlot label="Reference (optional)" hint="Guides the result" value={reference} onChange={setReference} accept="image" />
        <div style={S.fieldCol}>
          <label style={S.slotLabel}>Prompt</label>
          <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} style={S.textarea}
            placeholder="e.g. young woman, emerald silk saree, gold jhumka earrings, golden-hour light, 85mm, photoreal" />
        </div>
      </div>
      <div style={S.row}>
        <div style={S.fieldCol}>
          <label style={S.slotLabel}>Orientation</label>
          <div style={S.row}>
            <Pill active={orient === "portrait"} onClick={() => flip("portrait")}>Portrait</Pill>
            <Pill active={orient === "landscape"} onClick={() => flip("landscape")}>Landscape</Pill>
          </div>
        </div>
        <div style={S.fieldCol}><label style={S.slotLabel}>Width</label>
          <input type="number" step="32" value={w} onChange={(e) => setW(+e.target.value)} style={S.input} /></div>
        <div style={S.fieldCol}><label style={S.slotLabel}>Height</label>
          <input type="number" step="32" value={h} onChange={(e) => setH(+e.target.value)} style={S.input} /></div>
      </div>
      <button type="button" style={S.advToggle} onClick={() => setShowAdv((s) => !s)}>
        {showAdv ? "− Sampler settings" : "+ Sampler settings"}
      </button>
      {showAdv && (
        <div style={S.row}>
          <div style={S.fieldCol}><label style={S.slotLabel}>Seed (blank = random)</label>
            <input value={seed} onChange={(e) => setSeed(e.target.value)} placeholder="random" style={S.input} /></div>
          <div style={S.fieldCol}><label style={S.slotLabel}>Steps</label>
            <input type="number" value={steps} onChange={(e) => setSteps(+e.target.value)} style={S.input} /></div>
          <div style={S.fieldCol}><label style={S.slotLabel}>CFG</label>
            <input type="number" step="0.1" value={cfg} onChange={(e) => setCfg(+e.target.value)} style={S.input} /></div>
        </div>
      )}
      <div style={S.actionRow}>
        <button onClick={run} style={S.cta} disabled={st?.kind === "running"}>{st?.kind === "running" ? "Generating…" : "Generate image"}</button>
        <StatusLine status={st} />
      </div>
      <Gallery items={imgs} onSend={(it) => add({ kind: "image", url: absUrl(it.url), assetId: it.asset_id, label: "generated image" })} />
    </Panel>
  );
}

// 2 · Character
function CharacterPanel() {
  const { add } = useTray();
  const [ref, setRef] = useState(null);
  const [prompt, setPrompt] = useState("");
  const [name, setName] = useState("");
  const [styleQ, setStyleQ] = useState("");
  const [set, setSet] = useState([]);
  const [st, setSt] = useState(null);

  async function run() {
    if (!ref) return setSt({ kind: "error", text: "Add a reference image" });
    if (!prompt.trim()) return setSt({ kind: "error", text: "Enter a character prompt" });
    setSt({ kind: "running", text: "Building character sheet…" }); setSet([]);
    try {
      const fd = new FormData();
      appendAsset(fd, "character", ref);
      fd.append("character_prompt", prompt);
      if (name) fd.append("name", name);
      if (styleQ) fd.append("style_quality", styleQ);
      const r = await runJob("/character", fd, (s) => setSt({ kind: "running", text: s }));
      setSet(r.character_set || []); setSt({ kind: "done", text: "Character set ready" });
    } catch (e) { setSt({ kind: "error", text: String(e.message || e) }); }
  }

  return (
    <Panel title="Character" blurb="Turn one reference into a consistent character sheet — faces, poses, expressions.">
      <div style={S.grid2}>
        <AssetSlot label="Reference" hint="Face or full-body" value={ref} onChange={setRef} accept="image" />
        <div style={S.fieldCol}>
          <label style={S.slotLabel}>Character prompt</label>
          <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} style={S.textarea}
            placeholder="e.g. a woman, dark hair, grey wool turtleneck, brown eyes" />
          <div style={S.row}>
            <div style={S.fieldCol}><label style={S.slotLabel}>Name (optional)</label>
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder="character name" style={S.input} /></div>
          </div>
          <div style={S.fieldCol}><label style={S.slotLabel}>Style + quality (optional)</label>
            <input value={styleQ} onChange={(e) => setStyleQ(e.target.value)} placeholder="e.g. masterpiece, shot on iphone" style={S.input} /></div>
        </div>
      </div>
      <div style={S.actionRow}>
        <button onClick={run} style={S.cta} disabled={st?.kind === "running"}>{st?.kind === "running" ? "Working…" : "Generate character"}</button>
        <StatusLine status={st} />
      </div>
      <Gallery items={set} onSend={(it) => add({ kind: "image", url: absUrl(it.url), assetId: it.asset_id, label: "character still" })} />
    </Panel>
  );
}

// 3 · Video
function VideoPanel() {
  const { add } = useTray();
  const [character, setCharacter] = useState(null);
  const [outfit, setOutfit] = useState(null);
  const [product, setProduct] = useState(null);
  const [background, setBackground] = useState(null);
  const [character2, setCharacter2] = useState(null);
  const [prompt, setPrompt] = useState("");
  const [orient, setOrient] = useState("portrait");
  const [sizeIdx, setSizeIdx] = useState(11); // 928x1664-ish default (starred)
  const [duration, setDuration] = useState(5);
  const [video, setVideo] = useState(null);
  const [st, setSt] = useState(null);

  const sizeFor = (i) => { const [lw, lh] = VIDEO_SIZES[i]; return orient === "portrait" ? [lh, lw] : [lw, lh]; };

  async function run() {
    if (!character) return setSt({ kind: "error", text: "Add a character image" });
    setSt({ kind: "running", text: "Rendering video…" }); setVideo(null);
    try {
      const [w, h] = sizeFor(sizeIdx);
      const fd = new FormData();
      appendAsset(fd, "character", character);
      appendAsset(fd, "outfit", outfit);
      appendAsset(fd, "product", product);
      appendAsset(fd, "background", background);
      appendAsset(fd, "character2", character2);
      fd.append("prompt", prompt); fd.append("width", w); fd.append("height", h);
      fd.append("orient", orient); fd.append("duration", duration);
      const r = await runJob("/video", fd, (s) => setSt({ kind: "running", text: s }));
      setVideo(r); setSt({ kind: "done", text: `${duration}s video ready` });
    } catch (e) { setSt({ kind: "error", text: String(e.message || e) }); }
  }

  return (
    <Panel title="Video" blurb="Put the character in a scene with outfit, product and background. Five reference slots.">
      <div style={S.grid5}>
        <AssetSlot label="Character" value={character} onChange={setCharacter} accept="image" />
        <AssetSlot label="Outfit" value={outfit} onChange={setOutfit} accept="image" />
        <AssetSlot label="Product" value={product} onChange={setProduct} accept="image" />
        <AssetSlot label="Background" value={background} onChange={setBackground} accept="image" />
        <AssetSlot label="2nd character" hint="Optional" value={character2} onChange={setCharacter2} accept="image" />
      </div>
      <div style={S.fieldCol}>
        <label style={S.slotLabel}>Scene prompt</label>
        <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} style={S.textarea}
          placeholder="e.g. she holds the product to camera, warm studio light, label facing forward" />
      </div>
      <div style={S.row}>
        <div style={S.fieldCol}>
          <label style={S.slotLabel}>Orientation</label>
          <div style={S.row}>
            <Pill active={orient === "portrait"} onClick={() => setOrient("portrait")}>Portrait</Pill>
            <Pill active={orient === "landscape"} onClick={() => setOrient("landscape")}>Landscape</Pill>
          </div>
        </div>
        <div style={S.fieldCol}>
          <label style={S.slotLabel}>Size</label>
          <select value={sizeIdx} onChange={(e) => setSizeIdx(+e.target.value)} style={S.select}>
            {VIDEO_SIZES.map(([lw, lh], i) => {
              const [w, h] = orient === "portrait" ? [lh, lw] : [lw, lh];
              const key = `${lh}x${lw}`; // starred keyed as portrait w×h in the source
              const starred = VIDEO_STARRED.has(`${Math.min(w,h)}x${Math.max(w,h)}`);
              return <option key={i} value={i}>{w} × {h}{starred ? "  ★" : ""}</option>;
            })}
          </select>
        </div>
      </div>
      <div style={S.fieldCol}>
        <label style={S.slotLabel}>Duration</label>
        <div style={S.rowWrap}>
          {DURATIONS.map((d) => <Pill key={d} active={duration === d} onClick={() => setDuration(d)}>{d}s</Pill>)}
        </div>
      </div>
      <div style={S.actionRow}>
        <button onClick={run} style={S.cta} disabled={st?.kind === "running"}>{st?.kind === "running" ? "Rendering…" : "Generate video"}</button>
        <StatusLine status={st} />
      </div>
      {video?.video && (
        <div style={S.outBox}>
          <video key={video.video} src={absUrl(video.video)} controls style={S.video} />
          <button style={S.sendBtn} onClick={() => add({ kind: "video", url: absUrl(video.video), assetId: video.asset_id, label: `${duration}s scene` })}>Send to tray</button>
        </div>
      )}
    </Panel>
  );
}

// 4 · Lip-sync
function LipSyncPanel() {
  const { add } = useTray();
  const [face, setFace] = useState(null);
  const [aud, setAud] = useState(null);
  const [prompt, setPrompt] = useState("");
  const [duration, setDuration] = useState(5);
  const [longest, setLongest] = useState(864);
  const [ratio, setRatio] = useState("keep");
  const [talking, setTalking] = useState(null);
  const [st, setSt] = useState(null);

  async function run() {
    if (!face) return setSt({ kind: "error", text: "Add a face image" });
    if (!aud) return setSt({ kind: "error", text: "Add an audio file" });
    setSt({ kind: "running", text: "Syncing lips to audio…" }); setTalking(null);
    try {
      const fd = new FormData();
      appendAsset(fd, "face", face);
      appendAsset(fd, "audio", aud);
      if (prompt) fd.append("prompt", prompt);
      fd.append("duration", duration); fd.append("longest_side", longest); fd.append("ratio", ratio);
      const r = await runJob("/lipsync", fd, (s) => setSt({ kind: "running", text: s }));
      setTalking(r); setSt({ kind: "done", text: "Closeup ready" });
    } catch (e) { setSt({ kind: "error", text: String(e.message || e) }); }
  }

  return (
    <Panel title="Lip-sync" blurb="Sync a face to an audio file for a talking or singing closeup.">
      <div style={S.grid2}>
        <AssetSlot label="Face" hint="Front-facing" value={face} onChange={setFace} accept="image" />
        <AssetSlot label="Audio" hint="Upload a voice file" value={aud} onChange={setAud} accept="audio" />
      </div>
      <div style={S.fieldCol}>
        <label style={S.slotLabel}>Prompt (optional)</label>
        <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} style={S.textarea}
          placeholder="e.g. she faces the camera and delivers the line warmly, lip-synced to the audio" />
      </div>
      <div style={S.row}>
        <div style={S.fieldCol}>
          <label style={S.slotLabel}>Longest side</label>
          <div style={S.rowWrap}>{LONGEST_SIDES.map((s) => <Pill key={s} active={longest === s} onClick={() => setLongest(s)}>{s}</Pill>)}</div>
        </div>
      </div>
      <div style={S.row}>
        <div style={S.fieldCol}>
          <label style={S.slotLabel}>Aspect ratio</label>
          <div style={S.rowWrap}>{RATIOS.map((r) => <Pill key={r} active={ratio === r} onClick={() => setRatio(r)}>{r}</Pill>)}</div>
        </div>
        <div style={S.fieldCol}>
          <label style={S.slotLabel}>Duration</label>
          <div style={S.rowWrap}>{DURATIONS.map((d) => <Pill key={d} active={duration === d} onClick={() => setDuration(d)}>{d}s</Pill>)}</div>
        </div>
      </div>
      <div style={S.actionRow}>
        <button onClick={run} style={S.cta} disabled={st?.kind === "running"}>{st?.kind === "running" ? "Syncing…" : "Generate closeup"}</button>
        <StatusLine status={st} />
      </div>
      {talking?.talking_clip && (
        <div style={S.outBox}>
          <video key={talking.talking_clip} src={absUrl(talking.talking_clip)} controls style={S.video} />
          <button style={S.sendBtn} onClick={() => add({ kind: "video", url: absUrl(talking.talking_clip), assetId: talking.asset_id, label: "talking closeup" })}>Send to tray</button>
        </div>
      )}
    </Panel>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Tray rail
// ─────────────────────────────────────────────────────────────────────────
function TrayRail() {
  const { assets, remove, clear } = useTray();
  return (
    <aside style={S.rail}>
      <div style={S.railHead}><span style={S.railTitle}>Asset tray</span>
        {assets.length > 0 && <button style={S.railClear} onClick={clear}>Clear</button>}</div>
      {assets.length === 0 ? (
        <p style={S.railEmpty}>Nothing yet. Run any panel and send its output here — then feed it into any input slot.</p>
      ) : (
        <div style={S.railList}>
          {assets.map((a) => (
            <div key={a.id} style={S.railItem}>
              {a.kind === "image" ? <img src={a.url} alt={a.label} style={S.railThumb} />
                : <div style={S.railThumbAlt}><span style={S.kindTag}>{a.kind}</span></div>}
              <div style={S.railMeta}><span style={S.railLabel}>{a.label}</span><span style={S.railKind}>{a.kind}</span></div>
              <button style={S.railDel} onClick={() => remove(a.id)}>✕</button>
            </div>
          ))}
        </div>
      )}
    </aside>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// App
// ─────────────────────────────────────────────────────────────────────────
export default function AdStudio() {
  return (
    <TrayProvider>
      <div style={S.page}>
        <header style={S.header}>
          <div style={S.brandRow}><span style={S.brandMark}>▲</span><h1 style={S.brand}>Ad Studio</h1></div>
          <p style={S.lede}>Four workflows, run in any order. Each takes an upload or a tray asset and drops its result back for the next. Suggested path: image → character → video → lip-sync.</p>
          {DEMO_MODE && <div style={S.demoNote}>Demo mode is on — set <code>DEMO_MODE=false</code> and point <code>API_BASE</code> at your backend.</div>}
        </header>
        <div style={S.layout}>
          <main style={S.main}>
            <ImagePanel /><CharacterPanel /><VideoPanel /><LipSyncPanel />
            <footer style={S.footer}><span style={S.mono}>ad-studio</span> · modular pipeline over RunningHub</footer>
          </main>
          <TrayRail />
        </div>
      </div>
    </TrayProvider>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// helpers
// ─────────────────────────────────────────────────────────────────────────
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const absUrl = (u) => (!u ? u : u.startsWith("http") || u.startsWith("blob:") ? u : `${API_BASE}${u}`);

function appendAsset(fd, name, asset) {
  if (!asset) return;
  if (asset.file) fd.append(name, asset.file);
  else if (asset.assetId) fd.append(`${name}_ref`, asset.assetId);
  else if (asset.url) fd.append(`${name}_url`, asset.url);
}

async function runJob(path, formData, onStatus) {
  if (DEMO_MODE) {
    await sleep(1200);
    const demoImg = (n) => Array.from({ length: n }, (_, i) => ({ url: `https://picsum.photos/seed/${path}${i}/300/380`, asset_id: `demo${i}` }));
    if (path === "/image") return { images: demoImg(1) };
    if (path === "/character") return { character_set: demoImg(4) };
    if (path === "/video") return { video: "https://storage.googleapis.com/gtv-videos-bucket/sample/ForBiggerJoyrides.mp4", asset_id: "demoV" };
    return { talking_clip: "https://storage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4", asset_id: "demoT" };
  }
  const r = await fetch(`${API_BASE}${path}`, { method: "POST", body: formData });
  if (!r.ok) throw new Error(`${path} failed (${r.status})`);
  const { job_id } = await r.json();
  for (let i = 0; i < 400; i++) {
    const jr = await fetch(`${API_BASE}/jobs/${job_id}`);
    if (!jr.ok) throw new Error(`status check failed (${jr.status})`);
    const job = await jr.json();
    if (job.status === "DONE") return job;
    if (job.status === "FAILED") throw new Error(job.error || "job failed");
    onStatus?.(job.status || "working…");
    await sleep(3000);
  }
  throw new Error("timed out");
}

// ─────────────────────────────────────────────────────────────────────────
// styles
// ─────────────────────────────────────────────────────────────────────────
const S = {
  page: { minHeight: "100vh", background: "#0a0b0d", color: "#e7e9ec", fontFamily: "'Inter', system-ui, sans-serif", padding: "48px 24px 80px", maxWidth: 1180, margin: "0 auto" },
  header: { marginBottom: 32 },
  brandRow: { display: "flex", alignItems: "baseline", gap: 12 },
  brandMark: { color: accent, fontSize: 18 },
  brand: { fontSize: 26, fontWeight: 700, margin: 0, letterSpacing: "-0.02em" },
  lede: { color: "#9aa0a8", fontSize: 15, lineHeight: 1.55, maxWidth: 660, marginTop: 12 },
  demoNote: { marginTop: 16, padding: "10px 14px", borderRadius: 8, background: "#1a1508", border: "1px solid #3a2f10", color: "#d5a94f", fontSize: 13 },
  layout: { display: "grid", gridTemplateColumns: "1fr 300px", gap: 24, alignItems: "start" },
  main: { display: "flex", flexDirection: "column", gap: 16, minWidth: 0 },
  section: { background: "#101114", border: "1px solid #1e2024", borderRadius: 14, padding: 24 },
  sectionHead: { display: "flex", gap: 14, marginBottom: 20, alignItems: "flex-start" },
  sectionTitle: { fontSize: 18, fontWeight: 650, margin: 0 },
  sectionBlurb: { color: "#8a9098", fontSize: 13.5, margin: "4px 0 0", lineHeight: 1.4 },
  grid2: { display: "grid", gridTemplateColumns: "220px 1fr", gap: 18, marginBottom: 4 },
  grid5: { display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 12, marginBottom: 16 },
  fieldCol: { display: "flex", flexDirection: "column", gap: 8, flex: 1, marginTop: 12 },
  row: { display: "flex", gap: 12, alignItems: "flex-start" },
  rowWrap: { display: "flex", gap: 8, flexWrap: "wrap" },
  slotLabel: { fontSize: 12.5, color: "#9aa0a8", fontWeight: 550 },
  slot: { height: 150, borderRadius: 10, border: "1.5px dashed #2a2d33", display: "grid", placeItems: "center", overflow: "hidden", position: "relative" },
  slotImg: { width: "100%", height: "100%", objectFit: "cover" },
  slotFilled: { display: "grid", placeItems: "center", gap: 6, padding: 12, textAlign: "center" },
  slotMini: { color: "#9aa0a8", fontSize: 12 },
  slotHint: { color: "#5f656d", fontSize: 12.5, padding: 8, textAlign: "center" },
  slotBtns: { position: "absolute", bottom: 8, left: 8, right: 8, display: "flex", gap: 6, justifyContent: "center" },
  slotBtn: { background: "rgba(10,11,13,0.82)", border: "1px solid #2a2d33", color: "#cdd1d6", borderRadius: 7, padding: "5px 10px", fontSize: 11.5, cursor: "pointer" },
  slotBtnClear: { background: "rgba(10,11,13,0.82)", border: "1px solid #3a2020", color: "#d0554f", borderRadius: 7, padding: "5px 9px", fontSize: 11.5, cursor: "pointer" },
  kindTag: { fontFamily: "ui-monospace, monospace", fontSize: 10.5, color: accent, border: `1px solid ${accent}`, borderRadius: 5, padding: "2px 7px", textTransform: "uppercase" },
  picker: { position: "absolute", top: "100%", left: 0, right: 0, zIndex: 20, marginTop: 6, background: "#131417", border: "1px solid #2a2d33", borderRadius: 10, padding: 8, display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 6, maxHeight: 220, overflowY: "auto", boxShadow: "0 12px 30px rgba(0,0,0,0.5)" },
  pickerItem: { background: "#0c0d0f", border: "1px solid #24262b", borderRadius: 8, padding: 4, cursor: "pointer", display: "flex", flexDirection: "column", gap: 4, alignItems: "center" },
  pickerImg: { width: "100%", height: 56, objectFit: "cover", borderRadius: 5 },
  pickerKind: { fontFamily: "ui-monospace, monospace", fontSize: 10, color: accent, padding: "16px 0" },
  pickerLabel: { fontSize: 10.5, color: "#8a9098", textAlign: "center", lineHeight: 1.2 },
  textarea: { background: "#0c0d0f", border: "1px solid #24262b", borderRadius: 9, color: "#e7e9ec", padding: "11px 13px", fontSize: 14, lineHeight: 1.5, minHeight: 70, resize: "vertical", fontFamily: "inherit", outline: "none" },
  input: { background: "#0c0d0f", border: "1px solid #24262b", borderRadius: 9, color: "#e7e9ec", padding: "10px 12px", fontSize: 14, outline: "none", width: "100%", boxSizing: "border-box" },
  select: { background: "#0c0d0f", border: "1px solid #24262b", borderRadius: 9, color: "#e7e9ec", padding: "10px 12px", fontSize: 14, outline: "none" },
  advToggle: { alignSelf: "flex-start", marginTop: 14, background: "transparent", border: "none", color: accent, fontSize: 12.5, cursor: "pointer", padding: 0 },
  pill: { background: "#0c0d0f", border: "1px solid #24262b", borderRadius: 9, color: "#cdd1d6", padding: "8px 14px", fontSize: 13.5, cursor: "pointer", display: "flex", alignItems: "center", gap: 4 },
  pillActive: { borderColor: accent, color: accent, background: "#1a1508" },
  pillSub: { fontSize: 10.5, color: "#6b7280", fontFamily: "ui-monospace, monospace", marginLeft: 4 },
  star: { color: accent, fontSize: 11 },
  actionRow: { display: "flex", alignItems: "center", gap: 18, marginTop: 20 },
  cta: { background: accent, color: "#0a0b0d", border: "none", borderRadius: 9, padding: "11px 22px", fontSize: 14.5, fontWeight: 650, cursor: "pointer" },
  status: { display: "flex", alignItems: "center", gap: 8, fontSize: 13 },
  dot: { width: 7, height: 7, borderRadius: "50%" },
  mono: { fontFamily: "ui-monospace, monospace", fontSize: 12.5 },
  gallery: { display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginTop: 22 },
  galleryItem: { borderRadius: 10, overflow: "hidden", position: "relative", background: "#0c0d0f" },
  galleryImg: { width: "100%", height: 160, objectFit: "cover", display: "block" },
  sendOverlay: { position: "absolute", bottom: 8, left: "50%", transform: "translateX(-50%)", background: "rgba(10,11,13,0.85)", color: accent, border: `1px solid ${accent}`, fontSize: 11.5, fontWeight: 600, padding: "5px 12px", borderRadius: 20, cursor: "pointer", whiteSpace: "nowrap" },
  outBox: { marginTop: 20, display: "flex", flexDirection: "column", gap: 12 },
  sendBtn: { background: "transparent", color: accent, border: `1px solid ${accent}`, borderRadius: 8, padding: "8px 14px", fontSize: 12.5, fontWeight: 600, cursor: "pointer", alignSelf: "flex-start" },
  video: { width: "100%", borderRadius: 10, background: "#000" },
  rail: { position: "sticky", top: 24, background: "#101114", border: "1px solid #1e2024", borderRadius: 14, padding: 18, maxHeight: "calc(100vh - 48px)", overflowY: "auto" },
  railHead: { display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 },
  railTitle: { fontSize: 14, fontWeight: 650 },
  railClear: { background: "transparent", border: "none", color: "#6b7280", fontSize: 12, cursor: "pointer" },
  railEmpty: { color: "#5f656d", fontSize: 12.5, lineHeight: 1.5 },
  railList: { display: "flex", flexDirection: "column", gap: 8 },
  railItem: { display: "flex", gap: 10, alignItems: "center", padding: 8, background: "#0c0d0f", border: "1px solid #1e2024", borderRadius: 9 },
  railThumb: { width: 40, height: 40, objectFit: "cover", borderRadius: 6, flexShrink: 0 },
  railThumbAlt: { width: 40, height: 40, borderRadius: 6, display: "grid", placeItems: "center", background: "#131417", flexShrink: 0 },
  railMeta: { display: "flex", flexDirection: "column", gap: 2, flex: 1, minWidth: 0 },
  railLabel: { fontSize: 12.5, color: "#dfe2e6", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" },
  railKind: { fontSize: 10.5, color: "#6b7280", fontFamily: "ui-monospace, monospace" },
  railDel: { background: "transparent", border: "none", color: "#4b5058", fontSize: 13, cursor: "pointer", flexShrink: 0 },
  footer: { marginTop: 24, textAlign: "center", color: "#4b5058", fontSize: 12.5 },
};
