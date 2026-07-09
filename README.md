# AI Interview Simulator

An advanced AI-powered technical interview platform that conducts realistic voice-based interviews, evaluates technical and communication performance, generates adaptive follow-up questions, and tracks candidate improvement over time.

Unlike a basic interview chatbot, this project combines speech intelligence, resume-aware question generation, conversation state management, answer evaluation, and progress analytics.

## Key Features

- **Resume-Aware Interviews:** Upload a resume and generate targeted technical, project-based, and behavioral questions.
- **Voice-Based Interviewing:** Record spoken answers and convert them into transcripts using speech-to-text.
- **Speech Intelligence:** Detect filler words, hesitation, speaking speed, pauses, repeated words, and sentence restarts.
- **Dynamic Follow-Ups:** Generate follow-up questions based on answer quality, weak concepts, and confidence scores.
- **Answer Evaluation:** Measure keyword coverage, semantic similarity, completeness, technical accuracy, and communication clarity.
- **Progress Analytics:** Track improvement over multiple interview sessions using dashboards and visual reports.
- **Interview Memory:** Personalize future interviews based on past weaknesses and performance trends.

## System Architecture

```text
React Frontend
    |
WebRTC / Audio Recording
    |
FastAPI Backend
    |
+----------------------+----------------------+----------------------+
| Speech Engine        | Interview Engine     | Analytics Engine     |
| - Whisper STT        | - State Machine      | - Progress Metrics   |
| - Filler Detection   | - Follow-up Planner  | - Skill Trends       |
| - Pause Analysis     | - Adaptive Difficulty| - Reports            |
+----------------------+----------------------+----------------------+
    |
PostgreSQL + Redis + Object Storage
```

## Tech Stack

### Frontend
React
TypeScript
Tailwind CSS
shadcn/ui
Recharts
Backend
FastAPI
Python
PostgreSQL
Redis
Celery
AI / ML
Whisper for speech-to-text
sentence-transformers for semantic similarity
spaCy for NLP and entity extraction
scikit-learn for analytics
LLM APIs for interviewer behavior and evaluation
Infrastructure
Docker
GitHub Actions
S3-compatible storage
Cloud deployment target: AWS / GCP / Render
Core Modules
Speech Intelligence Module
Processes interview audio and extracts measurable communication signals:
speaking speed
pause count
average pause duration
long pauses
filler words
repeated words
sentence restarts
Interview Engine
Controls the interview flow using a conversation state machine:
introduction
resume questions
project deep dives
data structures and algorithms
behavioral questions
HR round
conclusion
Answer Understanding Engine
Evaluates answers using a structured pipeline:
transcript segmentation
embedding generation
topic extraction
expected concept coverage
semantic similarity
LLM-based explanation
Analytics Engine
Tracks performance across interview sessions:
technical accuracy
answer relevance
communication clarity
confidence
filler rate
improvement over time
Roadmap
See [ROADMAP.md](docs/ROADMAP.md).
Setup
See [SETUP.md](docs/SETUP.md).
Project Status
This project is currently in active development.
Current focus:
project foundation
backend API setup
resume upload
speech analytics
interview state machine
Author
Akshit Bedi
Computer Science Student, Batch 2024-2028
