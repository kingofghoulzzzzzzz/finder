import os
import subprocess
import sys
import traceback
from tqdm import tqdm
import tempfile
import shutil

def get_video_info(video_path):
    """Get comprehensive video information including duration, fps, resolution, and audio info."""
    try:
        # Get video duration
        duration_result = subprocess.run([
            'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', video_path
        ], capture_output=True, text=True, timeout=10)

        duration = float(duration_result.stdout.strip()) if duration_result.stdout.strip() else 0

        # Get video properties with more explicit field selection
        video_result = subprocess.run([
            'ffprobe', '-v', 'error', '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height,r_frame_rate,codec_name',
            '-of', 'csv=s=,:p=0:nk=1', video_path  # Added nk=1 to suppress headers
        ], capture_output=True, text=True, timeout=10)

        if video_result.stdout.strip():
            video_info = video_result.stdout.strip().split(',')
            print(f"Debug - Video info for {os.path.basename(video_path)}: {video_info}")

            # More robust parsing with validation
            try:
                width = int(video_info[1]) if video_info[1] and video_info[1].isdigit() else 1920
                height = int(video_info[2]) if len(video_info) > 2 and video_info[2] and video_info[2].isdigit() else 1080
                fps_str = video_info[3] if len(video_info) > 3 and video_info[3] else "60/1"
                video_codec = video_info[0] if len(video_info) > 3 else "h264"
            except (ValueError, IndexError) as e:
                print(f"Warning: Error parsing video info for {video_path}: {e}")
                width, height, fps_str, video_codec = 1920, 1080, "60/1", "h264"

            # Parse frame rate
            try:
                if '/' in fps_str:
                    num, den = fps_str.split('/')
                    fps = float(num) / float(den) if float(den) != 0 else 60.0
                else:
                    fps = float(fps_str) if fps_str else 60.0
            except (ValueError, ZeroDivisionError):
                fps = 60.0
        else:
            print(f"Warning: No video stream info found for {video_path}")
            width, height, fps, video_codec = 1920, 1080, 60.0, "h264"

        # Get detailed audio information
        audio_result = subprocess.run([
            'ffprobe', '-v', 'error', '-select_streams', 'a:0',
            '-show_entries', 'stream=codec_name,sample_rate,channels,duration,bit_rate',
            '-of', 'csv=s=,:p=0:nk=1', video_path  # Added nk=1 to suppress headers
        ], capture_output=True, text=True, timeout=10)

        has_audio = bool(audio_result.stdout.strip())
        audio_duration = None
        audio_codec = None
        sample_rate = None
        channels = None

        if has_audio:
            try:
                audio_info = audio_result.stdout.strip().split(',')
                print(f"Debug - Audio info for {os.path.basename(video_path)}: {audio_info}")

                audio_codec = audio_info[0] if len(audio_info) > 0 else "aac"
                sample_rate = int(audio_info[1]) if len(audio_info) > 1 and audio_info[1] and audio_info[1].isdigit() else 24000
                channels = int(audio_info[2]) if len(audio_info) > 2 and audio_info[2] and audio_info[2].isdigit() else 2
                if len(audio_info) > 3 and audio_info[3] and audio_info[3].replace('.', '').isdigit():
                    audio_duration = float(audio_info[3])
            except (ValueError, IndexError) as e:
                print(f"Warning: Error parsing audio info for {video_path}: {e}")
                audio_codec, sample_rate, channels = "aac", 24000, 2

        return {
            'duration': duration,
            'width': width,
            'height': height,
            'fps': fps,
            'video_codec': video_codec,
            'has_audio': has_audio,
            'audio_duration': audio_duration,
            'audio_codec': audio_codec,
            'sample_rate': sample_rate,
            'channels': channels,
            'path': video_path
        }

    except Exception as e:
        print(f"⚠️ Error getting info for {video_path}: {e}")
        traceback.print_exc()
        return None

def standardize_video(video_path, target_specs, temp_dir):
    """Standardize video to ensure consistent encoding parameters across all files."""
    info = get_video_info(video_path)
    if not info:
        return None

    needs_standardization = False
    reasons = []

    # Check video parameters
    if info['width'] != target_specs['width'] or info['height'] != target_specs['height']:
        needs_standardization = True
        reasons.append(f"resolution ({info['width']}x{info['height']} → {target_specs['width']}x{target_specs['height']})")

    if abs(info['fps'] - target_specs['fps']) > 0.1:
        needs_standardization = True
        reasons.append(f"fps ({info['fps']:.1f} → {target_specs['fps']})")

    # Check audio parameters
    if not info['has_audio']:
        needs_standardization = True
        reasons.append("missing audio")
    elif info['sample_rate'] != target_specs['sample_rate'] or info['channels'] != target_specs['channels']:
        needs_standardization = True
        reasons.append(f"audio format ({info['sample_rate']}Hz/{info['channels']}ch → {target_specs['sample_rate']}Hz/{target_specs['channels']}ch)")

    # Check for potential audio sync issues (audio/video duration mismatch)
    if info['has_audio'] and info['audio_duration']:
        duration_diff = abs(info['duration'] - info['audio_duration'])
        if duration_diff > 0.1:  # More than 100ms difference
            needs_standardization = True
            reasons.append(f"audio sync issue (A/V duration diff: {duration_diff:.3f}s)")

    if not needs_standardization:
        print(f"✅ {os.path.basename(video_path)} - already standardized")
        return video_path

    # Standardize the video
    print(f"🔧 Standardizing {os.path.basename(video_path)}: {', '.join(reasons)}")

    standardized_path = os.path.join(temp_dir, f"std_{os.path.basename(video_path)}")

    try:
        ffmpeg_cmd = [
            'ffmpeg', '-i', video_path, '-y'
        ]

        # Add silent audio track if missing
        if not info['has_audio']:
            ffmpeg_cmd.extend([
                '-f', 'lavfi', '-i', 'anullsrc=channel_layout=stereo:sample_rate=24000'
            ])

        # Video encoding with strict parameters
        ffmpeg_cmd.extend([
            '-c:v', 'libx264',
            '-vf', f'scale={target_specs["width"]}:{target_specs["height"]}:force_original_aspect_ratio=decrease,pad={target_specs["width"]}:{target_specs["height"]}:(ow-iw)/2:(oh-ih)/2,setsar=1',
            '-r', str(target_specs['fps']),
            '-pix_fmt', 'yuv420p',
            '-profile:v', 'high',
            '-level', '4.0',
            '-preset', 'medium',
            '-crf', '18',
            '-vsync', 'cfr',  # Constant frame rate
            '-force_key_frames', 'expr:gte(t,n_forced*2)',  # Keyframes every 2 seconds
        ])

        # Audio encoding with strict parameters
        if info['has_audio']:
            ffmpeg_cmd.extend([
                '-c:a', 'aac',
                '-b:a', '128k',
                '-ar', str(target_specs['sample_rate']),
                '-ac', str(target_specs['channels']),
                '-af', 'aresample=async=1:min_hard_comp=0.100000:first_pts=0'  # Audio resampling with sync
            ])
        else:
            ffmpeg_cmd.extend([
                '-c:a', 'aac',
                '-b:a', '128k',
                '-ar', str(target_specs['sample_rate']),
                '-ac', str(target_specs['channels']),
                '-map', '0:v:0', '-map', '1:a:0'
            ])

        # Timing and container parameters
        ffmpeg_cmd.extend([
            '-avoid_negative_ts', 'make_zero',
            '-fflags', '+genpts+igndts',
            '-movflags', '+faststart',
            '-max_muxing_queue_size', '2048',
            standardized_path
        ])

        result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, check=True)

        # Verify the standardized video
        new_info = get_video_info(standardized_path)
        if new_info and new_info['has_audio']:
            print(f"✅ Standardized: {os.path.basename(video_path)}")
            return standardized_path
        else:
            print(f"❌ Standardization verification failed for {video_path}")
            return None

    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to standardize {video_path}: {e}")
        print(f"Error output: {e.stderr}")
        return None

def create_concat_file(video_files, temp_dir):
    """Create a concat file for ffmpeg with proper escaping and verification."""
    concat_file = os.path.join(temp_dir, "concat_list.txt")

    try:
        with open(concat_file, 'w', encoding='utf-8') as f:
            for video_file in video_files:
                # Verify file exists and has audio
                if not os.path.exists(video_file):
                    print(f"❌ Video file not found: {video_file}")
                    return None

                info = get_video_info(video_file)
                if not info or not info['has_audio']:
                    print(f"❌ Video file missing audio: {video_file}")
                    return None

                # Use absolute paths and escape for concat demuxer
                abs_path = os.path.abspath(video_file)
                escaped_path = abs_path.replace("\\", "/").replace("'", "'\"'\"'")
                f.write(f"file '{escaped_path}'\n")

        print(f"📝 Created concat file with {len(video_files)} verified videos")
        return concat_file

    except Exception as e:
        print(f"❌ Error creating concat file: {e}")
        return None

def concatenate_videos_improved(video_files, output_path, temp_dir):
    """Improved video concatenation with enhanced audio sync handling."""
    concat_file = create_concat_file(video_files, temp_dir)
    if not concat_file:
        return False

    print(f"\n🎬 Concatenating {len(video_files)} videos with improved audio sync...")

    try:
        # Calculate total duration for progress tracking
        total_duration = 0
        for video_file in video_files:
            info = get_video_info(video_file)
            if info:
                total_duration += info['duration']

        # Create progress bar
        pbar = tqdm(total=total_duration, desc="Concatenating", unit="sec",
                   bar_format='{l_bar}{bar}| {n:.1f}/{total:.1f}s [{elapsed}<{remaining}]')

        # Enhanced concatenation command with stream copy for better performance
        # and audio sync preservation
        ffmpeg_cmd = [
            'ffmpeg',
            '-f', 'concat',
            '-safe', '0',
            '-i', concat_file,
            # Use stream copy since all videos are now standardized
            '-c:v', 'copy',
            '-c:a', 'copy',
            # Critical timing parameters
            '-avoid_negative_ts', 'make_zero',
            '-fflags', '+genpts',
            '-movflags', '+faststart',
            # Ensure proper stream mapping
            '-map', '0:v:0',
            '-map', '0:a:0',
            '-y',
            output_path
        ]

        print(f"🎬 Running improved concatenation...")
        print(f"Command: {' '.join(ffmpeg_cmd[:10])}...")  # Show first part of command

        # Run with progress tracking
        process = subprocess.Popen(
            ffmpeg_cmd,
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1
        )

        def parse_progress(line):
            if "time=" in line:
                try:
                    time_str = line.split("time=")[1].split()[0]
                    if ':' in time_str:
                        parts = time_str.split(':')
                        if len(parts) == 3:
                            h, m, s = parts
                            current_sec = int(h)*3600 + int(m)*60 + float(s)
                        else:
                            current_sec = float(time_str)
                    else:
                        current_sec = float(time_str)

                    # Update progress bar
                    if current_sec > pbar.n:
                        pbar.update(current_sec - pbar.n)
                except (ValueError, IndexError):
                    pass

        # Process output with error monitoring
        stderr_output = []
        while True:
            line = process.stderr.readline()
            if not line and process.poll() is not None:
                break
            if line:
                stderr_output.append(line.strip())
                parse_progress(line.strip())

        process.wait()
        pbar.close()

        if process.returncode == 0:
            # Comprehensive verification of the output
            final_info = get_video_info(output_path)
            if final_info:
                print(f"✅ Successfully created final video!")
                print(f"   📁 File: {output_path}")
                print(f"   ⏱️  Duration: {final_info['duration']:.1f} seconds ({final_info['duration']/60:.1f} minutes)")
                print(f"   📺 Resolution: {final_info['width']}x{final_info['height']}")
                print(f"   🎵 Audio: {'Yes' if final_info['has_audio'] else 'No'}")
                if final_info['audio_duration']:
                    sync_diff = abs(final_info['duration'] - final_info['audio_duration'])
                    print(f"   🔊 Audio sync: {sync_diff:.3f}s difference ({'✅ Good' if sync_diff < 0.1 else '⚠️  Check'})")
                print(f"   📊 File size: {os.path.getsize(output_path) / (1024*1024):.1f} MB")

                # Additional audio stream verification
                audio_streams_cmd = [
                    'ffprobe', '-v', 'error', '-select_streams', 'a',
                    '-show_entries', 'stream=index,codec_name,duration,start_time',
                    '-of', 'csv=p=0', output_path
                ]
                audio_check = subprocess.run(audio_streams_cmd, capture_output=True, text=True)
                if audio_check.returncode == 0 and audio_check.stdout.strip():
                    print(f"   🎧 Audio stream verified: {audio_check.stdout.strip()}")
                else:
                    print(f"   ⚠️  Audio stream verification failed")

                return True
            else:
                print("⚠️ Video created but unable to verify properties")
                return True
        else:
            print(f"❌ Concatenation failed with return code: {process.returncode}")
            # Print stderr for debugging
            if stderr_output:
                print("Error output (last 10 lines):")
                for line in stderr_output[-10:]:
                    print(f"  {line}")
            return False

    except Exception as e:
        print(f"❌ Error during concatenation: {e}")
        traceback.print_exc()
        return False

def main():
    # Configuration
    INPUT_DIR = "chapter-videos"
    OUTPUT_FILE = "complete_video.mp4"

    # Target specifications for standardization
    TARGET_SPECS = {
        'width': 1920,
        'height': 1080,
        'fps': 60,
        'sample_rate': 24000,
        'channels': 2
    }

    print("🎬 Enhanced Chapter Video Concatenation Script")
    print("   🔧 With Advanced Audio Sync Fixes")
    print("=" * 60)

    # Check input directory
    if not os.path.exists(INPUT_DIR):
        print(f"❌ Chapter videos directory '{INPUT_DIR}' not found!")
        return

    # Get all MP4 files sorted numerically
    video_files = []
    for file in os.listdir(INPUT_DIR):
        if file.lower().endswith('.mp4'):
            video_files.append(os.path.join(INPUT_DIR, file))

    if not video_files:
        print(f"❌ No MP4 files found in '{INPUT_DIR}'")
        return

    # Sort numerically by extracting numbers from filename
    video_files.sort(key=lambda x: int("".join(filter(str.isdigit, os.path.basename(x))))
                    if any(c.isdigit() for c in os.path.basename(x)) else float('inf'))

    print(f"📂 Found {len(video_files)} chapter videos:")
    for i, video in enumerate(video_files, 1):
        print(f"   {i:2d}. {os.path.basename(video)}")

    # Comprehensive analysis of videos
    print(f"\n🔍 Analyzing videos for consistency issues...")
    analysis_results = []
    issues_found = []

    for video_file in video_files:
        info = get_video_info(video_file)
        if info:
            analysis_results.append(info)
            issues = []

            if not info['has_audio']:
                issues.append("No audio")
            elif info['audio_duration'] and abs(info['duration'] - info['audio_duration']) > 0.1:
                issues.append(f"A/V sync issue ({abs(info['duration'] - info['audio_duration']):.3f}s)")

            if info['width'] != TARGET_SPECS['width'] or info['height'] != TARGET_SPECS['height']:
                issues.append(f"Resolution: {info['width']}x{info['height']}")

            if abs(info['fps'] - TARGET_SPECS['fps']) > 0.1:
                issues.append(f"FPS: {info['fps']:.1f}")

            if info['sample_rate'] != TARGET_SPECS['sample_rate']:
                issues.append(f"Sample rate: {info['sample_rate']}Hz")

            if issues:
                issues_found.append((os.path.basename(video_file), issues))
        else:
            issues_found.append((os.path.basename(video_file), ["Failed to analyze"]))

    if issues_found:
        print(f"⚠️  Found {len(issues_found)} videos with issues:")
        for filename, issues in issues_found:
            print(f"   📹 {filename}: {', '.join(issues)}")
    else:
        print("✅ All videos appear consistent")

    # Check if output file already exists
    if os.path.exists(OUTPUT_FILE):
        response = input(f"\n⚠️  Output file '{OUTPUT_FILE}' already exists. Overwrite? (y/N): ")
        if response.lower() != 'y':
            print("Operation cancelled.")
            return

    # Create temporary directory for processing
    with tempfile.TemporaryDirectory(prefix="video_concat_enhanced_") as temp_dir:
        print(f"\n🔧 Using temporary directory: {temp_dir}")

        # Standardize all videos to ensure consistency
        print("\n🔧 Standardizing videos for optimal concatenation...")
        standardized_videos = []

        for video_file in tqdm(video_files, desc="Standardizing videos"):
            standardized_video = standardize_video(video_file, TARGET_SPECS, temp_dir)
            if standardized_video:
                standardized_videos.append(standardized_video)
            else:
                print(f"❌ Failed to standardize {video_file}")
                return

        if len(standardized_videos) != len(video_files):
            print(f"❌ Only {len(standardized_videos)}/{len(video_files)} videos standardized successfully")
            return

        # Perform enhanced concatenation
        success = concatenate_videos_improved(standardized_videos, OUTPUT_FILE, temp_dir)

        if success:
            print(f"\n🎉 Enhanced concatenation completed!")
            print(f"✅ Final video saved as: {OUTPUT_FILE}")

            # Final comprehensive verification
            print(f"\n🔍 Performing final verification...")
            final_info = get_video_info(OUTPUT_FILE)
            if final_info:
                print(f"📊 Final Video Statistics:")
                print(f"   📁 File: {OUTPUT_FILE}")
                print(f"   ⏱️  Duration: {final_info['duration']:.1f} seconds ({final_info['duration']/60:.1f} minutes)")
                print(f"   📺 Resolution: {final_info['width']}x{final_info['height']}")
                print(f"   🎵 Audio: {'Yes' if final_info['has_audio'] else 'No'}")
                print(f"   📊 File size: {os.path.getsize(OUTPUT_FILE) / (1024*1024):.1f} MB")

                if final_info['audio_duration']:
                    sync_diff = abs(final_info['duration'] - final_info['audio_duration'])
                    print(f"   🔊 Audio sync verification: {sync_diff:.3f}s difference")
                    if sync_diff < 0.1:
                        print(f"   ✅ Audio sync is excellent!")
                    else:
                        print(f"   ⚠️  Audio sync may need attention")
        else:
            print(f"\n❌ Enhanced concatenation failed")
            if os.path.exists(OUTPUT_FILE):
                os.remove(OUTPUT_FILE)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⏹️  Operation cancelled by user")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        traceback.print_exc()
