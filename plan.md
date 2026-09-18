<!-- 64d686b3-54f0-47cc-a979-9e2b7c0c7f12 -->
---
todos:
  - id: "scaffold-merge"
    content: "Populate the destination with the combined runtime structure and shared configuration"
    status: completed
  - id: "unify-backend"
    content: "Add AssemblyAI token minting and combined auditable order persistence to Flask"
    status: completed
  - id: "integrate-workflow"
    content: "Build the voice-to-camera state flow and replace the scale panel with live camera"
    status: completed
  - id: "build-review"
    content: "Implement per-item voice/CV comparison, inline status icons, and editable final list"
    status: completed
  - id: "theme-ui"
    content: "Apply the navy/gold Chocolate Vision design across the merged Cocoa Vision layout"
    status: completed
  - id: "verify-docs"
    content: "Test the merged workflow and document setup, storage, and operation"
    status: completed
isProject: false
---
# Merge voice and camera verification

## 1. Establish the combined repository
- Populate `[D:\Chocolathon\Chocoa-Vision](D:\Chocolathon\Chocoa-Vision)` from the reusable runtime pieces of both projects without changing either source repository or copying their `.git`, generated datasets, model runs, captures, secrets, or dependency folders.
- Use the Chocolate Vision structure: `[backend/app.py](D:\Chocolathon\Chocoa-Vision\backend\app.py)`, `[frontend](D:\Chocolathon\Chocoa-Vision\frontend)`, `[pipeline](D:\Chocolathon\Chocoa-Vision\pipeline)`, root launcher, labels, requirements, and ignore rules. Retain the destination repository’s existing remote/history.
- Bring over Cocoa Vision’s voice hook, PCM worklet, transcript parser, box state concepts, controls, log/analytics components, and AssemblyAI environment setup.

## 2. Consolidate services and flavor data
- Extend the Flask app in `[backend/app.py](D:\Chocolathon\Chocoa-Vision\backend\app.py)` with `/api/assemblyai-token`, minting a short-lived AssemblyAI v3 token server-side from `SPEECH_TO_TEXT_API_KEY`; this removes the need to run the separate Express token server while keeping the existing browser streaming hook.
- Make `[labels.json](D:\Chocolathon\Chocoa-Vision\labels.json)` the shared catalog for camera output, transcript matching, dropdowns, and display names. Refactor the transcript parser to consume that catalog and preserve aliases where spoken wording differs from the trained class label.
- Keep the YOLO scan endpoint, photo storage, flavor endpoint, and order endpoints from Chocolate Vision.

## 3. Replace the scale workflow with camera verification
- Refactor Cocoa Vision’s packing state into explicit `idle → listening → scanning → review → saving/saved` phases.
- **Start New Box** clears prior draft state, starts the timer, and starts AssemblyAI recording through the existing mic hook.
- Replace `[ScalePanel.jsx](D:\Chocolathon\cocoa-vision\frontend\src\components\ScalePanel.jsx)` in the left half of the Cocoa Vision layout with a reusable live `CameraPanel`: working-camera probing, full-bleed preview without side bars, camera switching/retry, and native-resolution capture from Chocolate Vision.
- Add one primary **Finish recording and scan box** action. It will finalize/flush pending voice transcription, stop the mic, capture the current frame, upload it to `/api/scan`, and enter review. Disable repeated submissions and expose microphone/camera/API failures inline.

## 4. Compare voice and CV results
- Add a pure comparison utility that normalizes both sources by flavor slug and quantity, producing an overall `match`/`mismatch` plus per-flavor states: exact match, quantity mismatch, voice-only, or camera-only.
- The Review section starts from the voice list, as requested. Each voice row gets a clear status icon and camera quantity; camera-only detections appear in a separate mismatch callout so they cannot be silently omitted.
- Preserve the original CV prediction as read-only evidence. Cashier edits affect only the corrected/final voice list, and comparison badges recalculate against that unchanged prediction.
- Reuse/adapt the item editor for quantity changes, flavor swaps, additions, and removals. Keep all mismatch messaging inline—no browser popups.

## 5. Save auditable combined orders
- Extend order records to retain box size, transcript-derived items, original CV items, cashier-corrected final items, overall comparison status, timestamps/pack time, and the saved original/annotated image ID.
- Save only when the cashier explicitly confirms the reviewed list. Drive the order log and insights from persisted API records rather than Cocoa Vision’s browser-only local storage, while retaining edit and photo re-verification actions.
- Keep the Chocolate Vision CSV/image approach, with backward-compatible parsing for any older rows where practical.

## 6. Apply the Chocolate Vision visual system
- Use `[frontend/src/index.css](D:\Chocolathon\Chocolate Vision\frontend\src\index.css)` as the theme source: navy/deep-navy background, gold actions, paper cards, ink/muted text, and serif/sans typography.
- Restyle the imported Cocoa Vision header, status, voice panel, controls, review, order log, and insights consistently; preserve its compact two-panel composition with camera on the left and live spoken flavors on the right.
- Make the layout responsive so camera and voice stack cleanly on narrow displays and primary cashier controls remain prominent.

## 7. Verify and document
- Add focused tests for transcript normalization and voice/CV comparison edge cases, then run frontend tests, lint, and production build.
- Run Python syntax checks and Flask API smoke checks for token configuration errors, flavor loading, scan/order validation, and photo routes.
- Manually exercise the hardware flow where available: box size → start recording → live transcript → finish/scan → matching and mismatching review → edit → save → reopen photo.
- Rewrite `[README.md](D:\Chocolathon\Chocoa-Vision\README.md)` with architecture, environment variables, model-weight placement, setup/run commands, merged workflow, storage schema, and known hardware/network requirements.