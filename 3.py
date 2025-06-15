import os
import cv2
import re
import sys
import json
from tqdm import tqdm
from paddleocr import PaddleOCR
import logging
import time

# Configuration
STATUS_FILE = "chapter_status.json"

def load_status():
    """Load chapter processing status from JSON file"""
    if os.path.exists(STATUS_FILE):
        with open(STATUS_FILE, 'r') as f:
            return json.load(f)
    return {
        "skipped": []
    }

def save_status(status):
    """Save chapter processing status to JSON file"""
    with open(STATUS_FILE, 'w') as f:
        json.dump(status, f, indent=2)

def check_dependencies():
    try:
        import paddleocr
        import cv2
    except ImportError:
        print("Missing dependencies. Install with:")
        print("pip install paddleocr paddlepaddle opencv-python tqdm")
        sys.exit(1)

def setup_directories(base_dir):
    parent_dir = os.path.dirname(base_dir)
    text_dir = os.path.join(parent_dir, "chapters-panels-text")
    os.makedirs(text_dir, exist_ok=True)
    return text_dir

def initialize_ocr():
    return PaddleOCR(
        use_angle_cls=True,
        lang='en',
        det_db_box_thresh=0.3,
        use_space_char=True,
        det_db_unclip_ratio=2.0,
        show_log=False,
    )

def process_image(ocr, image_path, text_file_path):
    if os.path.exists(text_file_path):
        logging.info(f"Text file already exists: {text_file_path}. Skipping OCR for {image_path}")
        return None

    try:
        img = cv2.imread(image_path)
        if img is None:
            logging.error(f"Error: Could not read image file {image_path}")
            return None

        if len(img.shape) == 2:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
        elif img.shape[2] == 4:
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2RGB)
        elif img.shape[2] == 3:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        result = ocr.ocr(img, cls=True)

        if result is None:
            logging.warning(f"Warning: No OCR result for {image_path}")
            return None

        text_lines = []
        for block in result:
            if block is not None:
                for line in block:
                    if line is not None and len(line) >= 2:
                        text = line[1][0]
                        if text:
                            text = text.replace("<", "").replace(">", "")
                            text_lines.append(text)

        extracted_text = " ".join(text_lines) if text_lines else None

        if extracted_text:
            with open(text_file_path, 'w', encoding='utf-8') as f:
                f.write(extracted_text)
        return extracted_text

    except cv2.error as e:
        logging.error(f"OpenCV error processing {image_path}: {str(e)}")
        return None
    except Exception as e:
        logging.error(f"Error processing {image_path}: {str(e)}")
        return None

def process_chapter(ocr, chapter_path, text_base_dir, status):
    chapter_name = os.path.basename(chapter_path)
    text_chapter_dir = os.path.join(text_base_dir, chapter_name)
    os.makedirs(text_chapter_dir, exist_ok=True)

    image_files = [f for f in os.listdir(chapter_path)
                  if re.match(r'.*\.(jpg|jpeg|webp|png)$', f, re.IGNORECASE)]

    processed_count = 0
    error_count = 0

    for img_file in tqdm(image_files, desc=f"{chapter_name}", leave=False):
        img_path = os.path.join(chapter_path, img_file)
        txt_filename = os.path.splitext(img_file)[0] + ".txt"
        txt_file_path = os.path.join(text_chapter_dir, txt_filename)

        text = process_image(ocr, img_path, txt_file_path)
        if text:
            processed_count += 1
        else:
            if not os.path.exists(txt_file_path):
                error_count += 1

    # Update status based on processing results
    if error_count == 0 and processed_count > 0:
        status["skipped"].append(chapter_name)
    elif error_count > 0:
        status["skipped"].append(chapter_name)

    return processed_count, error_count

def main():
    check_dependencies()

    # Load status including skipped chapters
    status = load_status()
    skipped_chapters = set(status["skipped"])

    base_dir = "chapters-panels"
    if not os.path.exists(base_dir):
        print(f"Directory '{base_dir}' not found.")
        sys.exit(1)

    text_base_dir = setup_directories(base_dir)

    print("Initializing PaddleOCR...")
    ocr = initialize_ocr()

    chapter_dirs = []
    for d in os.listdir(base_dir):
        if os.path.isdir(os.path.join(base_dir, d)):
            # Skip chapters in the skipped list from JSON
            if d in skipped_chapters:
                print(f"Skipping chapter {d} (in skip list)")
                continue
            # Skip already processed chapters
            if d in status["skipped"]:
                print(f"Skipping chapter {d} (already processed)")
                continue
            chapter_dirs.append((d, os.path.join(base_dir, d)))

    if not chapter_dirs:
        print("No chapter folders found to process (after applying skip list).")
        return

    print(f"\nFound {len(chapter_dirs)} chapters to process (after skipping {len(skipped_chapters)} chapters).")

    total_text_files = 0
    total_errors = 0

    chunk_size = 4
    chapter_chunks = [chapter_dirs[i:i + chunk_size] for i in
                     range(0, len(chapter_dirs), chunk_size)]

    for i, chapter_chunk in enumerate(chapter_chunks):
        chunk_chapters = [c[0] for c in chapter_chunk]
        tqdm.write(f"\nProcessing chunk {i + 1}/{len(chapter_chunks)}: Chapters {chunk_chapters}")

        try:
            for chapter_name, chapter_path in tqdm(chapter_chunk, desc="Chunk Progress"):
                count, errors = process_chapter(ocr, chapter_path, text_base_dir, status)
                total_text_files += count
                total_errors += errors
                tqdm.write(f"  Chapter {chapter_name}: Extracted text from {count} pages ({errors} errors)")
                # Save status after each chapter
                save_status(status)
        except Exception as e:
            logging.error(f"Error processing chunk {i+1}: {e}")
            tqdm.write(f"  Chunk {i+1} processing failed partially. You can resume later.")
            ocr = initialize_ocr()
        finally:
            time.sleep(5)

    print(f"\nCompleted! Extracted text from {total_text_files} pages.")
    print(f"Encountered {total_errors} processing errors.")
    print(f"Text saved in: {text_base_dir}")
    print(f"Skipped chapters: {', '.join(skipped_chapters)}")

if __name__ == "__main__":
    main()
