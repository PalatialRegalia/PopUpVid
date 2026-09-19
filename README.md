# PopUp Video Overlay Generator
### Production Ready • Containerized • Cross-Platform

Transform any YouTube video into an MTV-style Pop-Up Video experience with AI-generated contextual trivia bubbles using local Ollama LLMs.

## Features

- **Local AI Processing**: Ollama integration with `qwen3:14b` (the model installed on prometheus-1; graceful fallback trivia pool if Ollama is unreachable)
- **Real Video Processing**: Full video downloads via `yt-dlp` and `FFmpeg` processing
- **Multiple Bubble Styles**: MTV Classic, Neon Glow, and Retro Rainbow palettes
- **Robust Font Handling**: Automated cross-platform font detection (Linux, macOS, Windows)
- **Zero-Escaping FFmpeg Overlays**: Temp `textfile` drawtext pipeline eliminates escaping bugs
- **One-Command Deployment**: Fully containerized with Docker Desktop and PowerShell orchestration

## Quick Start (3 Minutes)

### Prerequisites

- Docker Desktop (running)
- PowerShell or Terminal

### Installation & Launch

```powershell
# 1. Navigate to project directory
cd C:\Users\mathe\Desktop\PopUpVid

# 2. Deploy using Docker Compose
.\deploy.ps1

# 3. Open http://localhost:8501 in your browser
```

### Direct Docker Compose Usage

```bash
docker-compose up -d --build
```

### Stopping

```bash
docker-compose down
```

### Checking Logs

```bash
docker-compose logs -f
```

## Running Unit Tests

```bash
python tests/run_tests.py
```

## Architecture

- **`app.py`** — Main Streamlit application and FFmpeg overlay processing pipeline
- **`Dockerfile`** — Container build instructions with `libfreetype6`, `libfontconfig1`, and font packages
- **`docker-compose.yml`** — Docker Compose orchestration for app + Ollama LLM service
- **`deploy.ps1`** — Windows deployment script
- **`diagnose.ps1`** — Automated diagnostic and self-healing script
- **`tests/test_app.py`** — Unit tests covering URL validation, video ID extraction, escaping, and fallbacks

## Troubleshooting

Run `.\diagnose.ps1` to automatically test containers, network connectivity, yt-dlp, FFmpeg overlay rendering, and Ollama status.

## License

MIT

