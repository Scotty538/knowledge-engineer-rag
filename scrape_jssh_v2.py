import os
import re
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, urldefrag


START_URL = (
    "https://map.workandincome.govt.nz/map/income-support/main-benefits/jobseeker-support/index.html"
)

BASE_DOMAIN = "map.workandincome.govt.nz"
BASE_PATH = "/map/income-support/main-benefits/jobseeker-support/"

OUTPUT_DIR = "docs/jssh"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; KnowledgeEngineerRAG/1.0)"
}


def get_page(url):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=20
    )
    response.raise_for_status()
    return response.text


def discover_urls(html):
    """Find all JSSH pages linked from the starting page."""

    soup = BeautifulSoup(html, "html.parser")

    urls = set()

    for link in soup.find_all("a", href=True):

        href = urljoin(START_URL, link["href"])

        # Remove #section fragments
        href, _ = urldefrag(href)

        parsed = urlparse(href)

        if (
            parsed.netloc == BASE_DOMAIN
            and parsed.path.startswith(BASE_PATH)
            and parsed.path.endswith(".html")
        ):
            urls.add(href)

    return sorted(urls)


def clean_page(html, url):
    """Extract useful page content and convert it to Markdown-ish text."""

    soup = BeautifulSoup(html, "html.parser")

    # Get title
    title = soup.title.get_text(" ", strip=True) if soup.title else url

    # Remove things we don't want in the knowledge base
    for tag in soup.find_all([
        "script",
        "style",
        "nav",
        "header",
        "footer",
        "noscript"
    ]):
        tag.decompose()

    # Try to find the main content
    main = (
        soup.find("main")
        or soup.find("article")
        or soup.find(id="content")
        or soup.find(class_="content")
        or soup.body
    )

    if not main:
        return title, ""

    lines = []

    for element in main.find_all([
        "h1",
        "h2",
        "h3",
        "h4",
        "p",
        "li"
    ]):

        text = element.get_text(" ", strip=True)

        if not text:
            continue

        if element.name == "h1":
            lines.append(f"# {text}")

        elif element.name == "h2":
            lines.append(f"## {text}")

        elif element.name == "h3":
            lines.append(f"### {text}")

        elif element.name == "h4":
            lines.append(f"#### {text}")

        elif element.name == "li":
            lines.append(f"- {text}")

        else:
            lines.append(text)

    # Remove duplicate blank lines
    cleaned_lines = []

    previous_blank = False

    for line in lines:

        line = re.sub(r"\s+", " ", line).strip()

        if not line:
            if not previous_blank:
                cleaned_lines.append("")
            previous_blank = True
        else:
            cleaned_lines.append(line)
            previous_blank = False

    content = "\n\n".join(cleaned_lines)

    return title, content


def safe_filename(url):
    """Create a safe filename from the URL."""

    path = urlparse(url).path

    filename = os.path.basename(path)

    if not filename:
        filename = "index.html"

    filename = os.path.splitext(filename)[0]

    filename = re.sub(r"[^a-zA-Z0-9_-]", "_", filename)

    return filename + ".md"


def main():

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("Discovering JSSH pages...")

    html = get_page(START_URL)

    urls = discover_urls(html)

    print(f"Found {len(urls)} JSSH pages.")

    print(f"\nSaving pages to: {OUTPUT_DIR}\n")

    failed = []

    for i, url in enumerate(urls, start=1):

        print(f"[{i}/{len(urls)}] {url}")

        try:

            html = get_page(url)

            title, content = clean_page(html, url)

            filename = safe_filename(url)

            output_path = os.path.join(
                OUTPUT_DIR,
                filename
            )

            markdown = f"""---
title: {title}
url: {url}
benefit: JSSH
source: Work and Income Map
---

{content}
"""

            with open(
                output_path,
                "w",
                encoding="utf-8"
            ) as f:
                f.write(markdown)

            print(f"    Saved: {output_path}")

        except Exception as e:

            print(f"    FAILED: {e}")

            failed.append({
                "url": url,
                "error": str(e)
            })

        # Be polite to the website
        time.sleep(0.3)

    # Save failures
    if failed:

        failure_path = os.path.join(
            OUTPUT_DIR,
            "failed_urls.txt"
        )

        with open(
            failure_path,
            "w",
            encoding="utf-8"
        ) as f:

            for item in failed:
                f.write(
                    f"{item['url']}\n"
                    f"ERROR: {item['error']}\n\n"
                )

    print("\n--------------------------------")
    print("Crawl complete.")
    print(f"Pages found: {len(urls)}")
    print(f"Pages failed: {len(failed)}")
    print(f"Output directory: {OUTPUT_DIR}")
    print("--------------------------------")


if __name__ == "__main__":
    main()