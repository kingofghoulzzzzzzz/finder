import os
import subprocess
from tqdm import tqdm
import shutil
from PIL import Image, ImageFilter
import sys
import traceback  # Import traceback for detailed error logging

def get_audio_duration(audio_path, default_duration=1.0):
    """Get duration of audio file in seconds using ffprobe.
    Args:
        audio_path (str): Path to the audio file
        default_duration (float): Duration to return if there's an error (default: 1.0)
    Returns:
        float: Duration in seconds, or default_duration if error occurs
    Handles:
        - FFprobe errors
        - Missing files
        - Permission issues
        - Invalid audio files
        - System PATH issues
        - subprocess timeout
        - More robust error handling, including checking for specific errors
    """
    if not os.path.exists(audio_path):
        print(f"⚠️ Audio file not found: {audio_path}")
        return default_duration

    if not os.access(audio_path, os.R_OK):
        print(f"⚠️ No read permissions for audio file: {audio_path}")
        return default_duration

    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', audio_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10  # Add timeout to prevent hanging
        )

        # Check for ffprobe errors
        if result.stderr:
            error_msg = result.stderr.strip()
            if "Invalid data found" in error_msg or "Could not seek" in error_msg:
                print(
                    f"⚠️ Invalid audio file or seek error: {audio_path}.  Returning default duration."
                )
                return -1  # Return -1 to indicate an invalid audio file
            elif "No such file or directory" in error_msg:
                print(
                    f"⚠️ FFprobe could not find the file: {audio_path}.  Check the path and existence of the file."
                )
                return default_duration
            else:
                print(f"⚠️ FFprobe error for {audio_path}: {error_msg}")
                return default_duration

        duration = result.stdout.strip()
        if not duration:
            print(f"⚠️ Empty duration returned for {audio_path}")
            return default_duration

        try:
            return max(float(duration), 0.1)  # Ensure minimum 0.1s duration
        except ValueError:
            print(f"⚠️ Invalid duration format for {audio_path}: '{duration}'")
            return default_duration

    except subprocess.TimeoutExpired:
        print(f"⚠️ FFprobe timed out processing {audio_path}")
        return default_duration
    except (subprocess.SubprocessError, ValueError, OSError) as e:
        print(f"⚠️ Couldn't get duration for {audio_path}: {str(e)}")
        return default_duration
    except FileNotFoundError:
        print("⚠️ FFprobe not found. Ensure FFmpeg is installed and in your system's PATH.")
        sys.exit(1)
    except Exception as e:  # Catch any other unexpected exceptions
        print(f"⚠️ An unexpected error occurred while processing {audio_path}:")
        traceback.print_exc()  # Print the full traceback
        return default_duration

def verify_segment_has_audio(segment_path):
    """Verify that a video segment has an audio stream."""
    try:
        result = subprocess.run([
            'ffprobe', '-v', 'error', '-select_streams', 'a:0',
            '-show_entries', 'stream=codec_name', '-of', 'csv=p=0',
            segment_path
        ], capture_output=True, text=True, timeout=5)

        return result.returncode == 0 and result.stdout.strip() != ""
    except:
        return False

def create_silent_audio(duration, output_path):
    """Create a silent audio file of specified duration with precise timing."""
    try:
        ffmpeg_cmd = [
            'ffmpeg',
            '-y',
            '-f', 'lavfi',
            '-i', f'anullsrc=channel_layout=stereo:sample_rate=24000',
            '-t', str(duration),
            '-c:a', 'aac',
            '-b:a', '128k',
            '-ar', '24000',  # Explicit sample rate
            '-ac', '2',      # Explicit channel count
            '-avoid_negative_ts', 'make_zero',  # Ensure consistent timing
            output_path
        ]

        result = subprocess.run(ffmpeg_cmd, check=True, capture_output=True, text=True)
        if result.returncode == 0:
            return True
        else:
            print(f"❌ Silent audio creation failed with return code: {result.returncode}")
            return False
    except subprocess.CalledProcessError as e:
        print(f"❌ Error creating silent audio: {e}")
        print(f"Stderr: {e.stderr}")
        return False

def create_chapter_video(chapter_path, audio_base_dir, output_dir, fps=60, target_width=1920, target_height=1080):
    """Create a video for one chapter by creating individual video segments
    and concatenating them.

    Handles image processing, audio association, and video creation with ffmpeg.
    Includes comprehensive error handling and temporary file management.
    """
    chapter_name = os.path.basename(chapter_path)
    output_path = os.path.join(output_dir, f"{chapter_name}.mp4")

    # Check if output file already exists
    if os.path.exists(output_path):
        print(f"⏭️  Chapter video already exists, skipping: {chapter_name}")
        return True  # Return True to count as successful (already done)

    print(f"\n📁 Processing chapter: {chapter_name}")

    # Get all image files sorted numerically
    image_files = sorted(
        [f for f in os.listdir(chapter_path) if f.lower().endswith(('.png', '.webp', '.jpg', '.jpeg'))],
        key=lambda x: int("".join(filter(str.isdigit, x))) if any(c.isdigit() for c in os.path.basename(x)) else float('inf')
    )
    if not image_files:
        print(f"❌ No images found in {chapter_path}")
        return False

    temp_dir = os.path.join(os.getcwd(), f"temp_{chapter_name}")
    os.makedirs(temp_dir, exist_ok=True)  # Create if it doesn't exist.

    processed_images = []
    durations = []
    chapter_success = True  # Track success of chapter processing
    video_segments = []  # list to store video segments
    audio_paths = []

    # Image processing progress bar
    for img_file in tqdm(image_files, desc="Processing images"):
        img_path = os.path.join(chapter_path, img_file)
        temp_img_path = os.path.join(temp_dir, f"processed_{img_file}")

        try:
            # Open the image
            img = Image.open(img_path)
            width, height = img.size

            # Calculate aspect ratio of original image
            original_aspect_ratio = width / height
            target_aspect_ratio = target_width / target_height

            if original_aspect_ratio > target_aspect_ratio:
                # Original image is wider than target, resize by width
                resized_width = target_width
                resized_height = int(target_width / original_aspect_ratio)
                if resized_height % 2 != 0:
                    resized_height += 1
                y_offset = (target_height - resized_height) // 2
                x_offset = 0
            else:
                # Original image is taller or same aspect ratio, resize by height
                resized_height = target_height
                resized_width = int(target_height * original_aspect_ratio)
                if resized_width % 2 != 0:
                    resized_width += 1
                x_offset = (target_width - resized_width) // 2
                y_offset = 0

            resized_img = img.resize((resized_width, resized_height), Image.LANCZOS)

            # Create a blurred background image
            bg_img = img.resize((target_width, target_height),
                                            Image.LANCZOS).filter(
                ImageFilter.GaussianBlur(radius=200))

            # Create a new image and paste the resized image onto the blurred background
            new_img = Image.new('RGB', (target_width, target_height))
            new_img.paste(bg_img, (0, 0))
            new_img.paste(resized_img, (x_offset, y_offset))

            # Save the processed image to the temporary directory
            new_img.save(temp_img_path)
            processed_images.append(temp_img_path)

        except Exception as e:
            print(f"\n❌ Failed to process image {img_file}: {str(e)}")
            traceback.print_exc()  # Print detailed traceback
            chapter_success = False  # Set flag to false
            continue  # Skip to the next image

        # Find corresponding audio file
        base_name = os.path.splitext(img_file)[0]
        # Construct the audio directory relative to the script's location.  Important!
        audio_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    audio_base_dir, chapter_name)
        audio_path = None
        for ext in ['.mp3', '.wav', '.ogg', '.m4a']:
            potential_audio = os.path.join(audio_dir, f"{base_name}{ext}")
            if os.path.exists(potential_audio):
                audio_path = potential_audio
                break

        if audio_path:
            try:
                duration = get_audio_duration(audio_path)
                if duration > 0:  # check if the duration is greater than 0
                    audio_paths.append(audio_path)
                    durations.append(duration)
                elif duration == -1: # check if the audio is invalid
                    print(f"⚠️ Invalid audio file: {audio_path}. Using silent audio for this segment.")
                    # Create silent audio file
                    silent_audio_path = os.path.join(temp_dir, f"silent_{base_name}.aac")
                    if create_silent_audio(1.0, silent_audio_path):
                        audio_paths.append(silent_audio_path)
                        durations.append(1.0)
                    else:
                        audio_paths.append(None)
                        durations.append(1.0)
                else:
                    print(f"⚠️ Audio file has zero duration: {audio_path}. Using silent audio for this segment.")
                    # Create silent audio file
                    silent_audio_path = os.path.join(temp_dir, f"silent_{base_name}.aac")
                    if create_silent_audio(1.0, silent_audio_path):
                        audio_paths.append(silent_audio_path)
                        durations.append(1.0)
                    else:
                        audio_paths.append(None)
                        durations.append(1.0)
            except Exception as e:
                print(f"⚠️ Couldn't process audio {audio_path}: {str(e)}")
                traceback.print_exc()
                # Create silent audio file
                silent_audio_path = os.path.join(temp_dir, f"silent_{base_name}.aac")
                if create_silent_audio(1.0, silent_audio_path):
                    audio_paths.append(silent_audio_path)
                    durations.append(1.0)
                else:
                    audio_paths.append(None)
                    durations.append(1.0)
        else:
            # No audio file found, create silent audio
            silent_audio_path = os.path.join(temp_dir, f"silent_{base_name}.aac")
            if create_silent_audio(1.0, silent_audio_path):
                audio_paths.append(silent_audio_path)
                durations.append(1.0)
            else:
                audio_paths.append(None)
                durations.append(1.0)

    if not processed_images or not chapter_success:  # check the flag
        print("❌ No valid images processed or error during image processing. Skipping chapter.")
        shutil.rmtree(temp_dir, ignore_errors=True)  # Clean up
        return False

    # Create video segment for the current image
    segment_pbar = tqdm(total=len(processed_images), desc="Creating segments",
                                    unit="segment")  # keep pbar

    for i, img_path in enumerate(processed_images):
        base_name = os.path.splitext(os.path.basename(img_path))[0]
        segment_path = os.path.join(temp_dir, f"segment_{base_name}.mp4")

        try:
            # Create the ffmpeg command - ALWAYS include audio track
            ffmpeg_cmd = [
                'ffmpeg',
                '-y',  # Overwrite output files without asking
                '-loop', '1',
                '-framerate', str(fps),
                '-i', img_path
            ]

            # Always add audio input (either real audio or silent)
            if audio_paths[i] and os.path.exists(audio_paths[i]):
                ffmpeg_cmd.extend(['-i', audio_paths[i]])
            else:
                # Create inline silent audio if no audio file
                print(f"🔇 Creating silent audio for segment {i}")
                ffmpeg_cmd.extend([
                    '-f', 'lavfi',
                    '-i', 'anullsrc=channel_layout=stereo:sample_rate=24000'
                ])

            # Video and audio encoding parameters with precise timing
            ffmpeg_cmd.extend([
                '-c:v', 'libx264',
                '-c:a', 'aac',
                '-b:a', '128k',
                '-ar', '24000',  # Explicit audio sample rate
                '-ac', '2',      # Explicit audio channels
                '-pix_fmt', 'yuv420p',
                '-t', str(durations[i]),
                '-avoid_negative_ts', 'make_zero',  # Ensure consistent timing
                '-fflags', '+genpts',  # Generate presentation timestamps
                '-r', str(fps),  # Output frame rate
                segment_path
            ])

            # Run the command directly with subprocess
            result = subprocess.run(ffmpeg_cmd, check=True, capture_output=True, text=True)

            # Verify the segment has audio
            if not verify_segment_has_audio(segment_path):
                print(f"⚠️ Segment created without audio stream, recreating with forced audio...")
                # Try again with more explicit audio parameters
                ffmpeg_cmd_retry = [
                    'ffmpeg', '-y',
                    '-loop', '1', '-framerate', str(fps), '-i', img_path,
                    '-f', 'lavfi', '-i', 'anullsrc=channel_layout=stereo:sample_rate=24000',
                    '-c:v', 'libx264', '-c:a', 'aac', '-b:a', '128k',
                    '-ar', '24000', '-ac', '2', '-pix_fmt', 'yuv420p',
                    '-t', str(durations[i]), '-map', '0:v:0', '-map', '1:a:0',
                    '-avoid_negative_ts', 'make_zero', '-fflags', '+genpts',
                    '-r', str(fps), segment_path
                ]
                subprocess.run(ffmpeg_cmd_retry, check=True, capture_output=True, text=True)

            video_segments.append(segment_path)
            segment_pbar.update(1)

        except subprocess.CalledProcessError as e:
            error_message = e.stderr if hasattr(e, 'stderr') else 'No error details available'
            print(f"\n❌ FFmpeg Error creating segment for {img_path}:")
            print(f"Error output:\n{error_message}")
            chapter_success = False
            if os.path.exists(segment_path):
                os.remove(segment_path)
            break
        except Exception as e:
            print(f"\n❌ Unexpected error creating segment for {img_path}: {str(e)}")
            traceback.print_exc()
            chapter_success = False
            if os.path.exists(segment_path):
                os.remove(segment_path)
            break
    segment_pbar.close()  # close

    if not chapter_success:
        print("❌ Error occurred during segment creation. Skipping chapter.")
        for segment in video_segments:
            if os.path.exists(segment):
                os.remove(segment)
        shutil.rmtree(temp_dir, ignore_errors=True)
        return False

    # Concatenate the video segments
    if video_segments:
        print("\n🎬 Concatenating video segments...")
        concat_file = os.path.join(temp_dir, "concat.txt")
        try:
            with open(concat_file, 'w') as f:
                for segment in video_segments:
                    f.write(f"file '{segment}'\n")
        except Exception as e:
            print(f"❌ Error creating concat file: {e}")
            traceback.print_exc()
            for segment in video_segments:
                if os.path.exists(segment):
                    os.remove(segment)
            shutil.rmtree(temp_dir, ignore_errors=True)
            return False

        try:
            total_duration = sum(durations)
            concat_pbar = tqdm(total=total_duration, desc="Concatenating", unit="sec")

            def parse_progress(line, pbar):
                if "time=" in line:
                    time_str = line.split("time=")[1].split()[0]
                    try:
                        if ':' in time_str:
                            h, m, s = time_str.split(':')
                            current_sec = int(h)*3600 + int(m)*60 + float(s)
                        else:
                            current_sec = float(time_str)
                        pbar.update(current_sec - pbar.n)
                    except (ValueError, IndexError):
                        pass

            # Verify all segments have audio before concatenation
            print("🔍 Verifying all segments have audio streams...")
            segments_without_audio = []
            for i, segment in enumerate(video_segments):
                if not verify_segment_has_audio(segment):
                    segments_without_audio.append((i, segment))
                    print(f"⚠️ Segment {i} has no audio: {segment}")

            if segments_without_audio:
                print(f"❌ Found {len(segments_without_audio)} segments without audio. This will cause concatenation issues.")
                # Try to fix segments without audio by re-encoding with forced audio
                for i, segment in segments_without_audio:
                    print(f"🔧 Fixing segment {i}...")
                    temp_segment = segment + "_fixed.mp4"
                    fix_cmd = [
                        'ffmpeg', '-y', '-i', segment,
                        '-f', 'lavfi', '-i', 'anullsrc=channel_layout=stereo:sample_rate=24000',
                        '-c:v', 'copy', '-c:a', 'aac', '-b:a', '128k',
                        '-ar', '24000', '-ac', '2', '-map', '0:v:0', '-map', '1:a:0',
                        '-t', str(durations[i]), '-shortest', temp_segment
                    ]
                    try:
                        subprocess.run(fix_cmd, check=True, capture_output=True, text=True)
                        os.replace(temp_segment, segment)
                        print(f"✅ Fixed segment {i}")
                    except subprocess.CalledProcessError as e:
                        print(f"❌ Failed to fix segment {i}: {e}")
                        return False

            # FIXED: Use precise concatenation with timestamp alignment
            ffmpeg_cmd = [
                'ffmpeg',
                '-f', 'concat',
                '-safe', '0',
                '-i', concat_file,
                '-c:v', 'copy',
                '-c:a', 'copy',
                '-avoid_negative_ts', 'make_zero',  # Ensure consistent timing
                '-fflags', '+genpts',  # Generate presentation timestamps
                '-movflags', '+faststart',
                '-y',
                output_path
            ]

            print(f"🎬 Running concatenation command: {' '.join(ffmpeg_cmd)}")

            process = subprocess.Popen(
                ffmpeg_cmd,
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                universal_newlines=True,
                bufsize=1
            )

            while True:
                line = process.stderr.readline()
                if not line and process.poll() is not None:
                    break
                parse_progress(line, concat_pbar)

            process.wait()
            concat_pbar.close()

            if process.returncode != 0:
                print(f"❌ Concatenation failed with return code: {process.returncode}")
                raise subprocess.CalledProcessError(process.returncode, ffmpeg_cmd)

            # Verify final output has audio
            if verify_segment_has_audio(output_path):
                print(f"✅ Successfully created with audio: {output_path}")
            else:
                print(f"⚠️ Warning: Final output may not have audio: {output_path}")

            for segment in video_segments:
                if os.path.exists(segment):
                    os.remove(segment)
            shutil.rmtree(temp_dir, ignore_errors=True)
            return True
        except subprocess.CalledProcessError as e:
            print("\n❌ FFmpeg Error during concatenation:")
            print(f"Command: {' '.join(ffmpeg_cmd)}")
            print(f"Return Code: {e.returncode}")
            if os.path.exists(output_path):
                os.remove(output_path)
            for segment in video_segments:
                if os.path.exists(segment):
                    os.remove(segment)
            shutil.rmtree(temp_dir, ignore_errors=True)
            return False

        except Exception as e:
            print(f"\n❌ Unexpected error during concatenation: {str(e)}")
            traceback.print_exc()
            if os.path.exists(output_path):
                os.remove(output_path)
            for segment in video_segments:
                if os.path.exists(segment):
                    os.remove(segment)
            shutil.rmtree(temp_dir, ignore_errors=True)
            return False
    else:
        return False


def main():
    # Configuration
    IMAGE_BASE_DIR = "chapters-panels"
    AUDIO_BASE_DIR = "chapters-panels-speech"
    OUTPUT_DIR = "chapter-videos"
    FPS = 60
    TARGET_WIDTH = 1920  # changed the default
    TARGET_HEIGHT = 1080  # changed the default

    # Check directories
    if not os.path.exists(IMAGE_BASE_DIR):
        print(f"❌ Image directory '{IMAGE_BASE_DIR}' not found")
        return

    if not os.path.exists(AUDIO_BASE_DIR):
        print(
            f"⚠️ Audio directory '{AUDIO_BASE_DIR}' not found (will create videos with silent audio)")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Get chapter directories, sorted numerically
    chapter_dirs = sorted(
        [os.path.join(IMAGE_BASE_DIR, chapter)
         for chapter in os.listdir(IMAGE_BASE_DIR)
         if os.path.isdir(os.path.join(IMAGE_BASE_DIR, chapter))],
        key=lambda x: int("".join(filter(str.isdigit, os.path.basename(x)))) if any(
            c.isdigit() for c in os.path.basename(x)) else float('inf')
    )

    if not chapter_dirs:
        print("❌ No chapter folders found")
        return

    print(f"\nFound {len(chapter_dirs)} chapters to process")

    # Check for existing videos and show summary
    existing_videos = []
    new_chapters = []
    for chapter_path in chapter_dirs:
        chapter_name = os.path.basename(chapter_path)
        output_path = os.path.join(OUTPUT_DIR, f"{chapter_name}.mp4")
        if os.path.exists(output_path):
            existing_videos.append(chapter_name)
        else:
            new_chapters.append(chapter_path)

    if existing_videos:
        print(f"📋 Found {len(existing_videos)} existing videos that will be skipped:")
        for video in existing_videos:
            print(f"   ⏭️  {video}")

    if new_chapters:
        print(f"\n🎬 Will process {len(new_chapters)} new chapters:")
        for chapter in new_chapters:
            print(f"   📁 {os.path.basename(chapter)}")
    else:
        print("\n✅ All chapter videos already exist! Nothing to process.")
        return

    # Process chapters
    success_count = 0
    skipped_count = len(existing_videos)

    for chapter_path in chapter_dirs:
        if create_chapter_video(chapter_path, AUDIO_BASE_DIR, OUTPUT_DIR, FPS,
                                            TARGET_WIDTH, TARGET_HEIGHT):
            success_count += 1

    print(f"\n🎉 Completed!")
    print(f"   ✅ Successfully processed: {success_count - skipped_count} new chapters")
    print(f"   ⏭️  Skipped existing: {skipped_count} chapters")
    print(f"   📊 Total videos: {success_count}/{len(chapter_dirs)} chapters")
    print(f"   📂 Output directory: {os.path.abspath(OUTPUT_DIR)}")


if __name__ == "__main__":
    main()
