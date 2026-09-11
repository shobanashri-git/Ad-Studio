# Ad Studio — modular pipeline over RunningHub

Four independent workflows wrapped as a FastAPI backend + single-page React UI.
Run any panel in any order; outputs flow between panels through a shared asset tray.

Workflows: **image gen · character consistency · multi-image→video · image+audio lip-sync**
(all MiniMax H3 / Pixaroma graphs on RunningHub).

## Layout
```
adgen/
  runninghub.py    thin RunningHub client (upload/create/status/outputs/wait)
  config.py        per-workflow patch descriptors + node map + option lists
  patcher.py       loads exported workflow JSON, patches values, emits nodeInfoList
  orchestrator.py  the four operations (upload → patch → submit → wait → download)
  api.py           FastAPI: /image /character /video /lipsync, /jobs/{id}, /files/{name}
  stitch.py        ffmpeg helpers (unused by these workflows; kept for >15s later)
  workflows_*.json the exported API JSONs (source of truth for node IDs)
adgen-ui.jsx       the React UI (set DEMO_MODE=false, API_BASE to the backend)
```

## Setup
1. `pip install -r requirements.txt`  (fastapi, uvicorn, httpx, python-multipart)
2. Set env:
   ```
   export RH_API_KEY=...            # Personal+ tier
   export RH_BASE_URL=https://www.runninghub.ai   # or .cn for mainland
   export RH_WORKFLOW_IMAGE=...     # RunningHub workflowId for each workflow
   export RH_WORKFLOW_CHARACTER=...
   export RH_WORKFLOW_VIDEO=...
   export RH_WORKFLOW_LIPSYNC=...
   ```
3. Two placeholders still to fill:
   - `config.py` → VIDEO `character2` patch: set the **5th ref-image loader nodeId**
     once you add it in RunningHub (currently `REPLACE_5TH_LOADER_NODE`).
   - The four `RH_WORKFLOW_*` ids above (from each workflow's RunningHub page).
4. Run: `uvicorn adgen.api:app --reload`
5. UI: set `DEMO_MODE = false` and `API_BASE` in `adgen-ui.jsx`, drop it into a React app.

## How inputs map (the important part)
These Pixaroma nodes store values inside JSON-string "state" blobs, not plain
fields. `patcher.py` loads the exported graph and rewrites the right blob key or
plain field, then sends only the changed nodes as RunningHub node overrides.
Model/CLIP/VAE/sampler settings ride along from the export unchanged.

- **image**: prompt→node 244 (PromptState.text), width/height→241, seed/steps/cfg→225 (KSampler)
- **character**: face→LoadImage 626, prompt→String Literal 594, name→471, style+quality→608
- **video**: refs→loaders 236/238/240/241(+5th), prompt→239, duration→234 (seconds), size→223 (SizesState index)
- **lipsync**: face→236, audio→247 (LoadAudioState.file), prompt→239, duration→234, longest-side+ratio→243

Duration→frames is computed by the workflow's own duration node (nonlinear,
~24fps), so the backend only sets `seconds` — no beat-stitching needed.

## Notes
- Job + asset store are in-memory (single user). Move to Redis/DB for production.
- Outputs are downloaded to a temp dir and served at `/files/...`; push to real
  storage for production.
- Tray references: the UI sends `<name>_ref=<asset_id>` for tray picks; the
  backend resolves them to local paths and re-uploads to RunningHub.
