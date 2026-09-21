# PopUp Video Generator - Diagnostic & Troubleshooting Script
# Windows 11 PowerShell Diagnostics for AK-47 Framework
# Run this to identify exact failure points and auto-fix issues

Write-Host "🔍 PopUp Video Generator - System Diagnostics" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host ""

# Test 1: Docker Desktop Status
Write-Host "1️⃣ Testing Docker Desktop..." -ForegroundColor Yellow
try {
    $dockerInfo = docker info 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "   ✅ Docker Desktop is running" -ForegroundColor Green
        docker --version
    } else {
        Write-Host "   ❌ Docker Desktop not running" -ForegroundColor Red
        Write-Host "   🔧 FIX: Start Docker Desktop from Start Menu" -ForegroundColor Blue
        Write-Host "   📍 Path: C:\Program Files\Docker\Docker\Docker Desktop.exe" -ForegroundColor Gray
        exit 1
    }
} catch {
    Write-Host "   ❌ Docker not installed" -ForegroundColor Red
    Write-Host "   🔧 FIX: Install Docker Desktop from https://docker.com/products/docker-desktop" -ForegroundColor Blue
    exit 1
}

# Test 2: Check if containers exist and are running
Write-Host ""
Write-Host "2️⃣ Checking PopUp Video containers..." -ForegroundColor Yellow
$containers = docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | Select-String "popup-video"
if ($containers) {
    Write-Host "   ✅ Container running:" -ForegroundColor Green
    Write-Host "   $containers" -ForegroundColor Gray
} else {
    Write-Host "   ⚠️ No containers running" -ForegroundColor Yellow
    Write-Host "   🔧 Starting containers..." -ForegroundColor Blue
    
    if (Test-Path "docker-compose.yml") {
        docker-compose up -d
        Start-Sleep 10
        Write-Host "   ✅ Containers started" -ForegroundColor Green
    } else {
        Write-Host "   ❌ docker-compose.yml not found" -ForegroundColor Red
        Write-Host "   🔧 FIX: Run this script from the project directory" -ForegroundColor Blue
        exit 1
    }
}

# Test 3: Streamlit Web Interface
Write-Host ""
Write-Host "3️⃣ Testing Streamlit Web Interface..." -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8501" -TimeoutSec 5 -UseBasicParsing
    if ($response.StatusCode -eq 200) {
        Write-Host "   ✅ Streamlit running at http://localhost:8501" -ForegroundColor Green
    } else {
        Write-Host "   ❌ Streamlit not responding" -ForegroundColor Red
        Write-Host "   🔧 Checking container logs..." -ForegroundColor Blue
        docker-compose logs popup-video-app
    }
} catch {
    Write-Host "   ❌ Cannot connect to Streamlit" -ForegroundColor Red
    Write-Host "   🔧 FIX: Wait 30 seconds for container startup, then try again" -ForegroundColor Blue
}

# Test 4: Ollama LLM Server
Write-Host ""
Write-Host "4️⃣ Testing Ollama LLM Server..." -ForegroundColor Yellow
try {
    $ollamaResponse = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 10
    Write-Host "   ✅ Ollama server running" -ForegroundColor Green
    
    if ($ollamaResponse.models) {
        Write-Host "   📦 Available models:" -ForegroundColor Gray
        foreach ($model in $ollamaResponse.models) {
            Write-Host "      - $($model.name)" -ForegroundColor Gray
        }
    } else {
        Write-Host "   ⚠️ No models installed" -ForegroundColor Yellow
        Write-Host "   🔧 Install the model on the host: ollama pull qwen3:14b" -ForegroundColor Blue
        Write-Host "   (The app falls back to curated trivia until then - no action required)" -ForegroundColor Gray
    }
} catch {
    Write-Host "   ❌ Ollama not responding" -ForegroundColor Red
    Write-Host "   🔧 This is OK - app uses fallback trivia when Ollama unavailable" -ForegroundColor Blue
}

# Test 5: YouTube Download (yt-dlp)
Write-Host ""
Write-Host "5️⃣ Testing YouTube Download (yt-dlp)..." -ForegroundColor Yellow
$testUrl = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
try {
    $ytdlpTest = docker exec popup-video-app yt-dlp --version 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "   ✅ yt-dlp available: $ytdlpTest" -ForegroundColor Green
        
        # Test actual download
        Write-Host "   🧪 Testing sample download (metadata only)..." -ForegroundColor Gray
        $metadataTest = docker exec popup-video-app yt-dlp --skip-download --print-json $testUrl 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "   ✅ YouTube access working" -ForegroundColor Green
        } else {
            Write-Host "   ❌ YouTube download test failed" -ForegroundColor Red
            Write-Host "   🔧 Check internet connection or try different video" -ForegroundColor Blue
        }
    } else {
        Write-Host "   ❌ yt-dlp not available" -ForegroundColor Red
    }
} catch {
    Write-Host "   ❌ Cannot test yt-dlp" -ForegroundColor Red
}

# Test 6: FFmpeg Video Processing
Write-Host ""
Write-Host "6️⃣ Testing FFmpeg Video Processing..." -ForegroundColor Yellow
try {
    $ffmpegTest = docker exec popup-video-app ffmpeg -version 2>$null | Select-String "ffmpeg version" | Select-Object -First 1
    if ($ffmpegTest) {
        Write-Host "   ✅ FFmpeg available: $ffmpegTest" -ForegroundColor Green
        
        # Test the REAL production path: Pillow bubble + FFmpeg overlay graph
        Write-Host "   🧪 Testing bubble render + overlay (production path)..." -ForegroundColor Gray
        $overlayTest = @'
python3 <<'PYEOF'
import sys, subprocess, os
sys.path.insert(0, '/app')
from app import generate_bubble_image, build_overlay_graph

size = generate_bubble_image('POP-UP FACT', 'Diagnostics: this bubble renders and overlays correctly', 'MTV Classic', '#FF6B6B', 640, 360, '/tmp/diag_bubble.png', 1, 2)
bubble = {'png': '/tmp/diag_bubble.png', 'w': size[0], 'h': size[1], 'start': 0.5, 'end': 3.0, 'x': 40, 'y': 180, 'clip': 3.5}
inputs, graph, label = build_overlay_graph(640, 360, [bubble], animated=True)
cmd = ['ffmpeg', '-y', '-f', 'lavfi', '-i', 'testsrc2=size=640x360:rate=25:duration=4'] + inputs + \
      ['-filter_complex', graph, '-map', '[' + label + ']', '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', '/tmp/diag_overlay.mp4']
res = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
if res.returncode == 0 and os.path.exists('/tmp/diag_overlay.mp4') and os.path.getsize('/tmp/diag_overlay.mp4') > 1000:
    print('PIPELINE_OK: bubble %dx%d, overlay %d bytes' % (size[0], size[1], os.path.getsize('/tmp/diag_overlay.mp4')))
else:
    print('PIPELINE_FAIL: ' + (res.stderr or '')[-200:])
PYEOF
'@
        $result = docker exec popup-video-app bash -c $overlayTest
        if ($result -match "PIPELINE_OK") {
            Write-Host "   ✅ Bubble render + overlay working" -ForegroundColor Green
            Write-Host "   $result" -ForegroundColor Gray
        } else {
            Write-Host "   ❌ Overlay creation failed" -ForegroundColor Red
            Write-Host "   $result" -ForegroundColor Gray
            Write-Host "   🔧 Check FFmpeg container configuration" -ForegroundColor Blue
        }
    } else {
            Write-Host "   ❌ Overlay creation failed" -ForegroundColor Red
            Write-Host "   🔧 Check FFmpeg container configuration" -ForegroundColor Blue
        }
    } else {
        Write-Host "   ❌ FFmpeg not available" -ForegroundColor Red
    }
} catch {
    Write-Host "   ❌ Cannot test FFmpeg" -ForegroundColor Red
}

# Test 7: Transcript API
Write-Host ""
Write-Host "7️⃣ Testing Transcript Extraction..." -ForegroundColor Yellow
$testVideoId = "dQw4w9WgXcQ"
try {
    $transcriptTest = @"
python3 -c "
from youtube_transcript_api import YouTubeTranscriptApi
try:
    transcript = YouTubeTranscriptApi.get_transcript('$testVideoId', languages=['en'])
    print(f'SUCCESS: Found {len(transcript)} transcript segments')
except Exception as e:
    print(f'FAILED: {str(e)}')
"
"@
    $result = docker exec popup-video-app bash -c $transcriptTest
    if ($result -match "SUCCESS") {
        Write-Host "   ✅ Transcript extraction working" -ForegroundColor Green
        Write-Host "   📝 $result" -ForegroundColor Gray
    } else {
        Write-Host "   ❌ Transcript extraction failed" -ForegroundColor Red
        Write-Host "   📝 $result" -ForegroundColor Gray
        Write-Host "   🔧 Some videos don't have transcripts - this is normal" -ForegroundColor Blue
    }
} catch {
    Write-Host "   ❌ Cannot test transcript extraction" -ForegroundColor Red
}

# Test 8: End-to-End Pipeline Test (offline: synthetic video, real app pipeline)
Write-Host ""
Write-Host "🔟 Running End-to-End Pipeline Test..." -ForegroundColor Yellow
Write-Host "   🧪 Synthesizing a 6s test clip and running the full app pipeline..." -ForegroundColor Gray

$pipelineTest = @'
python3 <<'PYEOF'
import sys, os, subprocess
sys.path.insert(0, '/app')

print('Step 1: Synthesize test video...')
src = '/tmp/diag_src.mp4'
res = subprocess.run(['ffmpeg', '-y', '-f', 'lavfi', '-i', 'testsrc2=size=640x360:rate=25:duration=6',
                      '-f', 'lavfi', '-i', 'sine=duration=6', '-c:v', 'libx264', '-preset', 'ultrafast',
                      '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', src],
                     capture_output=True, text=True, timeout=120)
if res.returncode != 0 or not os.path.exists(src):
    print('FAILED to synthesize test video: ' + (res.stderr or '')[-200:])
    raise SystemExit(1)
print('OK: %d bytes' % os.path.getsize(src))

print('Step 2: Run create_overlay_video (bubbles + trivia + FFmpeg)...')
from app import create_overlay_video
transcript = [
    {'text': 'intro', 'start': 1.0, 'duration': 4.0},
    {'text': 'chorus', 'start': 3.5, 'duration': 4.0},
]
out, count, facts = create_overlay_video(
    src, transcript,
    {'max_popups': 2, 'duration': 2.5, 'bubble_style': 'MTV Classic', 'animated': True},
    temp_dir='/tmp/diag_work')

size = os.path.getsize(out)
print('OUTPUT: %s (%d pop-ups, %d bytes)' % (out, count, size))
for fact in facts:
    print('  fact at %.1fs: %s' % (fact['start'], fact['text'][:60]))
if size > 1000 and count == len(facts):
    print('END-TO-END PIPELINE WORKING!')
else:
    print('END-TO-END PIPELINE FAILED')
PYEOF
'@

try {
    $pipelineResult = docker exec popup-video-app bash -c $pipelineTest
    Write-Host "$pipelineResult" -ForegroundColor Gray
    
    if ($pipelineResult -match "END-TO-END PIPELINE WORKING") {
        Write-Host ""
        Write-Host "🎉 DIAGNOSIS COMPLETE - SYSTEM READY!" -ForegroundColor Green
        Write-Host "🌐 Open http://localhost:8501 to create pop-up videos" -ForegroundColor Cyan
    } else {
        Write-Host ""
        Write-Host "⚠️ Pipeline has issues - check error messages above" -ForegroundColor Yellow
    }
} catch {
    Write-Host "   ❌ Cannot run pipeline test" -ForegroundColor Red
}

# Summary and Next Steps
Write-Host ""
Write-Host "📋 DIAGNOSTIC SUMMARY" -ForegroundColor Cyan
Write-Host "===================" -ForegroundColor Cyan
Write-Host ""
Write-Host "✅ Green = Working correctly" -ForegroundColor Green
Write-Host "⚠️ Yellow = Working with warnings" -ForegroundColor Yellow  
Write-Host "❌ Red = Needs attention" -ForegroundColor Red
Write-Host "🔧 Blue = Suggested fix" -ForegroundColor Blue
Write-Host ""
Write-Host "Next steps:" -ForegroundColor White
Write-Host "1. Fix any RED issues above" -ForegroundColor White
Write-Host "2. Open http://localhost:8501" -ForegroundColor White
Write-Host "3. Paste a YouTube URL" -ForegroundColor White
Write-Host "4. Click 'Generate PopUp Video'" -ForegroundColor White
Write-Host ""
Write-Host "📞 If issues persist:" -ForegroundColor Yellow
Write-Host "   - Run: docker-compose logs -f" -ForegroundColor Gray
Write-Host "   - Check Docker Desktop has enough resources (4GB RAM)" -ForegroundColor Gray
Write-Host "   - Try restarting: docker-compose down && docker-compose up -d" -ForegroundColor Gray