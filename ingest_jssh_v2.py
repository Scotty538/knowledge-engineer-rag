import os
import glob
import re

from dotenv import load_dotenv
from openai import AzureOpenAI

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SearchField,
    SearchFieldDataType,
    VectorSearch,
    HnswAlgorithmConfiguration,
    VectorSearchProfile,
)


# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

load_dotenv()

SEARCH_ENDPOINT = os.environ["AZURE_SEARCH_ENDPOINT"]
SEARCH_KEY = os.environ["AZURE_SEARCH_KEY"]

INDEX_NAME = "jssh-policy"

EMBEDDING_DEPLOYMENT = os.environ[
    "AZURE_FOUNDRY_EMBEDDING_MODEL"
]

VECTOR_DIMENSIONS = 1536

INPUT_DIR = "docs/jssh_chunks"

BATCH_SIZE = 50

# Maximum approximate words for an embedding chunk.
# This is deliberately well below the 8192-token limit.
MAX_WORDS = 3000


# ---------------------------------------------------------
# Azure OpenAI
# ---------------------------------------------------------

client = AzureOpenAI(
    api_key=os.environ["AZURE_FOUNDRY_API_KEY"],
    azure_endpoint=os.environ["AZURE_FOUNDRY_ENDPOINT"],
    api_version="2024-10-21",
)


# ---------------------------------------------------------
# Azure AI Search
# ---------------------------------------------------------

index_client = SearchIndexClient(
    endpoint=SEARCH_ENDPOINT,
    credential=AzureKeyCredential(SEARCH_KEY),
)

search_client = SearchClient(
    endpoint=SEARCH_ENDPOINT,
    index_name=INDEX_NAME,
    credential=AzureKeyCredential(SEARCH_KEY),
)


# ---------------------------------------------------------
# Create index
# ---------------------------------------------------------

fields = [
    SearchField(
        name="id",
        type=SearchFieldDataType.String,
        key=True,
    ),

    SearchField(
        name="content",
        type=SearchFieldDataType.String,
        searchable=True,
    ),

    SearchField(
        name="title",
        type=SearchFieldDataType.String,
        searchable=True,
    ),

    SearchField(
        name="benefit",
        type=SearchFieldDataType.String,
        searchable=True,
        filterable=True,
    ),

    SearchField(
        name="source",
        type=SearchFieldDataType.String,
        searchable=True,
        filterable=True,
    ),

    SearchField(
        name="url",
        type=SearchFieldDataType.String,
    ),

    SearchField(
        name="section",
        type=SearchFieldDataType.String,
        searchable=True,
        filterable=True,
    ),

    SearchField(
        name="content_vector",
        type=SearchFieldDataType.Collection(
            SearchFieldDataType.Single
        ),
        searchable=True,
        vector_search_dimensions=VECTOR_DIMENSIONS,
        vector_search_profile_name="default-profile",
    ),
]


vector_search = VectorSearch(
    algorithms=[
        HnswAlgorithmConfiguration(
            name="hnsw"
        )
    ],
    profiles=[
        VectorSearchProfile(
            name="default-profile",
            algorithm_configuration_name="hnsw",
        )
    ],
)


index = SearchIndex(
    name=INDEX_NAME,
    fields=fields,
    vector_search=vector_search,
)


print(f"Creating/updating index: {INDEX_NAME}")

index_client.create_or_update_index(index)


# ---------------------------------------------------------
# Parse one YAML chunk block
# ---------------------------------------------------------

def parse_chunk_block(block):

    parts = block.split("---", 1)

    if len(parts) != 2:
        return None

    front_matter = parts[0].strip()
    content = parts[1].strip()

    metadata = {}

    for line in front_matter.splitlines():

        if ":" not in line:
            continue

        key, value = line.split(":", 1)

        metadata[key.strip()] = value.strip()

    if not content:
        return None

    return metadata, content


# ---------------------------------------------------------
# Split very large chunks
# ---------------------------------------------------------

def split_large_chunk(content):

    words = content.split()

    if len(words) <= MAX_WORDS:
        return [content]

    pieces = []

    for i in range(
        0,
        len(words),
        MAX_WORDS
    ):
        piece = " ".join(
            words[i:i + MAX_WORDS]
        )
        pieces.append(piece)

    return pieces


# ---------------------------------------------------------
# Load ALL chunks
# ---------------------------------------------------------

files = sorted(
    glob.glob(
        os.path.join(
            INPUT_DIR,
            "*.md"
        )
    )
)

print()
print(f"Found {len(files)} chunk files.")
print()


documents = []

large_chunks = 0


for filepath in files:

    filename = os.path.basename(filepath)

    with open(
        filepath,
        "r",
        encoding="utf-8"
    ) as f:
        text = f.read()

    # Each chunk is separated by ---
    blocks = text.split("---")

    # The file starts with --- so the useful blocks occur
    # in groups of metadata/content.
    i = 1

    while i < len(blocks):

        front_matter = blocks[i].strip()

        if not front_matter:
            i += 1
            continue

        if i + 1 >= len(blocks):
            break

        content = blocks[i + 1].strip()

        metadata = {}

        for line in front_matter.splitlines():

            if ":" not in line:
                continue

            key, value = line.split(
                ":",
                1
            )

            metadata[key.strip()] = value.strip()

        if not content:
            i += 2
            continue

        chunk_number = metadata.get(
            "chunk_id",
            "0"
        )

        base_name = os.path.splitext(
            filename
        )[0]

        base_name = re.sub(
            r"_chunks$",
            "",
            base_name
        )

        pieces = split_large_chunk(
            content
        )

        if len(pieces) > 1:
            large_chunks += 1

        for piece_number, piece in enumerate(
            pieces,
            start=1
        ):

            document_id = (
                f"jssh_"
                f"{base_name}_"
                f"{chunk_number}_"
                f"{piece_number}"
            )

            documents.append({
                "id": document_id,

                "content": piece,

                "title": metadata.get(
                    "title",
                    ""
                ),

                "benefit": metadata.get(
                    "benefit",
                    "JSSH"
                ),

                "source": metadata.get(
                    "source",
                    ""
                ),

                "url": metadata.get(
                    "url",
                    ""
                ),

                "section": metadata.get(
                    "section",
                    ""
                ),
            })

        i += 2


print(
    f"Loaded {len(documents)} chunks."
)

if large_chunks:
    print(
        f"Large chunks split: {large_chunks}"
    )

print()
print("Generating embeddings...")
print()


# ---------------------------------------------------------
# Generate embeddings
# ---------------------------------------------------------

for i in range(
    0,
    len(documents),
    BATCH_SIZE
):

    batch = documents[
        i:i + BATCH_SIZE
    ]

    texts = [
        document["content"]
        for document in batch
    ]

    response = client.embeddings.create(
        model=EMBEDDING_DEPLOYMENT,
        input=texts,
    )

    for document, embedding in zip(
        batch,
        response.data
    ):

        document[
            "content_vector"
        ] = embedding.embedding

    completed = min(
        i + BATCH_SIZE,
        len(documents)
    )

    print(
        f"[{completed}/{len(documents)}] "
        "embeddings generated"
    )


# ---------------------------------------------------------
# Upload
# ---------------------------------------------------------

print()
print("Uploading chunks to Azure AI Search...")
print()


for i in range(
    0,
    len(documents),
    BATCH_SIZE
):

    batch = documents[
        i:i + BATCH_SIZE
    ]

    result = search_client.upload_documents(
        documents=batch
    )

    failed = [
        r
        for r in result
        if not r.succeeded
    ]

    completed = min(
        i + BATCH_SIZE,
        len(documents)
    )

    if failed:

        print(
            f"[{completed}/{len(documents)}] "
            f"WARNING: {len(failed)} failed"
        )

        for failure in failed:
            print(
                failure.key,
                failure.error_message
            )

    else:

        print(
            f"[{completed}/{len(documents)}] "
            "uploaded"
        )


# ---------------------------------------------------------
# Finished
# ---------------------------------------------------------

print()
print("--------------------------------")
print("JSSH ingestion complete.")
print(f"Chunks indexed: {len(documents)}")
print(f"Index: {INDEX_NAME}")
print("--------------------------------")