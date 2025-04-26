import requests
import os
import time
import json
from urllib.parse import urlparse, quote_plus

# --- Configuration ---
POKEMON_TAG_MAP = {
    "Clodsire": "clodsire",
    "Rotom-Mow": "rotom_(mow)",
    "Rotom-Frost": "rotom_(frost)",
    "Blaziken-Mega": "mega_blaziken",
    "Obstagoon": "obstagoon",
    "Meloetta-Aria": "meloetta_(aria)",
}

MAX_IMAGES_PER_POKEMON = 500 # Adjust as needed, but start reasonably small!

OUTPUT_DIR = "./pokemon_pics/web_scrape"

API_URL = "https://danbooru.donmai.us/posts.json"

SAFETY_FILTER = "-rating:explicit -rating:questionable rating:safe" # Prioritize safe, exclude explicit/questionable

REQUEST_DELAY = 1.1

# User-Agent
HEADERS = {
    'User-Agent': 'PokemonDatasetScraper/1.0'
}

# --- End Configuration ---

def download_image_from_booru(post, output_subdir):
    """Downloads an image from a Danbooru post dictionary."""
    if 'file_url' not in post or not post['file_url']:
        print(f"  Skipping post ID {post.get('id', 'N/A')} - No file_url found.")
        return False
    if 'id' not in post:
         print(f"  Skipping post with URL {post.get('file_url', 'N/A')} - No ID found.")
         return False


    image_url = post['file_url']
    post_id = post['id']
    file_ext = post.get('file_ext', '')
    if not file_ext: # Try to guess from URL if missing
        try:
            path = urlparse(image_url).path
            file_ext = os.path.splitext(path)[1].lstrip('.')
        except Exception:
            file_ext = 'jpg' # Last resort guess

    filename = os.path.join(output_subdir, f"{post_id}.{file_ext}")

    if os.path.exists(filename):
        print(f"  Skipping post ID {post_id} - File already exists: {filename}")
        return False # Indicate already exists, not a failure

    print(f"  Downloading Post ID {post_id} -> {filename}...")
    try:
        time.sleep(REQUEST_DELAY) # Wait BEFORE downloading image
        img_response = requests.get(image_url, headers=HEADERS, stream=True, timeout=30)
        img_response.raise_for_status()

        with open(filename, 'wb') as f:
            for chunk in img_response.iter_content(chunk_size=8192):
                f.write(chunk)
        # print(f"  Successfully downloaded {filename}")
        return True # Indicate successful download

    except requests.exceptions.RequestException as e:
        print(f"  Error downloading {image_url} (Post ID {post_id}): {e}")
        # Optionally remove partially downloaded file
        if os.path.exists(filename):
            try:
                os.remove(filename)
            except OSError:
                pass
        return False
    except Exception as e:
        print(f"  An unexpected error occurred saving image for Post ID {post_id}: {e}")
        return False


def fetch_booru_posts(tag, limit_per_pokemon):
    """Fetches post data from Danbooru API for a given tag, handling pagination."""
    posts = []
    page = 1
    downloaded_count = 0
    max_attempts = 5 # Max attempts per page before giving up
    consecutive_failures = 0

    # Construct the search tags string
    search_tags = f"{tag} {SAFETY_FILTER}".strip()
    print(f"  Fetching posts for tags: '{search_tags}'")

    session = requests.Session()
    session.headers.update(HEADERS)

    while downloaded_count < limit_per_pokemon:
        print(f"\n  Requesting page {page} for tag '{tag}'...")
        params = {
            'tags': search_tags,
            'limit': min(200, limit_per_pokemon - downloaded_count), # Request up to 200 (API max) or remaining needed
            'page': page
        }

        try:
            time.sleep(REQUEST_DELAY) # Wait BEFORE making API call
            response = session.get(API_URL, params=params, timeout=20)
            response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)

            # Check content type before parsing JSON
            content_type = response.headers.get('content-type', '').lower()
            if 'application/json' not in content_type:
                 print(f"  Error: Expected JSON response but received Content-Type: {content_type}")
                 print(f"  Response text (first 500 chars): {response.text[:500]}")
                 consecutive_failures += 1
                 if consecutive_failures >= max_attempts:
                     print(f"  Too many consecutive errors fetching page {page}. Stopping for tag '{tag}'.")
                     break
                 continue # Try next page or break

            page_posts = response.json()
            consecutive_failures = 0 # Reset failures on success

            if not page_posts:
                print(f"  No more posts found for tag '{tag}' on page {page}.")
                break # Exit loop if no more posts are returned

            posts.extend(page_posts)
            downloaded_count = len(posts) # Update count based on fetched post *metadata*
            print(f"  Fetched {len(page_posts)} posts on page {page}. Total posts fetched so far: {downloaded_count}")

            page += 1 # Go to the next page for the next iteration

            # Optional: Break if fewer posts were returned than requested limit (likely end of results)
            if len(page_posts) < params['limit'] and params['limit'] == 200:
                 print("  Received fewer posts than limit, likely end of results.")
                 # We can break here, or let the next loop fetch normally and exit if page_posts is empty.
                 # Let's let the next loop confirm emptiness.


        except requests.exceptions.HTTPError as e:
             print(f"  HTTP Error fetching page {page} for tag '{tag}': {e.response.status_code} {e.response.reason}")
             print(f"  Response text (first 500 chars): {e.response.text[:500]}")
             consecutive_failures += 1
             if e.response.status_code == 429: # Too Many Requests
                 print("  Rate limit hit (429)! Increasing delay and retrying after a pause...")
                 time.sleep(10) # Longer pause after a 429
             elif consecutive_failures >= max_attempts:
                 print(f"  Too many consecutive HTTP errors fetching page {page}. Stopping for tag '{tag}'.")
                 break
             # Don't increment page on failure, retry same page (implicitly by continuing loop)
             continue

        except requests.exceptions.RequestException as e:
            print(f"  Network error fetching page {page} for tag '{tag}': {e}")
            consecutive_failures += 1
            if consecutive_failures >= max_attempts:
                print(f"  Too many consecutive network errors fetching page {page}. Stopping for tag '{tag}'.")
                break
            time.sleep(5) # Wait a bit longer after network errors
            continue # Retry same page

        except json.JSONDecodeError as e:
            print(f"  Error decoding JSON response from page {page} for tag '{tag}': {e}")
            print(f"  Response text (first 500 chars): {response.text[:500]}")
            consecutive_failures += 1
            if consecutive_failures >= max_attempts:
                print(f"  Too many consecutive JSON errors fetching page {page}. Stopping for tag '{tag}'.")
                break
            continue # Try next page or break

        # Safety break if something causes an infinite loop (e.g., API always returning data)
        if page > (limit_per_pokemon // 100) + 50: # Heuristic page limit
             print(f"  Warning: Reached page limit heuristic ({page}). Stopping fetch for tag '{tag}' to prevent potential infinite loop.")
             break


    print(f"\nFinished fetching metadata for tag '{tag}'. Total posts found: {len(posts)}")
    # Return only up to the requested limit, even if more metadata was fetched
    return posts[:limit_per_pokemon]


# --- Main Execution ---
if __name__ == "__main__":
    print("Starting Pokémon Image Downloader...")
    print(f"--- Using Source: {API_URL} ---")
    print(f"--- Max Images Per Pokémon: {MAX_IMAGES_PER_POKEMON} ---")
    print(f"--- Safety Filter: '{SAFETY_FILTER}' ---")
    print(f"--- Request Delay: {REQUEST_DELAY}s ---")
    print(f"--- Output Directory: {OUTPUT_DIR} ---")
    print("\n!! WARNING: THIS CAN DOWNLOAD LARGE AMOUNTS OF DATA !!")
    print("!! WARNING: REVIEW DOWNLOADED IMAGES CAREFULLY FOR CONTENT !!")
    print("!! WARNING: ENSURE TAGS IN POKEMON_TAG_MAP ARE CORRECT FOR DANBOORU !!\n")

    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        print(f"Created base directory: {OUTPUT_DIR}")

    total_downloaded_count = 0
    total_attempted = 0

    for name, tag in POKEMON_TAG_MAP.items():
        print("-" * 40)
        print(f"Processing: {name} (Tag: {tag})")

        pokemon_dir = os.path.join(OUTPUT_DIR, tag)
        os.makedirs(pokemon_dir, exist_ok=True)
        print(f"  Output subdirectory: {pokemon_dir}")

        # 1. Fetch all post metadata first
        posts_to_download = fetch_booru_posts(tag, MAX_IMAGES_PER_POKEMON)
        num_posts_found = len(posts_to_download)
        total_attempted += num_posts_found
        print(f"\nFound {num_posts_found} potential images for tag '{tag}'. Starting downloads...")

        # 2. Download the images for the fetched posts
        current_pokemon_downloaded = 0
        for i, post_data in enumerate(posts_to_download):
            print(f"  Attempting download {i+1}/{num_posts_found} for tag '{tag}'...")
            if download_image_from_booru(post_data, pokemon_dir):
                 current_pokemon_downloaded += 1
            # The necessary delay is already inside download_image_from_booru or fetch_booru_posts

        print(f"\nFinished processing '{tag}'. Successfully downloaded {current_pokemon_downloaded}/{num_posts_found} images.")
        total_downloaded_count += current_pokemon_downloaded

    print("-" * 40)
    print("Download process finished.")
    print(f"Attempted to download metadata for {total_attempted} posts across all tags.")
    print(f"Successfully downloaded {total_downloaded_count} images in total.")
    print(f"Images saved in subdirectories within: {OUTPUT_DIR}")
    print("\nReminder: You will likely need to manually review, clean, and annotate these images before training a model.")