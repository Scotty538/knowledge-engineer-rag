import os
import re

from dotenv import load_dotenv
from openai import AzureOpenAI
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient

load_dotenv()

# -----------------------------
# Azure OpenAI
# -----------------------------

client = AzureOpenAI(
    api_key=os.environ["AZURE_FOUNDRY_API_KEY"],
    azure_endpoint=os.environ["AZURE_FOUNDRY_ENDPOINT"],
    api_version="2024-10-21",
)

embedding_deployment = os.environ["AZURE_FOUNDRY_EMBEDDING_MODEL"]
chat_deployment = os.environ["AZURE_FOUNDRY_CHAT_MODEL"]

# -----------------------------
# Azure AI Search
# -----------------------------

search_client = SearchClient(
    endpoint=os.environ["AZURE_SEARCH_ENDPOINT"],
    index_name="jssh-policy",
    credential=AzureKeyCredential(
        os.environ["AZURE_SEARCH_KEY"]
    ),
)

# -----------------------------
# Question
# -----------------------------

question = input("Question: ")

# -----------------------------
# 1. Embed the question
# -----------------------------

embedding_response = client.embeddings.create(
    model=embedding_deployment,
    input=question,
)

query_vector = embedding_response.data[0].embedding

# -----------------------------
# 2. Retrieve relevant chunks
# -----------------------------

results = search_client.search(
    search_text=None,
    vector_queries=[
        {
            "kind": "vector",
            "vector": query_vector,
            "fields": "content_vector",
            "k": 5,
        }
    ],
    select=[
        "content",
        "title",
        "section",
        "url",
        "benefit",
    ],
)

results = list(results)

# -----------------------------
# 3. Build context
# -----------------------------

context_parts = []

for i, result in enumerate(results, start=1):

    context_parts.append(
        f"""
SOURCE {i}

Title: {result["title"]}
Section: {result["section"]}

Content:
{result["content"]}
"""
    )

context = "\n".join(context_parts)

# -----------------------------
# 4. Ask the LLM
# -----------------------------

system_prompt = """
You are a knowledge-base assistant for Work and Income policy.

Answer the user's question using ONLY the information
contained in the supplied knowledge-base context.

Do not use outside knowledge.

If the context does not contain enough information to
answer the question, say exactly:

"I don't have enough information in the knowledge base."

Do not invent policy rules, rates, eligibility requirements,
dates, or other facts.

CITATIONS:

Every factual statement in your answer must be supported
by one or more of the supplied sources.

Cite sources using ONLY this format:

[Source 1]
[Source 2]
[Source 1, Source 3]

Only cite source numbers that actually appear in the
supplied context.

Do NOT write URLs.

Do NOT invent source numbers.

Keep the answer concise.
"""

user_prompt = f"""
Knowledge-base context:

{context}

User question:

{question}
"""

response = client.chat.completions.create(
    model=chat_deployment,
    messages=[
        {
            "role": "system",
            "content": system_prompt,
        },
        {
            "role": "user",
            "content": user_prompt,
        },
    ],
)

answer = response.choices[0].message.content


# -----------------------------
# 5. Validate citations
# -----------------------------

valid_source_numbers = set(range(1, len(results) + 1))

# Find every citation block, e.g.
# [Source 1]
# [Source 3, Source 4]
citation_blocks = re.findall(
    r"\[Source\s+([0-9,\s]+)\]",
    answer
)

cited_numbers = set()

for block in citation_blocks:
    numbers = re.findall(r"\d+", block)

    for number in numbers:
        cited_numbers.add(int(number))

cited_numbers = sorted(cited_numbers)

invalid_numbers = [
    number
    for number in cited_numbers
    if number not in valid_source_numbers
]


# -----------------------------
# 6. Display answer
# -----------------------------

print()
print("================================")
print("ANSWER")
print("================================")
print(answer)

# -----------------------------
# 7. Display cited sources only
# -----------------------------

print()
print("================================")
print("SOURCES")
print("================================")

if not cited_numbers:
    print("No sources cited.")

else:

    for number in cited_numbers:

        if number not in valid_source_numbers:
            continue

        result = results[number - 1]

        print()
        print(f"[Source {number}]")
        print(f"Title: {result['title']}")
        print(f"Section: {result['section']}")
        print(f"URL: {result['url']}")

# -----------------------------
# 8. Warn about invalid citations
# -----------------------------

if invalid_numbers:

    print()
    print("WARNING:")
    print(
        "The model produced invalid source number(s): "
        + ", ".join(str(n) for n in invalid_numbers)
    )
