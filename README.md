# PopUp Video Overlay Generator
### Production Ready • Containerized • Cross-Platform

Transform any YouTube video into an MTV-style Pop-Up Video experience with AI-generated contextual trivia bubbles using local Ollama LLMs.

## Features

- **Local AI Processing**: Ollama integration with `qwen3:14b` (the model installed on prometheus-1; graceful fallback trivia pool if Ollama is unreachable)
- **Real Video Processing**: Full video downloads via `yt-dlp` and `FFmpeg` processing
- **Multiple Bubble Styles**: MTV Classic, Neon Glow, and Retro Rainbow palettes — each with contrast-aware text colors so trivia is always readable
- **Pixel-Perfect Bubbles**: Bubbles are rendered by Pillow at the video's native resolution, measured in pixels (not characters), so text can never be clipped or garbled — on any resolution from 480p to 4K
- **Deterministic Fonts**: Archivo Black + DejaVu Sans are bundled in `fonts/` (with licenses), so bubbles render identically on Windows, macOS and inside the Docker image
- **Animated Pop-Ins**: Bubbles fade in/out and gently float; a static-overlay fallback kicks in automatically if your FFmpeg build rejects the animated graph
- **Live Bubble Preview**: The sidebar shows the exact bubble that will be baked into your video
- **Trivia Timeline**: Every generated pop-up (timestamp + fact + color) is listed after rendering
- **Robust URL Handling**: `youtube.com/watch`, `youtu.be`, `/shorts`, `/live`, `/embed`, `m.` and `music.` hosts
- **Caption-Less Videos Work**: no transcript? Pop-ups are still spread across the whole video using duration-aware anchor points
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

The suite covers URL validation, video ID extraction, trivia sanitization (think-blocks, emoji, markdown), contrast-aware color picking, bubble rendering (all styles, all resolutions, width budgets), slide splitting, the FFmpeg overlay graph (bounded loops + fades), Ollama fallbacks, and — when FFmpeg is installed — a full end-to-end render of a synthetic video.

## Architecture

- **`app.py`** — Main Streamlit application, trivia pipeline, Pillow bubble renderer and FFmpeg overlay processing
- **`fonts/`** — Bundled fonts (Archivo Black, DejaVu Sans + licenses) used by every bubble
- **`Dockerfile`** — Container build instructions with `libfreetype6`, `libfontconfig1`, font packages and the bundled fonts
- **`docker-compose.yml`** — Docker Compose orchestration for app + Ollama LLM service
- **`deploy.ps1`** — Windows deployment script
- **`diagnose.ps1`** — Automated diagnostic and self-healing script (renders a real bubble + overlay end-to-end)
- **`index.html`** — Landing page with connection testing
- **`tests/test_app.py`** — 65 unit/integration tests covering the full pipeline

## Troubleshooting

- Run `.\diagnose.ps1` to automatically test containers, network connectivity, yt-dlp, bubble + FFmpeg overlay rendering, and Ollama status.
- If overlays look static instead of animated, your FFmpeg build rejected the animated graph — the app already retried with static overlays so output is still correct; you can also turn off **Animated pop-in** in the sidebar.
- Trivia falls back to a curated fact pool whenever Ollama is unreachable, slow, or returns unusable text — the app never blocks on the LLM.

## License

MIT (bundled fonts keep their own permissive licenses in `fonts/`)

