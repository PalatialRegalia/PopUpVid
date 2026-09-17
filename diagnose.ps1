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
        Write-Host "   🔧 Installing llama2 model..." -ForegroundColor Blue
        docker exec popup-ollama ollama pull llama2
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
        
        # Test overlay creation with sample
        Write-Host "   🧪 Testing overlay creation..." -ForegroundColor Gray
        $overlayTest = @"
ffmpeg -f lavfi -i testsrc=duration=5:size=320x240:rate=1 -vf "drawtext=text='Test Pop-up':fontcolor=white:fontsize=20:box=1:boxcolor=red@0.8:x=(w-text_w)/2:y=h-50:enable='between(t,1,4)'" -t 5 -y /app/temp/test_overlay.mp4 2>/dev/null
"@
        $result = docker exec popup-video-app bash -c $overlayTest
        if ($LASTEXITCODE -eq 0) {
            Write-Host "   ✅ Overlay creation working" -ForegroundColor Green
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

# Test 8: End-to-End Pipeline Test
Write-Host ""
Write-Host "8️⃣ Running End-to-End Pipeline Test..." -ForegroundColor Yellow
Write-Host "   🧪 Testing with Rick Astley video (small sample)..." -ForegroundColor Gray

$pipelineTest = @"
python3 -c "
import os, tempfile, subprocess
from youtube_transcript_api import YouTubeTranscriptApi

print('Step 1: Download test...')
temp_dir = '/app/temp/pipeline_test'
os.makedirs(temp_dir, exist_ok=True)

try:
    # Test download (first 10 seconds only)
    cmd = ['yt-dlp', '-f', 'worst', '--download-archive', '/dev/null', '-o', f'{temp_dir}/test.%(ext)s', '--external-downloader-args', '-ss 0 -t 10', 'https://www.youtube.com/watch?v=dQw4w9WgXcQ']
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode == 0:
        print('✅ Download: SUCCESS')
    else:
        print(f'❌ Download: FAILED - {result.stderr[:100]}')
        exit(1)
    
    print('Step 2: Transcript test...')
    transcript = YouTubeTranscriptApi.get_transcript('dQw4w9WgXcQ', languages=['en'])
    print(f'✅ Transcript: Found {len(transcript)} segments')
    
    print('Step 3: Overlay test...')
    video_files = [f for f in os.listdir(temp_dir) if f.endswith(('.mp4', '.webm'))]
    if video_files:
        video_path = os.path.join(temp_dir, video_files[0])
        output_path = os.path.join(temp_dir, 'test_output.mp4')
        
        overlay_cmd = [
            'ffmpeg', '-i', video_path,
            '-vf', 'drawtext=text=TEST POPUP:fontcolor=white:fontsize=20:box=1:boxcolor=red@0.8:x=(w-text_w)/2:y=h-50:enable=between(t,1,3)',
            '-c:a', 'copy', '-y', output_path
        ]
        
        overlay_result = subprocess.run(overlay_cmd, capture_output=True, text=True, timeout=30)
        if overlay_result.returncode == 0 and os.path.exists(output_path):
            file_size = os.path.getsize(output_path)
            print(f'✅ Overlay: SUCCESS - Output file {file_size} bytes')
            print('🎉 END-TO-END PIPELINE WORKING!')
        else:
            print(f'❌ Overlay: FAILED - {overlay_result.stderr[:100]}')
    else:
        print('❌ No video file found for overlay test')
        
except Exception as e:
    print(f'❌ Pipeline test failed: {str(e)}')
"
"@

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