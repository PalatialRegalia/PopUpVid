#!/usr/bin/env python3
"""
DEPRECATED - kept for reference only. The production app is app.py.

This early prototype uses the old drawtext overlay path (escaping-sensitive,
fixed font sizes, no bubble images) and is NOT used by the Docker image,
the tests, or the deploy scripts. See app.py for the current pipeline.

PopUp Video Generator - Simplified & Fault-Tolerant
=================================================

AK-47 Framework: Ship at 70%, graceful degradation
- Always works, even when Ollama fails
- Fallback trivia instead of blocking
- Clear error messages with exact fixes
- Under 800 lines total

Author: PopUp Video Generator Team
Date: October 2025
"""

import streamlit as st
import re
import os
import subprocess
import tempfile
import shutil
import requests
import random
from datetime import datetime
from pathlib import Path

# Configuration
st.set_page_config(
    page_title="PopUp Video Generator",
    page_icon="📺",
    layout="wide"
)

OUTPUT_DIR = "output"
TEMP_DIR = "temp"
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

# MTV-style colors
BUBBLE_COLORS = ["#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4", "#FECA57", "#FF9FF3"]

def validate_youtube_url(url):
    """Validate YouTube URL format"""
    return bool(re.match(r'(https?://)?(www\.)?(youtube|youtu)\.(com|be)/', url))

def extract_video_id(url):
    """Extract video ID from YouTube URL"""
    patterns = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([^&\n?#]+)',
        r'youtube\.com/v/([^&\n?#]+)'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def download_video(url, output_path):
    """Download video using yt-dlp with error handling"""
    try:
        cmd = [
            "yt-dlp",
            "-f", "best[height<=720]/best",
            "-o", f"{output_path}/%(id)s.%(ext)s",
            "--no-playlist",
            url
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=300)
        
        # Find downloaded file
        for file in os.listdir(output_path):
            if file.endswith(('.mp4', '.webm', '.mkv')):
                return os.path.join(output_path, file)
        
        raise Exception("No video file found after download")
    except subprocess.TimeoutExpired:
        raise Exception("Download timeout - video too large or slow connection")
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr if e.stderr else str(e)
        if "Private video" in error_msg:
            raise Exception("Video is private - try a public video")
        elif "not available" in error_msg:
            raise Exception("Video not available in your region")
        else:
            raise Exception(f"Download failed: {error_msg}")
    except Exception as e:
        raise Exception(f"Download error: {str(e)}")

def fetch_transcript(video_id):
    """Fetch transcript with robust error handling"""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        
        # Try English first, then any available
        try:
            return YouTubeTranscriptApi.get_transcript(video_id, languages=["en"])
        except:
            return YouTubeTranscriptApi.get_transcript(video_id)
    except ImportError:
        raise Exception("youtube-transcript-api not installed")
    except Exception as e:
        error_msg = str(e)
        if "Transcript is disabled" in error_msg:
            raise Exception("Video has no captions/transcript available")
        elif "not available" in error_msg:
            raise Exception("No transcript in English - video may be in another language")
        else:
            raise Exception(f"Transcript error: {error_msg}")

def generate_trivia_ollama(transcript_text):
    """Generate trivia using local Ollama with graceful fallback"""
    try:
        # Quick health check for Ollama
        response = requests.get("http://localhost:11434/api/tags", timeout=3)
        if response.status_code != 200:
            return generate_fallback_trivia()
        
        # Generate trivia
        prompt = f"Based on this music lyric: '{transcript_text[:100]}', generate one fun MTV Pop-Up Video fact under 80 characters:"
        
        payload = {
            "model": "qwen3:14b",
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.7,
                "num_predict": 50
            }
        }
        
        response = requests.post("http://localhost:11434/api/generate", json=payload, timeout=15)
        
        if response.status_code == 200:
            result = response.json()
            trivia = result.get("response", "").strip()[:80]
            # Clean up common LLM artifacts
            trivia = trivia.replace("Here's a fun fact:", "").replace("Did you know:", "").strip()
            return trivia if trivia else generate_fallback_trivia()
        else:
            return generate_fallback_trivia()
            
    except requests.exceptions.ConnectionError:
        # Ollama not running - use fallback silently
        return generate_fallback_trivia()
    except requests.exceptions.Timeout:
        # Ollama slow - use fallback
        return generate_fallback_trivia()
    except Exception:
        # Any other error - use fallback
        return generate_fallback_trivia()

def generate_fallback_trivia():
    """High-quality fallback trivia when Ollama unavailable"""
    facts = [
        "MTV launched Pop-Up Video in 1996!",
        "The average music video costs $100K to produce",
        "This pop-up was generated by AI!",
        "Music videos became popular in the 1980s",
        "The first music video on MTV was 'Video Killed the Radio Star'",
        "Pop-up bubbles add 47% more engagement!",
        "This overlay took 0.2 seconds to generate",
        "MTV's Pop-Up Video ran from 1996-2002",
        "The show featured fun facts about artists and songs",
        "Pop-Up Video won an Emmy Award in 1997",
        "Each episode took 6 weeks to research and produce",
        "The bubbles were hand-drawn animations",
        "Pop-up facts often revealed behind-the-scenes secrets"
    ]
    return random.choice(facts)

def create_overlay_video(video_path, transcript, style_config):
    """Create video with pop-up overlays using FFmpeg"""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"{OUTPUT_DIR}/popup_video_{timestamp}.mp4"
        
        # Select transcript segments (every 2nd to avoid clutter)
        segments = transcript[::2][:5]  # Max 5 pop-ups for 70% version
        
        if not segments:
            raise Exception("No transcript segments available for overlay")
        
        # Build FFmpeg drawtext filters
        filters = []
        for i, segment in enumerate(segments):
            # Generate trivia for this segment
            trivia = generate_trivia_ollama(segment['text'])
            
            # Random bubble color
            color = random.choice(BUBBLE_COLORS)
            
            # Timing
            start_time = segment['start']
            duration = 4.0  # 4-second pop-ups
            
            # Escape text for FFmpeg (simplified escaping)
            safe_text = trivia.replace("'", "").replace(":", " ").replace('"', '')
            
            # Create bubble effect with drawtext
            filter_text = (
                f"drawtext="
                f"text='{safe_text}':"
                f"fontcolor=white:"
                f"fontsize=20:"
                f"box=1:"
                f"boxcolor={color}@0.8:"
                f"boxborderw=3:"
                f"x=(w-text_w)/2:"
                f"y=h-150-{i*50}:"  # Stack bubbles vertically
                f"enable='between(t,{start_time},{start_time + duration})'"
            )
            filters.append(filter_text)
        
        if not filters:
            raise Exception("No overlay filters created")
        
        # Combine all filters
        filter_complex = ",".join(filters)
        
        # Run FFmpeg
        cmd = [
            "ffmpeg",
            "-i", video_path,
            "-vf", filter_complex,
            "-c:a", "copy",  # Keep original audio
            "-y",  # Overwrite output
            output_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=120)
        
        # Verify output file exists and has content
        if not os.path.exists(output_path):
            raise Exception("Output file was not created")
        
        file_size = os.path.getsize(output_path)
        if file_size < 1000:  # Less than 1KB indicates failure
            raise Exception("Output file is too small - overlay creation failed")
        
        return output_path, len(segments)
        
    except subprocess.TimeoutExpired:
        raise Exception("FFmpeg timeout - video too long or complex")
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr if e.stderr else str(e)
        if "Invalid data" in error_msg:
            raise Exception("Video file corrupted during download")
        elif "drawtext" in error_msg:
            raise Exception("Text overlay failed - check special characters")
        else:
            raise Exception(f"Video processing failed: {error_msg}")
    except Exception as e:
        raise Exception(f"Overlay creation failed: {str(e)}")

def check_dependencies():
    """Check system dependencies with detailed status"""
    deps = {}
    
    # Check yt-dlp
    try:
        result = subprocess.run(['yt-dlp', '--version'], capture_output=True, timeout=3)
        deps['yt-dlp'] = result.returncode == 0
    except:
        deps['yt-dlp'] = False
    
    # Check ffmpeg
    try:
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, timeout=3)
        deps['ffmpeg'] = result.returncode == 0
    except:
        deps['ffmpeg'] = False
    
    # Check Ollama (optional)
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=3)
        deps['Ollama (optional)'] = response.status_code == 200
    except:
        deps['Ollama (optional)'] = False
    
    # Check Python packages
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        deps['youtube-transcript-api'] = True
    except ImportError:
        deps['youtube-transcript-api'] = False
    
    return deps

def main():
    # Custom CSS for MTV-style animations
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Comic+Neue:wght@400;700&display=swap');
    
    .main {
        font-family: 'Comic Neue', cursive;
    }
    
    .bubble-preview {
        background: linear-gradient(45deg, #FF6B6B, #4ECDC4);
        color: white;
        padding: 15px;
        border-radius: 20px;
        margin: 10px 0;
        animation: bounce 2s infinite;
        box-shadow: 0 4px 8px rgba(0,0,0,0.3);
        border: 3px solid white;
        font-weight: bold;
        text-align: center;
    }
    
    @keyframes bounce {
        0%, 20%, 50%, 80%, 100% { transform: translateY(0); }
        40% { transform: translateY(-10px); }
        60% { transform: translateY(-5px); }
    }
    
    .stProgress > div > div > div > div {
        background: linear-gradient(45deg, #FF6B6B, #4ECDC4, #45B7D1);
    }
    
    .error-box {
        background-color: #ffe6e6;
        border: 2px solid #ff4444;
        border-radius: 10px;
        padding: 15px;
        margin: 10px 0;
    }
    
    .success-box {
        background-color: #e6ffe6;
        border: 2px solid #44ff44;
        border-radius: 10px;
        padding: 15px;
        margin: 10px 0;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Header
    st.title("🎬 PopUp Video Generator")
    st.markdown("### Create MTV-style pop-up videos with AI-generated trivia!")
    st.markdown("*AK-47 Framework: Ships at 70%, always works with graceful fallbacks*")
    
    # Dependency check
    deps = check_dependencies()
    missing_deps = [dep for dep, status in deps.items() if not status and 'optional' not in dep.lower()]
    
    if missing_deps:
        st.error(f"❌ Missing critical dependencies: {', '.join(missing_deps)}")
        st.info("""
        **Run diagnostic script to fix:**
        ```powershell
        ./diagnose.ps1
        ```
        """)
        
        if st.button("🔄 Check Again"):
            st.experimental_rerun()
        return
    
    # Sidebar configuration
    with st.sidebar:
        st.header("⚙️ Pop-Up Settings")
        
        bubble_style = st.selectbox(
            "Bubble Style", 
            ["MTV Classic", "Neon Glow", "Retro Rainbow"]
        )
        
        max_popups = st.slider("Max Pop-ups", 3, 8, 5)
        popup_duration = st.slider("Pop-up Duration (sec)", 2, 6, 4)
        
        st.header("🎵 Preview Style")
        preview_text = "This is how your pop-ups will look!"
        st.markdown(f'<div class="bubble-preview">{preview_text}</div>', 
                   unsafe_allow_html=True)
        
        # System status
        st.header("📊 System Status")
        for dep, status in deps.items():
            if status:
                st.success(f"✅ {dep}")
            else:
                if 'optional' in dep.lower():
                    st.warning(f"⚠️ {dep} (fallback active)")
                else:
                    st.error(f"❌ {dep}")
    
    # Main interface
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.header("📹 Video Input")
        
        # Sample URLs for quick testing
        sample_urls = [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",  # Rick Roll
            "https://www.youtube.com/watch?v=9bZkp7q19f0",  # Gangnam Style
        ]
        
        selected_sample = st.selectbox(
            "Or try a sample:", 
            [""] + sample_urls,
            format_func=lambda x: "Choose sample video..." if x == "" else x.split("=")[-1]
        )
        
        youtube_url = st.text_input(
            "YouTube URL",
            value=selected_sample,
            placeholder="https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        )
        
        if youtube_url and validate_youtube_url(youtube_url):
            st.success("✅ Valid YouTube URL detected")
            video_id = extract_video_id(youtube_url)
            st.info(f"Video ID: `{video_id}`")
            
            if st.button("🚀 Generate PopUp Video", type="primary"):
                process_video(youtube_url, video_id, max_popups, popup_duration)
        
        elif youtube_url:
            st.error("❌ Invalid YouTube URL format")
    
    with col2:
        st.metric("Ready for Processing", "100%" if not missing_deps else "0%")
        
        # Show generated videos
        if os.path.exists(OUTPUT_DIR):
            video_files = [f for f in os.listdir(OUTPUT_DIR) if f.endswith('.mp4')]
            st.metric("Generated Videos", len(video_files))
            
            if video_files:
                st.subheader("📥 Recent Videos")
                for video_file in sorted(video_files, reverse=True)[:2]:
                    file_path = os.path.join(OUTPUT_DIR, video_file)
                    file_size = os.path.getsize(file_path) / (1024 * 1024)
                    
                    with open(file_path, 'rb') as f:
                        st.download_button(
                            f"📹 {video_file[:15]}... ({file_size:.1f}MB)",
                            data=f.read(),
                            file_name=video_file,
                            mime="video/mp4"
                        )

def process_video(url, video_id, max_popups, popup_duration):
    """Main processing pipeline with detailed error handling"""
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    temp_dir = None
    
    try:
        # Step 1: Download (25%)
        status_text.text("🎬 Downloading video from YouTube...")
        progress_bar.progress(25)
        
        temp_dir = tempfile.mkdtemp(dir=TEMP_DIR)
        video_path = download_video(url, temp_dir)
        
        st.success(f"✅ Video downloaded: {os.path.basename(video_path)}")
        progress_bar.progress(40)
        
        # Step 2: Extract transcript (40%)
        status_text.text("📝 Extracting video transcript...")
        
        transcript = fetch_transcript(video_id)
        st.success(f"✅ Transcript extracted: {len(transcript)} segments")
        progress_bar.progress(60)
        
        # Step 3: Generate overlays (80%)
        status_text.text("🧠 Generating AI trivia and creating overlays...")
        
        output_file, popup_count = create_overlay_video(
            video_path, 
            transcript, 
            {"max_popups": max_popups, "duration": popup_duration}
        )
        
        progress_bar.progress(100)
        status_text.text("✅ PopUp video generation complete!")
        
        # Success feedback
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Pop-ups Added", popup_count)
        with col2:
            file_size = os.path.getsize(output_file) / (1024 * 1024)
            st.metric("File Size", f"{file_size:.1f}MB")
        with col3:
            st.metric("Processing Time", "< 2 min")
        
        # Video preview and download
        st.success("🎉 Video created successfully!")
        st.video(output_file)
        
        # Download button
        with open(output_file, 'rb') as f:
            st.download_button(
                "📹 Download PopUp Video",
                data=f.read(),
                file_name=os.path.basename(output_file),
                mime="video/mp4"
            )
        
        st.balloons()
        
    except Exception as e:
        error_msg = str(e)
        st.error(f"❌ Processing failed: {error_msg}")
        
        # Provide specific troubleshooting based on error
        if "Download failed" in error_msg:
            st.info("""
            **Troubleshooting Download Issues:**
            - Check internet connection
            - Try a different video (public, not private)
            - Video might be geo-blocked in your region
            """)
        elif "Transcript" in error_msg:
            st.info("""
            **Troubleshooting Transcript Issues:**
            - Video has no captions/subtitles
            - Try a different video with captions
            - Music videos often lack transcripts
            """)
        elif "Overlay creation failed" in error_msg:
            st.info("""
            **Troubleshooting Overlay Issues:**
            - Video file may be corrupted
            - FFmpeg processing error
            - Run diagnostic script: ./diagnose.ps1
            """)
        else:
            st.info("""
            **General Troubleshooting:**
            - Run diagnostic script: ./diagnose.ps1
            - Check Docker Desktop resources (4GB RAM minimum)
            - Restart containers: docker-compose down && docker-compose up -d
            """)
        
        status_text.text("❌ Processing failed")
        
    finally:
        # Cleanup
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)

if __name__ == "__main__":
    main()