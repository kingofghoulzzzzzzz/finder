import requests
from bs4 import BeautifulSoup
import os
import re
import concurrent.futures
import queue
import time
from tqdm import tqdm  # Import tqdm

def download_image(session, image_url, chapter_folder, image_index, job_queue):
    """
    Downloads a single image and saves it to the specified folder using concurrent.futures.

    Args:
        session (requests.Session): The requests session.
        image_url (str): The URL of the image to download.
        chapter_folder (str): The path to the folder where the image should be saved.
        image_index (int): The index of the image (for naming).
        job_queue (queue.Queue): Queue to communicate results/exceptions.
    """
    try:
        # Correct potential triple slash in URL if present
        if image_url.startswith('https:///'):
            image_url = 'https://' + image_url[len('https:///'):]

        response = session.get(image_url, stream=True, timeout=10)
        response.raise_for_status()

        file_extension = os.path.splitext(image_url)[1].split('?')[0]
        if not file_extension:
            file_extension = '.png' # Default to PNG if no extension found

        # Changed from f"{image_index:03d}" to f"{image_index}" to remove leading zeros
        image_filename = os.path.join(chapter_folder, f"{image_index}{file_extension}")
        with open(image_filename, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        job_queue.put((True, f"Downloaded image {image_index + 1} for chapter {os.path.basename(chapter_folder)}"))
    except requests.exceptions.RequestException as e:
        error_msg = f"    Error downloading image {image_index + 1} from {image_url}: {e}"
        print(error_msg)
        job_queue.put((False, error_msg))
    except Exception as e:
        error_msg = f"    Unexpected error downloading image {image_index + 1} from {image_url}: {e}"
        print(error_msg)
        job_queue.put((False, error_msg))
    finally:
        return

def download_chapter_images(session, chapter_url, chapter_folder, chapter_num, job_queue):
    """
    Downloads all images for a given chapter using concurrent.futures, with tqdm progress bar.
    This function is generic and works for both ManhwaClan and ManhuaFast once the chapter URL is known.

    Args:
        session (requests.Session): The requests session.
        chapter_url (str): The URL of the chapter page.
        chapter_folder (str): The path to the folder where images should be saved.
        chapter_num (int): The chapter number.
        job_queue (queue.Queue): Queue to communicate results/exceptions.
    """
    try:
        print(f"Downloading chapter {chapter_num} from: {chapter_url}")
        response = session.get(chapter_url, timeout=10)
        response.raise_for_status()
        chapter_soup = BeautifulSoup(response.content, 'html.parser')

        image_urls = []
        image_index = 0
        # Look for images within 'reading-content' div or directly with 'page-break no-gaps'
        reading_content_div = chapter_soup.find('div', class_='reading-content')

        if reading_content_div:
            # Find all img tags within the reading content div
            img_elements = reading_content_div.find_all('img', class_='wp-manga-chapter-img')
            for img_element in img_elements:
                if 'data-src' in img_element.attrs:
                    image_urls.append(img_element['data-src'].strip())
                elif 'src' in img_element.attrs:
                    image_urls.append(img_element['src'].strip())
        else:
            # Fallback if 'reading-content' not found, try direct img search
            print(f"Warning: 'reading-content' div not found for chapter {chapter_num}. Attempting direct image search.")
            while True:
                image_element = chapter_soup.find('img', {'id': f'image-{image_index}'})
                if image_element:
                    if 'data-src' in image_element.attrs:
                        image_url = image_element['data-src'].strip()
                    elif 'src' in image_element.attrs:
                        image_url = image_element['src'].strip()
                    else:
                        image_url = None

                    if image_url:
                        image_urls.append(image_url)
                        image_index += 1
                    else:
                        break # No src or data-src found for this image
                else:
                    break # No more images with sequential IDs

        if not image_urls:
            error_msg = f"No images found for chapter {chapter_num} at {chapter_url}"
            print(error_msg)
            job_queue.put((False, error_msg))
            return

        # Use ThreadPoolExecutor to download images concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(download_image, session, img_url, chapter_folder, i, job_queue) for i, img_url in enumerate(image_urls)]

            # Use tqdm to display progress for this chapter
            for _ in tqdm(concurrent.futures.as_completed(futures), total=len(image_urls), desc=f"Chapter {chapter_num}", unit="image"):
                pass  # Just iterate to show progress

        print(f"Finished downloading chapter {chapter_num}.")
        job_queue.put((True, f"Finished downloading chapter {chapter_num}"))

    except requests.exceptions.RequestException as e:
        error_msg = f"Error fetching chapter {chapter_num}: {e}"
        print(error_msg)
        job_queue.put((False, error_msg))
    except Exception as e:
        error_msg = f"Unexpected error downloading chapter {chapter_num}: {e}"
        print(error_msg)
        job_queue.put((False, error_msg))


def download_manga(manga_url, num_chapters, source_type):
    """
    Downloads manga chapters and their images from a given URL, using concurrent.futures.
    Supports both ManhwaClan and ManhuaFast.

    Args:
        manga_url (str): The URL of the manga's main page.
        num_chapters (int): The number of chapters to download.
        source_type (str): 'manhwaclan' or 'manhuafast'.
    """
    if num_chapters < 1:
        print("Number of chapters must be at least 1.")
        return

    try:
        session = requests.Session()
        chapter_links = {}

        if source_type == 'manhwaclan':
            print(f"Fetching chapter list from ManhwaClan: {manga_url}")
            main_page_response = session.get(manga_url, timeout=10)
            main_page_response.raise_for_status()
            soup = BeautifulSoup(main_page_response.content, 'html.parser')

            chapter_list_items = soup.find_all('li', class_='wp-manga-chapter')
            for item in chapter_list_items:
                link_tag = item.find('a')
                if link_tag and 'href' in link_tag.attrs:
                    chapter_url = link_tag['href']
                    match = re.search(r'chapter-(\d+)/?', chapter_url)
                    if match:
                        chapter_num = int(match.group(1))
                        chapter_links[chapter_num] = chapter_url
        elif source_type == 'manhuafast':
            print(f"Generating chapter links for ManhuaFast from: {manga_url}")
            # Construct chapter URLs directly from 1 to num_chapters
            base_manga_url = manga_url.rstrip('/') # Ensure no trailing slash for consistent joining
            for i in range(1, num_chapters + 1):
                chapter_url = f"{base_manga_url}/chapter-{i}/"
                chapter_links[i] = chapter_url
        else:
            print("Invalid source type. Please choose 'manhwaclan' or 'manhuafast'.")
            return

        if not chapter_links:
            print(f"Could not find any chapter links for the given manga URL and source type.")
            return

        # Filter chapters based on num_chapters requested (this is already handled for manhuafast by the loop)
        # For manhwaclan, this still ensures we only download up to num_chapters
        chapters_to_download = {
            num: url for num, url in chapter_links.items()
            if 1 <= num <= num_chapters
        }

        if not chapters_to_download:
            print(f"No chapters found within the first {num_chapters} chapters range.")
            return

        sorted_chapter_links = dict(sorted(chapters_to_download.items()))
        output_folder = "chapters"
        os.makedirs(output_folder, exist_ok=True)

        job_queue = queue.Queue()
        futures = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            for chapter_num, chapter_url in sorted_chapter_links.items():
                chapter_folder = os.path.join(output_folder, f"Chapter {chapter_num}")

                # Skip if chapter folder already exists and is not empty
                if os.path.exists(chapter_folder) and os.listdir(chapter_folder):
                    print(f"Skipping Chapter {chapter_num} - folder already exists")
                    continue

                os.makedirs(chapter_folder, exist_ok=True)
                future = executor.submit(download_chapter_images, session, chapter_url, chapter_folder, chapter_num, job_queue)
                futures.append(future)

            # Wait for all chapters to download, with a progress bar
            for _ in tqdm(concurrent.futures.as_completed(futures), total=len(sorted_chapter_links), desc="Total Chapters", unit="chapter"):
                pass

        # Process results/exceptions from the queue
        while not job_queue.empty():
            success, message = job_queue.get()
            if success:
                print(message)
            else:
                print(message)

        print("Download complete!")
        session.close()

    except requests.exceptions.RequestException as e:
        print(f"Error during manga download: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    manga_link = "https://manhuafast.net/manga/apocalypse-sword-god/"
    source_choice = None

    if "manhuafast.net/manga" in manga_link:
        source_choice = 'manhuafast'
        print("Detected source: ManhuaFast")
    elif "manhwaclan.com/manga" in manga_link:
        source_choice = 'manhwaclan'
        print("Detected source: ManhwaClan")
    else:
        print("Could not automatically detect source from the provided URL. Please ensure it's a valid ManhwaClan or ManhuaFast manga URL.")
        exit()

    while True:
        try:
            num = int(input("Enter the number of chapters to extract (minimum is 1): "))
            if num >= 1:
                break
            else:
                print("Number of chapters must be at least 1.")
        except ValueError:
            print("Invalid input. Please enter a number.")

    download_manga(manga_link, num, source_choice)
