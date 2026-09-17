# PopUp Video Overlay Generator - Windows 11 Deployment Script
# Following AK-47 Framework: Ship at 70%, iterate from production

Write-Host "🎬 PopUp Video Generator - Windows 11 Setup" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host ""

# Check if Docker Desktop is running
try {
    $dockerInfo = docker info 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker not running"
    }
    Write-Host "✅ Docker Desktop is running" -ForegroundColor Green
} catch {
    Write-Host "❌ Docker Desktop not running or not installed" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please install and start Docker Desktop:" -ForegroundColor Yellow
    Write-Host "https://www.docker.com/products/docker-desktop/" -ForegroundColor Blue
    Write-Host ""
    Write-Host "Then run this script again." -ForegroundColor Yellow
    exit 1
}

# Create output and temp directories
Write-Host "📁 Creating directories..." -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path "output" | Out-Null
New-Item -ItemType Directory -Force -Path "temp" | Out-Null
Write-Host "✅ Directories created" -ForegroundColor Green

Write-Host ""
Write-Host "🚀 Starting PopUp Video Generator" -ForegroundColor Cyan
Write-Host "==================================" -ForegroundColor Cyan

# Build and run with Docker Compose
Write-Host "📦 Building Docker containers..." -ForegroundColor Yellow
docker-compose build

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Docker build failed" -ForegroundColor Red
    exit 1
}

Write-Host "🎬 Launching PopUp Video Generator..." -ForegroundColor Yellow
docker-compose up -d

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Docker launch failed" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "✅ PopUp Video Generator is now running!" -ForegroundColor Green
Write-Host ""
Write-Host "🌐 Access the app at: " -NoNewline -ForegroundColor White
Write-Host "http://localhost:8501" -ForegroundColor Blue
Write-Host "📡 Ollama API at: " -NoNewline -ForegroundColor White  
Write-Host "http://localhost:11434" -ForegroundColor Blue
Write-Host ""
Write-Host "🎯 AK-47 Framework Applied:" -ForegroundColor Cyan
Write-Host "  ✅ Problem First - MTV-style pop-up videos" -ForegroundColor Green
Write-Host "  ✅ Audit Ruthlessly - 5 core features only" -ForegroundColor Green
Write-Host "  ✅ Architecture Blueprint - 5-layer pipeline" -ForegroundColor Green
Write-Host "  ✅ Code Minimal - Under 800 lines" -ForegroundColor Green
Write-Host "  ✅ Deploy Early - Ships at 70% complete" -ForegroundColor Green
Write-Host ""
Write-Host "📊 System Status:" -ForegroundColor Yellow
docker-compose ps

Write-Host ""
Write-Host "📝 Quick Start Guide:" -ForegroundColor Yellow
Write-Host "1. Open http://localhost:8501 in your browser" -ForegroundColor White
Write-Host "2. Paste a YouTube URL (try: https://www.youtube.com/watch?v=dQw4w9WgXcQ)" -ForegroundColor White
Write-Host "3. Click 'Generate PopUp Video'" -ForegroundColor White
Write-Host "4. Download your MTV-style pop-up video!" -ForegroundColor White
Write-Host ""
Write-Host "🛑 To stop: " -NoNewline -ForegroundColor Red
Write-Host "docker-compose down" -ForegroundColor White
Write-Host "📋 To check logs: " -NoNewline -ForegroundColor Blue
Write-Host "docker-compose logs -f" -ForegroundColor White
Write-Host ""
Write-Host "🎉 Ready to create pop-up videos!" -ForegroundColor Green