import os
import cv2
import numpy as np
import torch
from ultralytics import YOLO
from typing import List

# Global model instance
global_model = None

class Model:
    def __init__(self, model_path: str):
        global global_model
        self.model = global_model
        self.model_path = model_path
        self.imported = False

    def load(self):
        global global_model
        if self.model is None:
            self.__load()
            global_model = self.model  # Update global instance

    def __load(self):
        global global_model
        if not self.imported:
            self.imported = True
        try:
            self.model = YOLO(self.model_path)  # Load YOLOv11 model directly
            print(f"Model loaded successfully from {self.model_path}")
        except Exception as e:
            print(f"Error loading AI model: {e}. Ensure the model path and compatibility are correct.")
            self.model = None  # Set to None if loading fails

    def __call__(self, *args, **kwds):
        if self.model is None:
            self.load()
            if self.model is None:
                return None
        return self.model(*args, **kwds)

def load_image(filepath: str) -> np.ndarray:
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Image not found at: {filepath}")
    return cv2.imread(filepath)

def extract_panels(image: np.ndarray, bounding_boxes: List[tuple[int, int, int, int]], padding: int = 40) -> List[np.ndarray]:
    panels = []
    height, width = image.shape[:2]
    for x1, y1, x2, y2 in bounding_boxes:
        x, y, w, h = max(0, x1 - padding), max(0, y1 - padding), min(width - x1, (x2 - x1) + 2 * padding), min(height - y1, (y2 - y1) + 2 * padding)
        panel = image[y:y + h, x:x + w]
        panels.append(panel)
    return panels

def draw_bounding_boxes(image: np.ndarray, bounding_boxes: List[tuple[int, int, int, int]], output_dir: str, filename: str) -> np.ndarray:
    image_with_boxes = image.copy()
    for x1, y1, x2, y2 in bounding_boxes:
        cv2.rectangle(image_with_boxes, (x1, y1), (x2, y2), (0, 255, 0), 2)
    boxes_dir = os.path.join(output_dir, "bounding_boxes")
    if not os.path.exists(boxes_dir):
        os.makedirs(boxes_dir)
    out_path = os.path.join(boxes_dir, filename)
    cv2.imwrite(out_path, image_with_boxes)
    return image_with_boxes

def generate_panel_blocks(image: np.ndarray, model: Model, output_dir: str, filename: str) -> tuple[List[np.ndarray], List[tuple[int, int, int, int]]]:
    # Convert to RGB for YOLOv11 (it expects RGB input)
    image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    results = model(image_rgb)  # YOLOv11 inference
    if results is None:
        return [], []

    bounding_boxes = []
    for detection in results[0].boxes:  # Access boxes from the first result
        x1, y1, x2, y2 = map(int, detection.xyxy[0].tolist()[:4])
        conf = detection.conf.item()
        if conf > 0.4:  # Confidence threshold
            bounding_boxes.append((x1, y1, x2, y2))

    if not bounding_boxes:
        return [], []

    # Sort bounding boxes by y1 coordinate (top to bottom)
    bounding_boxes.sort(key=lambda x: x[1])

    draw_bounding_boxes(image, bounding_boxes, output_dir, filename)
    panels = extract_panels(image, bounding_boxes)
    return panels, bounding_boxes

def extract_panels_from_image(image_path: str, output_dir: str, model: Model, chapter_number: int) -> None:
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    image = load_image(image_path)
    filename = os.path.basename(image_path)
    image_name, image_ext = os.path.splitext(filename)

    panel_blocks, bounding_boxes = generate_panel_blocks(image, model, output_dir, filename)

    if not panel_blocks:
        print(f"No panels detected in {filename}")
        return

    # Name panels based on chapter number and vertical position
    for panel_index, panel in enumerate(panel_blocks):
        panel_name = f"{image_name}_{panel_index}{image_ext}"
        out_path = os.path.join(output_dir, panel_name)
        cv2.imwrite(out_path, panel)
    print(f"Extracted {len(panel_blocks)} panels from {filename} and saved to {output_dir}")

def extract_panels_from_chapters(chapters_dir: str, output_dir: str, model: Model) -> None:
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    chapter_dirs = [d for d in os.listdir(chapters_dir) if os.path.isdir(os.path.join(chapters_dir, d)) and d.startswith("Chapter ")]
    chapter_dirs.sort(key=lambda x: int(x.split(" ")[1]))

    for chapter_dir in chapter_dirs:
        # Extract chapter number from directory name (e.g., "Chapter 1" -> 1)
        chapter_number = int(chapter_dir.split(" ")[1])
        chapter_path = os.path.join(chapters_dir, chapter_dir)
        chapter_output_path = os.path.join(output_dir, chapter_dir)
        if os.path.exists(chapter_output_path):
            print(f"Skipping {chapter_dir} as it already exists in the output directory")
            continue
        os.makedirs(chapter_output_path)

        image_files = [f for f in os.listdir(chapter_path) if os.path.isfile(os.path.join(chapter_path, f)) and f.lower().endswith(('.png', '.webp', '.jpg', '.jpeg'))]
        image_files.sort(key=lambda x: int(os.path.splitext(x)[0]))

        for image_file in image_files:
            image_path = os.path.join(chapter_path, image_file)
            extract_panels_from_image(image_path, chapter_output_path, model, chapter_number)

if __name__ == "__main__":
    chapters_dir = "./chapters"
    output_dir = "./chapters-panels"
    model_path = "./best.pt"  # Path to your trained YOLOv11 model

    # Initialize and load the global model
    global_model_instance = Model(model_path)
    global_model_instance.load()

    if global_model_instance.model is None:
        print("Failed to initialize the model. Exiting.")
        exit(1)

    extract_panels_from_chapters(chapters_dir, output_dir, global_model_instance)
