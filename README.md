# RoadEye

RoadEye is a real-time road-video intelligence system for detecting vehicles, estimating lane context, spotting near-miss situations, and preserving evidence. It combines computer vision, IPFS storage, and a Solana smart contract so the most severe incidents are not only saved as clips but also recorded on-chain.

## What It Does

- Detects vehicles in road video using a custom YOLOv8 model.
- Estimates relative distance and time-to-collision for each tracked vehicle.
- Detects lane geometry and overlays it on the processed video.
- Flags near-miss events with severity labels such as LOW, MEDIUM, HIGH, and CRITICAL.
- Buffers surrounding video frames and exports incident clips automatically.
- Uploads clips to IPFS through Pinata.
- Writes HIGH and CRITICAL incidents to Solana Devnet through an Anchor program.
- Exposes a Streamlit dashboard for uploading video, watching the live result, and reviewing clips/incidents.

## Project Layout

```text
.
├── contracts/
│   └── near_miss_registry/      # Anchor program and tests
├── dlbackend/                   # Flask API, CV pipeline, Pinata, Solana integration
│   ├── api/
│   ├── src/
│   └── frontend/                # Streamlit UI used with the backend
└── dlfrontend/                  # Standalone Streamlit frontend
```

## Main Features

### Video intelligence

- Vehicle detection with Ultralytics YOLOv8n custom weights.
- Lane detection with OpenCV line extraction and polygon overlays.
- Distance estimation from bounding-box width and a calibrated focal length.
- TTC-based risk scoring and severity classification.

### Incident handling

- Near-miss tracking with per-vehicle state across frames.
- Clip capture with pre-roll and post-roll buffering around events.
- Automatic upload of clips and metadata to Pinata IPFS.
- Local incident history with clip CIDs, timestamps, severity, and on-chain status.

### Blockchain recording

- Solana Devnet integration through AnchorPy.
- Anchor program `near_miss_registry` maintains a registry counter and immutable incident records.
- HIGH and CRITICAL events are submitted on-chain with the clip CID and detection metadata.

### User interface

- Streamlit dashboard with upload, start, stop, and live stream controls.
- Event cards for recent incidents and IPFS clip links.
- Status indicators for queued, running, completed, and failed jobs.

## How The System Works

1. A road video is uploaded from the Streamlit app.
2. The Flask backend processes the video frame by frame.
3. YOLO detects vehicles and OpenCV estimates lane structure.
4. The backend tracks approaching vehicles, estimates distance and TTC, and assigns a severity label.
5. When the risk threshold is met, the backend saves the surrounding frames as a clip.
6. The clip is uploaded to Pinata IPFS.
7. HIGH and CRITICAL incidents are also recorded on Solana Devnet.
8. The frontend shows the processed stream and incident history.

## Technology Stack

- Frontend: Streamlit
- Backend API: Flask
- Computer Vision: OpenCV, Ultralytics YOLOv8n
- Storage: IPFS via Pinata
- Blockchain: Solana Devnet with AnchorPy
- Smart Contract: Rust / Anchor

## Local Setup

### Backend

```bash
cd dlbackend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Create `dlbackend/.env` with the required secrets:

```env
PINATA_JWT=your_pinata_jwt
PROGRAM_ID=your_solana_program_id
REPORTER_PRIVATE_KEY=your_solana_private_key
CAMERA_ID=dashcam-001
PINATA_GATEWAY=https://your-gateway.mypinata.cloud/ipfs
SOLANA_RPC_URL=https://api.devnet.solana.com
```

Start the backend:

```bash
python api/app.py
```

### Frontend

In a second terminal:

```bash
cd dlfrontend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Create `dlfrontend/.env`:

```env
BACKEND_URL=http://localhost:5000
```

Run the UI:

```bash
streamlit run frontend/streamlit_app.py
```

### Optional: contract tests

The Anchor program lives in `contracts/near_miss_registry`. Use the usual Anchor workflow to build and test it against a local validator.

## API Endpoints

| Method | Path                 | Purpose                             |
| ------ | -------------------- | ----------------------------------- |
| `POST` | `/upload`            | Upload a video and create a job     |
| `POST` | `/start/<video_id>`  | Start processing the uploaded video |
| `GET`  | `/stream/<video_id>` | MJPEG stream of processed frames    |
| `POST` | `/stop/<video_id>`   | Stop a running job                  |
| `GET`  | `/status/<video_id>` | Return job status                   |
| `GET`  | `/clips/<video_id>`  | Return clips created for the job    |
| `GET`  | `/incidents`         | Return all recorded incidents       |

## Environment Variables

### Backend

- `PINATA_JWT`
- `PROGRAM_ID`
- `REPORTER_PRIVATE_KEY`
- `CAMERA_ID`
- `PINATA_GATEWAY`
- `SOLANA_RPC_URL`
- `RUNTIME_DATA_DIR` optional, overrides the temporary working directory for uploads and clips

### Frontend

- `BACKEND_URL`

## Deployment Notes

- The backend is designed to run in Docker on Hugging Face Spaces.
- The Streamlit frontend can be deployed separately on Streamlit Community Cloud.
- Production secrets should be stored in the host platform's secret manager instead of `.env` files.
