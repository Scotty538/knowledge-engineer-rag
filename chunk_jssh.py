import os
import re
import glob

INPUT_DIR = "docs/jssh"
OUTPUT_DIR = "docs/jssh_chunks"


def clean_text(text):
    """Clean up excessive whitespace."""
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_front_matter(text):
    """Extract the simple YAML metadata at the top of the file."""
    metadata = {}

    if not text.startswith("---"):
        return metadata, text

    parts = text.split("---", 2)

    if len(parts) < 3:
        return metadata, text

    front_matter = parts[1]
    content = parts[2]

    for line in front_matter.strip().splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            metadata[key.strip()] = value.strip()

    return metadata, content.strip()


def chunk_document(filepath):
    """Split a document into chunks based on Markdown headings."""

    with open(filepath, "r", encoding="utf-8") as f:
        text = f.read()

    metadata, content = parse_front_matter(text)

    lines = content.splitlines()

    chunks = []

    current_section = "Introduction"
    current_lines = []

    for line in lines:

        # Detect Markdown headings
        if line.startswith("#"):

            # Save previous section
            if current_lines:
                section_text = clean_text(
                    "\n".join(current_lines)
                )

                if section_text:
                    chunks.append({
                        "section": current_section,
                        "content": section_text
                    })

            # Determine new section
            heading = line.lstrip("#").strip()

            current_section = heading
            current_lines = []

        else:
            current_lines.append(line)

    # Save final section
    if current_lines:
        section_text = clean_text(
            "\n".join(current_lines)
        )

        if section_text:
            chunks.append({
                "section": current_section,
                "content": section_text
            })

    return metadata, chunks


def main():

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    files = glob.glob(
        os.path.join(INPUT_DIR, "*.md")
    )

    print(f"Found {len(files)} documents.")
    print()

    total_chunks = 0

    for i, filepath in enumerate(files, start=1):

        metadata, chunks = chunk_document(filepath)

        filename = os.path.basename(filepath)
        output_filename = os.path.splitext(filename)[0] + "_chunks.md"
        output_path = os.path.join(
            OUTPUT_DIR,
            output_filename
        )

        with open(
            output_path,
            "w",
            encoding="utf-8"
        ) as f:

            for chunk_number, chunk in enumerate(chunks, start=1):

                f.write("---\n")
                f.write(f"chunk_id: {chunk_number}\n")
                f.write(f"title: {metadata.get('title', '')}\n")
                f.write(f"benefit: {metadata.get('benefit', 'JSSH')}\n")
                f.write(f"source: {metadata.get('source', '')}\n")
                f.write(f"url: {metadata.get('url', '')}\n")
                f.write(f"section: {chunk['section']}\n")
                f.write("---\n\n")

                f.write(chunk["content"])
                f.write("\n\n")

                total_chunks += 1

        print(
            f"[{i}/{len(files)}] "
            f"{filename} → {len(chunks)} chunks"
        )

    print()
    print("--------------------------------")
    print("Chunking complete.")
    print(f"Documents: {len(files)}")
    print(f"Total chunks: {total_chunks}")
    print(f"Output: {OUTPUT_DIR}")
    print("--------------------------------")


if __name__ == "__main__":
    main()