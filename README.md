# Interview Prep — AI Interview Simulator

A production-grade technical interview simulation and communication intelligence platform. The system conducts realistic, multi-turn technical interviews across Software Engineering domains (Python, Databases & SQL, System Design, and Behavioral), evaluates candidate responses, extracts speech and nonverbal telemetry, and provides evidence-based coaching and longitudinal analytics.

The application is built on a Python FastAPI backend, an embedded SQLite database with Write-Ahead Logging (WAL), and a dependency-free vanilla HTML5/CSS3/JavaScript Single-Page Application (SPA) frontend styled with a dark LeetCode-Problemset-inspired design system.

---

## Table of Contents

- [Key Capabilities](#key-capabilities)
- [System Architecture](#system-architecture)
- [Technology Stack](#technology-stack)
- [Repository Structure](#repository-structure)
- [Configuration & Environment Variables](#configuration--environment-variables)
- [Local Development Setup](#local-development-setup)
- [Testing & Quality Assurance](#testing--quality-assurance)
- [API Reference Overview](#api-reference-overview)
- [Production Architecture & Operations](#production-architecture--operations)
- [Privacy, Security & Responsible AI](#privacy-security--responsible-ai)

---

## Key Capabilities

### 1. Multi-Turn Conversational Interview Engine
- Conducts adaptive multi-turn technical interviews with configurable depth (1 to 10 turns).
- Supports customizable interviewer personas (`professional`, `supportive`, `challenging`, `concise`), experience levels (`junior`, `mid`, `senior`, `lead`), and target job roles.
- Dynamic conversational branching: generates contextual follow-up questions when candidate answers reveal gaps, ambiguities, or shallow technical depth.

### 2. Structured Resume & Job Description Probing
- Ingests candidate resumes and job descriptions concurrently via `document_processor.py`.
- Extracts verified technical skills, project facts, metrics, and architecture claims with automated PII sanitization.
- Generates targeted technical probing questions that challenge candidate claims, implementation tradeoffs, and system scale.

### 3. Standalone Single Question Practice
- Curated question catalog covering Python, Databases, System Design, and Behavioral topics across `easy`, `medium`, and `hard` difficulty tiers.
- Multi-dimensional technical evaluations providing numerical scores (1-10), technical correctness assessments, identified strengths, and missed concepts or edge cases.

### 4. Speech & Communication Intelligence
- Local, offline automatic speech recognition powered by `faster-whisper` (CTranslate2, `base.en`, CPU `int8` quantization).
- Acoustic waveform analysis: calculates total duration, speaking duration, pause duration, pause count, average pause duration, long pauses (>= 1.5s), and phonation ratio.
- Linguistic and delivery analysis: measures speaking rate (WPM), articulation rate (WPM), repeated words, and filler words (`um`, `uh`, `like`, `you know`, `actually`, `basically`, etc.).
- Deterministic delivery scoring (1-10) with actionable pacing and clarity recommendations.

### 5. Computer Vision & Nonverbal Telemetry
- Objective nonverbal telemetry extraction using MediaPipe Face Landmarker with OpenCV fallback.
- Client-side framing guide overlay with real-time face alignment guides.
- Extracts purely observable physical geometry: face detection ratio, centering offset, gaze/head-pose deviation (yaw, pitch, roll angles and variance), head motion frequency (Hz), and motion energy.
- Environmental camera quality checks (lighting conditions and resolution).
- **Strictly observable signals only**: zero emotion classification, zero sentiment profiling, and zero psychological inference.

### 6. Longitudinal Analytics, Replay & Coaching Reports
- Aggregates performance across sessions: technical scores, communication delivery scores, nonverbal telemetry scores, and categorical proficiencies.
- Interactive Session Replay: turn-by-turn breakdown of questions, candidate transcripts, audio/video metrics, and evaluator feedback.
- Evidence-based performance coaching: deterministic factual signals synthesized with Gemini recommendations into structured, actionable improvement plans.

### 7. Self-Managed Authentication & Session Authorization
- Self-managed user registration and authentication using `bcrypt` password hashing (minimum 8 characters) and email normalization.
- Stateless, cryptographically signed cookies via `itsdangerous` (`auth_token` for accounts, `guest_token` for guest sessions).
- Strict session ownership enforcement with non-disclosing 404 responses for unauthorized access.

---

## System Architecture

```text
+-----------------------------------------------------------------------------------+
|                                 Client Browser                                    |
|  - Vanilla HTML5 / Modern CSS3 / ES6+ JavaScript SPA (web/index.html)             |
|  - Web Audio API / MediaRecorder / HTML5 Canvas Camera Framing Guide              |
+-----------------------------------------+-----------------------------------------+
                                          | HTTPS / Cookie Auth
                                          v
+-----------------------------------------------------------------------------------+
|                              Reverse Proxy (Nginx)                                |
|  - TLS Termination (Let's Encrypt SSL)                                            |
|  - Reverse proxy to 127.0.0.1:8000                                                |
+-----------------------------------------+-----------------------------------------+
                                          | HTTP (Localhost)
                                          v
+-----------------------------------------------------------------------------------+
|                         Application Server (FastAPI / Uvicorn)                    |
|                                                                                   |
|  +-----------------------------------------------------------------------------+  |
|  | Concurrency Control: Process-Local Inference Gate (threading.Semaphore(1))   |  |
|  | - Serializes heavy CPU-bound ML inference (Whisper STT / MediaPipe Vision)  |  |
|  | - Prevents RAM exhaustion / OOM crashes on resource-constrained VM hosts    |  |
|  +-----------------------------------------------------------------------------+  |
|                                                                                   |
|  +-------------------------+ +-------------------------+ +---------------------+  |
|  |   Interview Engine      | |    Evaluator Engine     | |   Speech Engine     |  |
|  |   - Turn State Machine  | |    - Gemini Evaluator   | |   - faster-whisper  |  |
|  |   - Claim Probing       | |    - Heuristic Fallback | |   - Audio Analyzer  |  |
|  +-------------------------+ +-------------------------+ +---------------------+  |
|  +-------------------------+ +-------------------------+ +---------------------+  |
|  |   Vision Analyzer       | |    Document Processor   | |   Coaching Engine   |  |
|  |   - MediaPipe Landmarker| |    - Resume / JD Parser | |   - Evidence Signal |  |
|  |   - OpenCV Fallback     | |    - PII Sanitizer      | |   - Insights Engine |  |
|  +-------------------------+ +-------------------------+ +---------------------+  |
+-----------------------------------------+-----------------------------------------+
                                          |
                   +----------------------+----------------------+
                   |                                             |
                   v                                             v
+-------------------------------------+       +-------------------------------------+
|        External AI Services         |       |         Embedded Persistence        |
|  - Google Gemini API (google-genai) |       |  - SQLite 3 (WAL Mode)              |
|  - Default: gemini-3.6-flash        |       |  - Foreign Key Constraints Enabled  |
|  - Fallback: Heuristic Evaluators   |       |  - Atomic Online Backup API         |
+-------------------------------------+       +------------------+------------------+
                                                                 |
                                                                 v
                                              +-------------------------------------+
                                              |       Off-VM Backup Storage         |
                                              |  - Azure Blob Storage (Gzip)        |
                                              |  - Managed Identity Authentication  |
                                              +-------------------------------------+
```

---

## Technology Stack

| Layer | Technology | Details |
| :--- | :--- | :--- |
| **Frontend** | Vanilla HTML5, CSS3, JavaScript (ES6+) | Single-file SPA in `web/index.html`. Zero dependencies, zero build steps, zero node/npm requirements. |
| **Backend Framework** | FastAPI, Uvicorn, Starlette | Python asynchronous web framework with Pydantic v2 data validation and OpenAPI schema generation. |
| **Runtime** | Python 3.10–3.12 | Supported and validated Python runtime environment. |
| **Database** | SQLite 3 | Embedded database operating in Write-Ahead Logging (`WAL`) mode with `busy_timeout = 5000` and `synchronous = NORMAL`. |
| **AI / LLM** | Google Gemini API (`google-genai`) | Centralized configuration in `gemini_config.py`. Default model `gemini-3.6-flash` (configurable via `GEMINI_MODEL`). Context-aware deterministic heuristic fallback when API key is unavailable. |
| **Speech-to-Text** | `faster-whisper` | Fast, offline transcription using CTranslate2 (`base.en` model, CPU `int8` quantization). |
| **Audio Processing** | Python `wave`, `numpy` | Native standard-library waveform parsing, RMS energy calculation, and acoustic signal feature extraction. |
| **Computer Vision** | `mediapipe`, `opencv-python`, `av` | MediaPipe Face Landmarker task model with OpenCV fallback. Objective head-pose, gaze, and framing analysis. |
| **Authentication** | `bcrypt`, `itsdangerous` | Self-managed authentication: bcrypt password hashing (min 8 chars), stateless signed HTTP-only cookies. |
| **Hosting & OS** | Microsoft Azure VM (Standard_B2ats_v2) | Ubuntu 24.04 LTS in Korea Central region (`interview-simulator-vm-korea`). 2 GB persistent swapfile. |
| **Web Server** | Nginx | Reverse proxy handling TLS termination, client buffer management (50MB uploads), and HTTP/1.1 proxying. |
| **Process Management**| systemd | `interview-simulator.service` with auto-restart, unprivileged execution (`azureuser`), and sandboxing (`PrivateTmp=true`, `ProtectSystem=full`). |
| **Disaster Recovery** | `sqlite3.backup`, Azure Blob Storage | `scripts/backup_db.py`, `interview-backup.timer`, System-Assigned Managed Identity via `azure-identity`. |

---

## Repository Structure

```text
.
├── backend/
│   ├── __init__.py
│   ├── analytics.py             # Aggregate metrics, session history, and skill profiling
│   ├── audio_analyzer.py        # Waveform parsing, acoustic metrics, and delivery scoring
│   ├── auth.py                  # User authentication, bcrypt hashing, and signed cookies
│   ├── category_classifier.py   # Canonical category detection and status thresholds
│   ├── coaching.py              # Evidence-based coaching signals and action plan synthesis
│   ├── database.py              # SQLite connection pooling, WAL configuration, and schema migrations
│   ├── document_processor.py    # Resume/JD extraction, PII scrubbing, and claim parsing
│   ├── evaluator.py             # Gemini API answer evaluation and heuristic fallback analyzer
│   ├── gemini_config.py         # Centralized Gemini model identifier and configuration
│   ├── inference_gate.py        # Process-local concurrency semaphore protecting ML operations
│   ├── insights_engine.py       # Longitudinal trend analysis and performance insights
│   ├── interview_engine.py      # Multi-turn state machine, claim probing, and session flow
│   ├── interviewer.py           # Adaptive follow-up question generation
│   ├── main.py                  # FastAPI application, route declarations, and lifecycle hooks
│   ├── question_bank.py         # Question catalog storage, filtering, and database seeding
│   ├── question_data.py         # Static question seed dataset across domains and difficulty tiers
│   ├── speech_engine.py         # faster-whisper STT loading, caching, and transcription
│   ├── strategy_engine.py       # Conversational follow-up strategy rules
│   └── vision_analyzer.py       # MediaPipe/OpenCV nonverbal telemetry and geometry extraction
├── deploy/
│   ├── README.md                # Detailed production runbook and Azure deployment guide
│   ├── interview-backup.service # systemd oneshot backup service unit
│   ├── interview-backup.timer   # systemd timer for nightly automated backups (02:00 UTC)
│   ├── interview-simulator.service # systemd application service definition
│   ├── nginx-interview-simulator.conf # Nginx reverse proxy configuration template
│   └── setup_swap.sh            # Shell script creating and persisting 2 GB system swap
├── docs/                        # Architecture documentation, design specs, and roadmap
├── scripts/
│   └── backup_db.py             # Automated SQLite online backup, verification, and Azure Blob sync
├── tests/                       # Automated test suite (558 tests across all phases)
├── web/
│   └── index.html               # Complete frontend SPA application (HTML5, CSS3, ES6+ JS)
├── requirements.txt             # Pinned Python package dependencies
└── README.md                    # Project documentation
```

---

## Configuration & Environment Variables

The application is configured through environment variables or a local `.env` file in the project root.

| Variable | Type | Default | Description | Required |
| :--- | :--- | :--- | :--- | :--- |
| `GEMINI_API_KEY` | `string` | *None* | Google Gemini API key used for evaluation, question probing, document extraction, and coaching. When omitted, deterministic heuristic fallbacks activate automatically. | Optional (Dev) / Recommended (Prod) |
| `GEMINI_MODEL` | `string` | `gemini-3.6-flash` | Model identifier used for all Gemini LLM calls. | Optional |
| `DATABASE_PATH` | `string` | `backend/interview.db` | Filesystem path to the SQLite database file (e.g., `/data/interview.db` in production). Set to `:memory:` for in-memory testing. | Optional |
| `AUTH_SECRET_KEY` | `string` | `dev-auth-secret-...` | Cryptographic secret key used to sign stateless authentication and guest cookies. In production mode, startup fails if this is unset. | Required in Production |
| `ENVIRONMENT` | `string` | `development` | Operating environment (`development` or `production`). Can also be set via `APP_ENV`, `ENV`, or `PRODUCTION=true`. | Optional |
| `COOKIE_SECURE` | `boolean` | `false` | When set to `true`, session cookies require HTTPS (`Secure` flag). Set to `true` in production with TLS. | Recommended in Prod |
| `FRONTEND_ORIGIN` | `string` | *Localhost list* | Comma-separated list of allowed origins for CORS. In production, defaults to an empty list unless explicitly specified. | Optional |
| `UVICORN_WORKERS` | `integer` | `1` | Number of Uvicorn worker processes. Must be `1` in production to enforce process-local inference concurrency protection. | Required <= 1 in Prod |
| `INFERENCE_GATE_TIMEOUT`| `float` | `30.0` | Timeout in seconds for acquiring the ML inference semaphore before returning HTTP 503 Service Unavailable. | Optional |
| `WHISPER_MODEL_SIZE` | `string` | `base.en` | Model size for `faster-whisper` (`tiny.en`, `base.en`, `small.en`, `medium.en`). | Optional |
| `WHISPER_DEVICE` | `string` | `cpu` | Device for Whisper inference (`cpu` or `cuda`). | Optional |
| `WHISPER_COMPUTE_TYPE` | `string` | `int8` | Computation quantization type for Whisper (`int8`, `float16`, `float32`). | Optional |
| `AZURE_STORAGE_ACCOUNT` | `string` | *None* | Azure Storage Account name used by `backup_db.py` to replicate database backups to cloud blob storage. | Optional (Backups) |
| `AZURE_STORAGE_CONTAINER` | `string` | `interview-backups` | Target container name in Azure Blob Storage for database backups. | Optional (Backups) |

---

## Local Development Setup

### Prerequisites
- Python 3.10–3.12 (validated for MediaPipe, faster-whisper, and PyAV binary compatibility)
- Git
- Modern web browser (Chrome, Edge, Firefox, or Safari) with microphone and camera permissions for audio/video features
- *(Node.js, npm, or frontend bundlers are NOT required)*

### 1. Clone the Repository
```bash
git clone https://github.com/AkshitBedi/Ai-Interview-Simulator.git
cd Ai-Interview-Simulator
```

### 2. Create and Activate a Virtual Environment
```bash
# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate

# Windows (PowerShell)
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Install Python Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure Environment Variables (Optional)
Create a `.env` file in the root directory:
```bash
# Optional: Provide your Gemini API key for full AI evaluation
GEMINI_API_KEY=your_gemini_api_key_here

# Optional: Override the Gemini model (defaults to gemini-3.6-flash)
GEMINI_MODEL=gemini-3.6-flash

# Authentication secret for development (falls back to a default dev key if unset)
AUTH_SECRET_KEY=local-development-secret-key-32-chars-long
```

### 5. Launch the Application
Start the Uvicorn ASGI server:
```bash
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

Database tables and initial question bank seeds are automatically initialized on application startup via `create_tables()`.

### 6. Access the Application
Open your browser and navigate to:
```text
http://127.0.0.1:8000
```
- The frontend SPA is served directly at the root URL `/`.
- Interactive API documentation (Swagger UI) is available at `/docs`.
- Alternate API documentation (ReDoc) is available at `/redoc`.

---

## Testing & Quality Assurance

The codebase includes an extensive automated test suite implemented using Python's standard-library `unittest` framework. The suite covers unit logic, integration pipelines, database migrations, authentication isolation, and API contract invariants.

### Run the Full Test Suite
```bash
python -m unittest discover -s tests -p "test_*.py"
```

### Test Suite Structure
- `tests/test_phase1_database.py` — Database schema, connection pooling, and CRUD operations.
- `tests/test_phase2_evaluator.py` — Evaluation scoring, heuristic fallbacks, and Gemini API integration.
- `tests/test_phase3_interview_engine.py` — Multi-turn conversation state machine and turn transitions.
- `tests/test_phase4_speech_analytics.py` — Waveform acoustic metrics, pause detection, WPM, and delivery scoring.
- `tests/test_phase5_vision_analytics.py` — Nonverbal telemetry, centering, head pose, and motion energy.
- `tests/test_phase6_analytics.py` — Longitudinal progress tracking and aggregate metrics.
- `tests/test_phase7_frontend_contract.py` — REST API contracts and payload response shapes.
- `tests/test_phase8_interview_flow.py` — End-to-end interview lifecycle and turn transitions.
- `tests/test_phase9_coaching.py` — Evidence-based coaching signals and action plan generation.
- `tests/test_phase10_question_catalog.py` — Question bank filtering, difficulty tiers, and metadata parsing.
- `tests/test_phase11_configuration.py` — Session configuration normalization and style validation.
- `tests/test_phase12_document_processor.py` — Resume and job description parsing, PII sanitization.
- `tests/test_phase13_claim_probing.py` — Targeted claim extraction and adversarial follow-up generation.
- `tests/test_phase14_insights.py` — Longitudinal insights engine and progress trend analysis.
- `tests/test_phase15_session_replay.py` — Turn-by-turn session replay and telemetry playback.
- `tests/test_phase16_auth.py` — User registration, login, signed cookies, and session authorization.
- `tests/test_phase17_production_hardening.py` — Concurrency gate, memory guards, and worker configuration.
- `tests/test_phase17_1_cloud_backup.py` — SQLite online backup, verification, and Azure Blob synchronization.
- `tests/test_phase18_frontend_integration.py` — Frontend contract integration and DOM element validation.
- `tests/test_phase18b_session_start.py` — Session start payload structures and backward compatibility.

---

## API Reference Overview

### Health & System
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/` | Serves the Single-Page Application (`web/index.html`). |
| `GET` | `/health` | Verifies database connectivity and service availability. |
| `GET` | `/stats` | Returns overall database record statistics (counts of questions, answers, evaluations). |

### Authentication & Account
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/auth/register` | Registers a new user account with bcrypt password hashing; sets signed `auth_token` cookie. |
| `POST` | `/auth/login` | Authenticates credentials and sets signed `auth_token` cookie. |
| `POST` | `/auth/logout` | Clears account cookie. |
| `GET` | `/auth/me` | Returns the current authenticated user profile or guest status. |
| `GET` | `/account/interviews` | Lists interview sessions owned by the authenticated user. |

### Questions & Single Answer Practice
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/questions` | Queries question catalog with optional filtering by `category`, `difficulty`, `limit`, and `offset`. |
| `GET` | `/questions/random` | Returns a random question matching optional category and difficulty filters. |
| `GET` | `/questions/{id}` | Retrieves a specific question by ID. |
| `POST` | `/answers` | Submits an answer for single-question evaluation (returns score, feedback, technical accuracy, strengths, missing points). |
| `GET` | `/answers/{id}/feedback` | Retrieves stored evaluation feedback for an answer. |

### Multi-Turn Interview Sessions
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/sessions` | Initializes an interview session. Accepts JSON payload or `multipart/form-data` with resume and JD files. |
| `GET` | `/sessions/{id}` | Retrieves current session state, active turn, and progress. |
| `POST` | `/sessions/{id}/answer` | Submits a text answer for the active turn; advances session state and generates next question or follow-up. |
| `POST` | `/sessions/{id}/answer-audio` | Submits an audio recording (`multipart/form-data`); transcribes speech, extracts acoustic metrics, and advances session. |
| `POST` | `/sessions/{id}/answer-multimodal`| Submits video and/or audio files; runs multimodal pipeline (STT, acoustic analysis, nonverbal telemetry) and advances session. |
| `GET` | `/sessions/{id}/summary` | Generates comprehensive end-of-session evaluation report across all turns. |
| `GET` | `/sessions/{id}/replay` | Returns complete turn-by-turn session replay data including transcripts, audio metrics, and visual telemetry. |
| `GET` | `/sessions/{id}/coaching` | Generates structured performance coaching report with prioritized action items. |

### Speech & Vision Intelligence
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/speech/status` | Returns Speech-to-Text engine availability and loaded Whisper model metadata. |
| `POST` | `/speech/analyze` | Analyzes an uploaded audio file and transcript for delivery metrics and scoring. |
| `GET` | `/vision/status` | Returns Computer Vision backend status (`mediapipe`, `opencv`, or unavailable). |
| `POST` | `/vision/analyze` | Analyzes uploaded video for nonverbal telemetry (face presence, centering, gaze, motion). |

### Longitudinal Analytics
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/analytics/overview` | Retrieves aggregate metrics, category breakdowns, and performance percentiles. |
| `GET` | `/analytics/history` | Retrieves chronological session performance history. |
| `GET` | `/analytics/insights` | Generates AI-synthesized longitudinal progress insights and growth trajectory. |

---

## Production Architecture & Operations

The application is deployed on a dedicated Azure Linux VM in the Korea Central region.

### Production Runtime Invariants
1. **Single Uvicorn Worker**: The application executes under Uvicorn with `--workers 1`. This enforces the process-local `threading.Semaphore(1)` inference gate in `backend/inference_gate.py`, ensuring that heavy ML operations (Whisper STT and MediaPipe) execute sequentially.
2. **Swapfile Protection**: A 2 GB persistent swapfile (`/swapfile`) with `vm.swappiness=10` ensures memory stability on the production virtual machine host (Azure Standard_B2ats_v2).
3. **Database Isolation & WAL Mode**: Production persistence resides at `/data/interview.db` using SQLite's Write-Ahead Logging mode. This enables concurrent readers while a single writer commits, preventing thread contention.
4. **Automated Online Backups**: Automated nightly backups run via systemd timer (`interview-backup.timer`) at 02:00 UTC. The backup utility (`scripts/backup_db.py`):
   - Uses the non-blocking `sqlite3.Connection.backup()` API.
   - Verifies structural integrity with `PRAGMA integrity_check`.
   - Compresses the backup with gzip.
   - Retains 14 days of local archives at `/var/backups/interview-simulator`.
   - Replicates compressed backups to Azure Blob Storage using System-Assigned Managed Identity (`DefaultAzureCredential`), requiring zero static storage account keys.

### Useful Production Management Commands
```bash
# Check application status
sudo systemctl status interview-simulator.service

# View live application logs
sudo journalctl -u interview-simulator.service -f

# Restart application service
sudo systemctl restart interview-simulator.service

# Trigger a manual database backup and upload to Azure Blob Storage
python3 scripts/backup_db.py --source /data/interview.db --upload-azure

# Restore database from a local or Azure Blob backup archive
python3 scripts/backup_db.py --restore /var/backups/interview-simulator/backup_*.db.gz --target /data/interview.db
```

---

## Privacy, Security & Responsible AI

- **Observable Nonverbal Telemetry**: The computer vision pipeline measures strictly observable physical cues: face presence, centering offset within the camera frame, head-pose angles, and motion energy. It does **not** perform emotion recognition, sentiment analysis, or psychological profiling.
- **PII Scrubbing**: The document processor automatically scrubs phone numbers, email addresses, and personal URLs from uploaded resumes and job descriptions before passing data to LLM reasoning prompts.
- **Secure Password Storage**: Passwords are never stored in plaintext. They are salted and hashed using `bcrypt` with a minimum length requirement of 8 characters.
- **Stateless Cryptographic Cookies**: Session tokens are signed using `itsdangerous` with `HttpOnly` and `SameSite=Lax` flags, preventing cross-site scripting (XSS) token exfiltration. In production mode, the `Secure` flag enforces HTTPS transmission.
- **Zero Sensitive Data Logging**: Database backup logs, application traces, and error outputs redact PII, tokens, and database row contents.
- **Resilient Fallbacks**: If external AI APIs become unavailable or rate-limited, the application degrades gracefully to deterministic heuristic evaluation and rule-based questioning, ensuring that candidates can continue practicing without disruption.