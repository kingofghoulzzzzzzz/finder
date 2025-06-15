import requests
import os
import json
from tqdm import tqdm
import time
import logging
import concurrent.futures

# Configure logging
logging.basicConfig(level=logging.ERROR,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[
                        logging.FileHandler("tts_conversion_errors.log"),
                        logging.StreamHandler()
                    ])

def text_to_speech(text, csrf_token, session_cookie):
    """Convert text to speech using texttospeech.online API with retry mechanism."""
    url = "https://texttospeech.online/home/tryme_action/"
    headers = {
        "accept": "*/*",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": "en-US,en;q=0.9,cs;q=0.8,es;q=0.7,ar;q=0.6",
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "cookie": f"site_lang=english; csrf_cookie_name={csrf_token}; ci_session={session_cookie}",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    }
    payload = {
        "csrf_test_name": csrf_token,
        "front_tryme_language": "en-US",
        "front_tryme_voice": "NJ8T7lsYz6807a59702179cfa9e078954784f43e7lnsAt5PVC_neural",
        "front_tryme_text": text
    }

    for attempt in range(200):
        try:
            response = requests.post(url, headers=headers, data=payload, timeout=20)
            response.raise_for_status()
            result = response.json()
            return result.get("tts_uri") if result.get("result") else None
        except Exception as e:
            time.sleep(5)
    return None

def save_audio_file(url, output_path):
    """Download and save the audio file from the given URL"""
    try:
        response = requests.get(url, timeout=20)
        response.raise_for_status()
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'wb') as f:
            f.write(response.content)
        return True
    except Exception as e:
        logging.error(f"Failed to download audio: {str(e)}")
        return False

def process_text_file(text_file, chapter_path, output_base_dir, csrf_token, session_cookie):
    """Process a single text file and return success status"""
    try:
        with open(text_file, 'r', encoding='utf-8') as f:
            text = f.read().strip()
        if not text:
            return False

        audio_url = text_to_speech(text, csrf_token, session_cookie)
        if not audio_url:
            return False

        relative_path = os.path.relpath(text_file, chapter_path)
        output_path = os.path.join(
            output_base_dir,
            os.path.basename(chapter_path),
            os.path.splitext(relative_path)[0] + ".mp3"
        )
        return save_audio_file(audio_url, output_path)
    except Exception as e:
        logging.error(f"Error processing {text_file}: {str(e)}")
        return False

def process_chapter(chapter_path, output_base_dir, csrf_token, session_cookie):
    """Process all text files in a chapter directory"""
    chapter_name = os.path.basename(chapter_path)
    text_files = [os.path.join(root, f)
                 for root, _, files in os.walk(chapter_path)
                 for f in files if f.endswith('.txt')]

    if not text_files:
        return chapter_name, 0, 0

    success = 0
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = {executor.submit(process_text_file, tf, chapter_path, output_base_dir, csrf_token, session_cookie): tf
                  for tf in text_files}

        for future in tqdm(concurrent.futures.as_completed(futures), total=len(text_files),
                         desc=f"Chapter {chapter_name}", leave=False):
            if future.result():
                success += 1

    return chapter_name, success, len(text_files) - success

def main():
    # Configuration
    CSRF_TOKEN = "6b2c71b51eda8cec742b5c2ae4fbb9cc"
    SESSION_COOKIE = "851rdk25ukhrprdajkbib2hq9g08r4p4"
    TEXT_BASE_DIR = "chapters-panels-text"
    OUTPUT_BASE_DIR = "chapters-panels-speech"

    if not os.path.exists(TEXT_BASE_DIR):
        print(f"Directory '{TEXT_BASE_DIR}' not found.")
        return

    # Find chapters to process
    chapter_dirs = []
    for chapter in os.listdir(TEXT_BASE_DIR):
        chapter_path = os.path.join(TEXT_BASE_DIR, chapter)
        output_path = os.path.join(OUTPUT_BASE_DIR, chapter)
        if os.path.isdir(chapter_path) and not os.path.exists(output_path):
            chapter_dirs.append(chapter_path)
        elif os.path.isdir(chapter_path):
            print(f"Skipping chapter {chapter} - already processed")

    if not chapter_dirs:
        print("No chapters to process.")
        return

    print(f"Processing {len(chapter_dirs)} chapters...")
    results = []

    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = [executor.submit(process_chapter, cp, OUTPUT_BASE_DIR, CSRF_TOKEN, SESSION_COOKIE)
                  for cp in chapter_dirs]

        for future in tqdm(concurrent.futures.as_completed(futures), total=len(chapter_dirs),
                          desc="Total Progress"):
            name, success, errors = future.result()
            results.append((name, success, errors))
            tqdm.write(f"{name}: {success} succeeded, {errors} failed")

    total_success = sum(r[1] for r in results)
    total_errors = sum(r[2] for r in results)

    print(f"\nCompleted! {total_success} files succeeded, {total_errors} failed")
    print(f"Results saved in: {OUTPUT_BASE_DIR}")

if __name__ == "__main__":
    main()
