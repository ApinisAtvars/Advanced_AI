import requests
from bs4 import BeautifulSoup
import os
import time
import re
from urllib.parse import urljoin, quote_plus, urlparse
import hashlib # For unique filenames based on URL

# --- Configuration ---
POKEMON_LIST = [
    'clodsire',
    'rotom-mow',
    'rotom-frost',
    'blaziken-mega',
    'obstagoon',
    'meloetta-aria',
]

# Base directory to save images
BASE_SAVE_DIR = "/home/atvars/School/advanced_ai/Pokemon/pokemon_pics/web_scrape_2"

# Headers to mimic a browser
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.3/KHTML, like Gecko Chrome/91.0.4472.124 Safari/537.36'
}

# Delay between requests to be polite (in seconds)
REQUEST_DELAY = 2

# Set to keep track of downloaded image URLs across all sources for a Pokemon
downloaded_image_urls = set()
# --- End Configuration ---

def sanitize_filename(name):
    """Removes invalid characters for filenames."""
    # Remove invalid chars
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    # Reduce multiple underscores
    name = re.sub(r'_+', '_', name)
    # Remove leading/trailing underscores/spaces
    name = name.strip('_ ')
    # Limit length if necessary (optional)
    # max_len = 100
    # name = name[:max_len]
    return name

def get_image_extension(url, content_type=None):
    """Determines the image extension from URL or Content-Type header."""
    parsed_url = urlparse(url)
    path = parsed_url.path
    try:
        ext = os.path.splitext(path)[1].lower()
        if ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
            return ext
    except Exception:
        pass

    # Fallback to Content-Type
    if content_type:
        if 'jpeg' in content_type or 'jpg' in content_type:
            return '.jpg'
        elif 'png' in content_type:
            return '.png'
        elif 'gif' in content_type:
            return '.gif'
        elif 'webp' in content_type:
            return '.webp'

    # Default if unsure
    return '.jpg'

def download_image(img_url, save_dir, pokemon_name, source_prefix):
    """Downloads a single image if not already downloaded."""
    global downloaded_image_urls
    if img_url in downloaded_image_urls:
        # print(f"    -> Skipping duplicate: {img_url}")
        return False

    print(f"    -> Attempting to download: {img_url}")
    time.sleep(REQUEST_DELAY / 2) # Shorter delay before download attempt

    try:
        response = requests.get(img_url, headers=HEADERS, stream=True, timeout=20)
        response.raise_for_status() # Raise an exception for bad status codes

        # Check content type
        content_type = response.headers.get('Content-Type', '').lower()
        if not content_type or not content_type.startswith('image/'):
            print(f"    -> Skipped non-image content: {img_url} (Type: {content_type})")
            return False

        # Create a somewhat unique filename
        # Use hash of URL for uniqueness, prefix with source/pokemon
        url_hash = hashlib.md5(img_url.encode()).hexdigest()[:10]
        extension = get_image_extension(img_url, content_type)
        filename = f"{source_prefix}_{pokemon_name}_{url_hash}{extension}"
        filepath = os.path.join(save_dir, filename)

        # Save the image
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(1024 * 8): # Read in chunks
                f.write(chunk)

        print(f"    -> Saved: {filename}")
        downloaded_image_urls.add(img_url)
        return True

    except requests.exceptions.RequestException as e:
        print(f"    -> Error downloading {img_url}: {e}")
    except Exception as e:
        print(f"    -> General error processing {img_url}: {e}")

    return False

# --- Scraper Functions ---

def scrape_bulbapedia(pokemon_name, save_dir):
    """Scrapes images from Bulbapedia."""
    print(f"\n[Bulbapedia] Scraping for '{pokemon_name}'...")
    # Format name for Bulbapedia URL (approximations, might need refinement)
    # Common pattern: Capitalize, replace space/hyphen with underscore, add _(Pokémon)
    formatted_name = pokemon_name.replace('-', '_').replace(' ', '_').capitalize()
    # Specific fixes based on list
    if pokemon_name == 'rotom-mow': formatted_name = 'Rotom' # Mow form is on main Rotom page
    if pokemon_name == 'rotom-frost': formatted_name = 'Rotom' # Frost form is on main Rotom page
    if pokemon_name == 'blaziken-mega': formatted_name = 'Blaziken' # Mega form on main page
    if pokemon_name == 'meloetta-aria': formatted_name = 'Meloetta' # Aria form on main page

    # Handle Pokémon suffix only if not already handled by specific fix
    if pokemon_name not in ['rotom-mow', 'rotom-frost', 'blaziken-mega', 'meloetta-aria']:
         # Bulbapedia usually adds _(Pokémon) - needs URL encoding
         search_term = f"{formatted_name}_(Pokémon)"
    else:
         search_term = f"{formatted_name}_(Pokémon)" # Main pages also have suffix

    base_url = f"https://bulbapedia.bulbagarden.net/wiki/{quote_plus(search_term)}"
    print(f"  Bulbapedia URL: {base_url}")

    found_count = 0
    try:
        response = requests.get(base_url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

        # Find images - often within <a> tags linking to file pages
        image_links = soup.select('a > img') # Get images inside links first

        potential_urls = set()

        for img_tag in image_links:
            parent_a = img_tag.find_parent('a')
            if not parent_a or not parent_a.get('href'):
                continue

            file_page_url = urljoin(base_url, parent_a['href'])

            # Only follow links that likely lead to file pages
            if '/wiki/File:' not in file_page_url:
                continue

            # Extract potential direct image src (usually thumbnails)
            thumb_src = img_tag.get('src')
            if thumb_src:
                 full_thumb_url = urljoin(base_url, thumb_src)
                 # Crude filter: check if pokemon name variations are in alt text or URL
                 alt_text = img_tag.get('alt', '').lower()
                 if any(p in alt_text or p in full_thumb_url.lower() for p in pokemon_name.split('-')):
                     potential_urls.add(full_thumb_url)


            # Visit the file page to get the full resolution image
            print(f"  Checking file page: {file_page_url}")
            time.sleep(REQUEST_DELAY) # Delay before hitting file page
            try:
                file_page_resp = requests.get(file_page_url, headers=HEADERS, timeout=15)
                file_page_resp.raise_for_status()
                file_soup = BeautifulSoup(file_page_resp.content, 'html.parser')

                # Find the link to the full image - usually in div#file > a
                full_img_link = file_soup.select_one('div#file a img') # Get the img inside the main link
                if full_img_link and full_img_link.get('src'):
                     full_res_url = urljoin(file_page_url, full_img_link['src'])
                     # Check if it looks like a valid image URL from archives
                     if 'archives.bulbagarden.net' in full_res_url:
                          potential_urls.add(full_res_url)
                          print(f"    -> Found potential full-res: {full_res_url}")

            except requests.exceptions.RequestException as e:
                print(f"    -> Error fetching file page {file_page_url}: {e}")
            except Exception as e:
                 print(f"    -> Error parsing file page {file_page_url}: {e}")


        print(f"  [Bulbapedia] Found {len(potential_urls)} potential image URLs. Downloading...")
        for img_url in potential_urls:
             if download_image(img_url, save_dir, pokemon_name, "bulbapedia"):
                 found_count += 1
                 time.sleep(REQUEST_DELAY) # Delay between downloads


    except requests.exceptions.RequestException as e:
        print(f"  Error fetching Bulbapedia page for {pokemon_name}: {e}")
    except Exception as e:
        print(f"  Error parsing Bulbapedia page for {pokemon_name}: {e}")

    print(f"  [Bulbapedia] Downloaded {found_count} new images for '{pokemon_name}'.")

def scrape_zerochan(pokemon_name, save_dir):
    """Scrapes images from Zerochan."""
    print(f"\n[Zerochan] Scraping for '{pokemon_name}'...")
    # Format name for Zerochan (usually space/hyphen -> +, Capitalized words)
    # Specific handling needed for forms/mega
    if pokemon_name == 'rotom-mow': search_term = 'Rotom (Mow Form)'
    elif pokemon_name == 'rotom-frost': search_term = 'Rotom (Frost Form)'
    elif pokemon_name == 'blaziken-mega': search_term = 'Mega Blaziken'
    elif pokemon_name == 'meloetta-aria': search_term = 'Meloetta (Aria Forme)' # Zerochan uses 'Forme'
    else:
         search_term = ' '.join(word.capitalize() for word in pokemon_name.split('-'))

    base_url = f"https://www.zerochan.net/{quote_plus(search_term)}"
    query_params = {'p': 1} # Start with page 1
    found_count = 0
    max_pages = 5 # Limit number of pages to scrape to avoid excessive requests

    print(f"  Zerochan Search URL (base): {base_url}")

    while query_params['p'] <= max_pages:
        current_url = f"{base_url}?p={query_params['p']}"
        print(f"  Scraping page {query_params['p']}: {current_url}")

        try:
            response = requests.get(current_url, headers=HEADERS, timeout=20)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')

            # Find links to individual image pages (usually within #thumbs li > a)
            image_page_links = soup.select('#thumbs > li > a:first-of-type')

            if not image_page_links:
                print(f"  No more image links found on page {query_params['p']}. Stopping.")
                break # No images on this page, likely end of results

            page_potential_urls = set()
            for link in image_page_links:
                href = link.get('href')
                if href and not href.startswith(('http:', 'https:')):
                    img_page_url = urljoin(base_url, href)
                    # print(f"    Found image page link: {img_page_url}") # Debugging

                    # Now visit the image page to find the full-res link
                    time.sleep(REQUEST_DELAY) # Delay before hitting image page
                    try:
                        img_page_resp = requests.get(img_page_url, headers=HEADERS, timeout=15)
                        img_page_resp.raise_for_status()
                        img_soup = BeautifulSoup(img_page_resp.content, 'html.parser')

                        # Find the full image link (often #large or specific link)
                        # Method 1: Look for a direct link with 'static.zerochan.net'
                        full_img_tag = img_soup.select_one('a[href*="static.zerochan.net"]')
                        if not full_img_tag:
                            # Method 2: Look for the main image display if Method 1 fails
                            full_img_tag = img_soup.select_one('#large') # Often the container
                            if full_img_tag:
                                 # Check if 'a' or 'img' inside #large has the src/href
                                 inner_link = full_img_tag.find('a')
                                 if inner_link and inner_link.get('href') and 'static.zerochan.net' in inner_link.get('href'):
                                     full_img_tag = inner_link # Use the inner 'a' tag
                                 else:
                                     inner_img = full_img_tag.find('img')
                                     if inner_img and inner_img.get('src') and 'static.zerochan.net' in inner_img.get('src'):
                                         full_img_tag = inner_img # Use the inner 'img' tag
                                     else:
                                          full_img_tag = None # Reset if no valid link found


                        if full_img_tag:
                            full_res_url = full_img_tag.get('href') or full_img_tag.get('src')
                            if full_res_url:
                                page_potential_urls.add(full_res_url)
                                # print(f"      -> Found potential full-res: {full_res_url}") # Debugging
                        # else:
                            # print(f"      -> Could not find full-res link on {img_page_url}") # Debugging

                    except requests.exceptions.RequestException as e:
                        print(f"    -> Error fetching image page {img_page_url}: {e}")
                    except Exception as e:
                         print(f"    -> Error parsing image page {img_page_url}: {e}")


            print(f"  [Zerochan Page {query_params['p']}] Found {len(page_potential_urls)} potential image URLs. Downloading...")
            page_download_count = 0
            for img_url in page_potential_urls:
                if download_image(img_url, save_dir, pokemon_name, "zerochan"):
                    found_count += 1
                    page_download_count +=1
                    time.sleep(REQUEST_DELAY) # Delay between downloads

            print(f"  [Zerochan Page {query_params['p']}] Downloaded {page_download_count} new images.")

            # Check for a "next" page link to continue (or just increment page number)
            # Simple pagination: just increment page number. Zerochan often uses ?p=
            query_params['p'] += 1
            time.sleep(REQUEST_DELAY) # Delay before scraping next page

        except requests.exceptions.RequestException as e:
            print(f"  Error fetching Zerochan page {query_params['p']} for {pokemon_name}: {e}")
            break # Stop if a page fetch fails
        except Exception as e:
             print(f"  Error parsing Zerochan page {query_params['p']} for {pokemon_name}: {e}")
             break # Stop if parsing fails


    print(f"\n  [Zerochan] Total downloaded {found_count} new images for '{pokemon_name}'.")


# --- Main Execution ---
if __name__ == "__main__":
    if not os.path.exists(BASE_SAVE_DIR):
        os.makedirs(BASE_SAVE_DIR)
        print(f"Created base directory: {BASE_SAVE_DIR}")

    for pokemon in POKEMON_LIST:
        print(f"\n{'='*10} Processing: {pokemon} {'='*10}")
        pokemon_save_dir = os.path.join(BASE_SAVE_DIR, sanitize_filename(pokemon))
        if not os.path.exists(pokemon_save_dir):
            os.makedirs(pokemon_save_dir)
            print(f"Created directory for {pokemon}: {pokemon_save_dir}")

        # Reset downloaded list for each Pokemon to allow same image if relevant to multiple searches (e.g. Rotom forms)
        # If you want images to be unique ACROSS ALL pokemon, move this set outside the loop.
        downloaded_image_urls = set()

        # Call scraper functions for each source
        scrape_bulbapedia(pokemon, pokemon_save_dir)
        scrape_zerochan(pokemon, pokemon_save_dir)
        # Add calls to other scraper functions here if you implement more

        print(f"\n{'='*10} Finished processing: {pokemon} {'='*10}")
        time.sleep(REQUEST_DELAY * 2) # Longer delay between Pokemon

    print("\nScraping complete for all specified Pokémon.")