# Cocoa Vision
A cashier-facing point-of-sale command center for packing chocolate boxes. Cocoa Vision listens to a cashier calling out flavors as they pack a box, weighs the box on a scale, and automatically reconciles the two — flagging a mismatch if the spoken count doesn't match what's on the scale, and auto-committing the box once they agree.

## How it works

1. A cashier picks a box size (6, 10, 16, 30, or 50 pieces) and taps **Start New Box**.
2. Cocoa Vision starts listening via a live speech-to-text stream (AssemblyAI) and picks out flavor names from the house catalog as they're spoken.
3. The scale reports its weight (in production, from real scale hardware; in this build, via simulate buttons for testing).
4. Once both a voice count and a scale weight are present, Cocoa Vision compares piece counts:
   - **Match** → the box is auto-saved and logged.
   - **Voice count higher than scale count** → flagged as a mismatch for the cashier to review.
   - **Voice count lower than scale count** → stays in a buffering state, waiting for more spoken items.

## Project structure
```
.
├── frontend/
└── backend/
```

## Tech stack

- **Frontend:** React, Vite, Tailwind CSS
- **Voice:** [AssemblyAI](https://www.assemblyai.com/) real-time streaming transcription
- **Backend:** Node.js — issues short-lived AssemblyAI tokens so the API key never reaches the browser

## Getting started

### Backend

```bash
cd backend
npm install
cp .env.example .env   # then add your AssemblyAI API key
npm start
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Configuration

Key constants live near the top of `frontend/src/components/cocoa-vision.jsx`:

| Constant | Purpose |
|---|---|
| `BOX_SIZE_OPTIONS` | Selectable box sizes shown to the cashier |
| `PIECE_WEIGHT` | Nominal weight (g) used to derive piece count from scale weight |
| `WEIGHT_TOLERANCE_G` | Allowed drift between itemized voice weight and scale weight before it's flagged |
| `STARTING_BOX_NUMBER` | First box number of the shift; auto-increments from there |

The flavor menu lives separately in `frontend/src/components/constants/flavorCatalog.js` — add, remove, or reweight flavors there without touching component code.