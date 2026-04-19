"""Quick utility: list recent Seedance video generation tasks and their video URLs."""
import os
from dotenv import load_dotenv

load_dotenv()

from byteplussdkarkruntime import Ark
from config import SEEDANCE_BASE_URL

client = Ark(
    base_url=SEEDANCE_BASE_URL,
    api_key=os.environ["ARK_API_KEY"],
)

print("Fetching recent tasks...\n")
result = client.content_generation.tasks.list()

succeeded = []
for task in result.items:
    if task.status == "succeeded" and task.content:
        url = task.content.video_url
        if url:
            succeeded.append({"id": task.id, "url": url, "duration": task.duration})

print(f"Found {len(succeeded)} succeeded tasks out of {result.total} total\n")

for i, t in enumerate(succeeded, 1):
    print(f"Shot {i} ({t['duration']}s): {t['id']}")
    print(f"  {t['url']}\n")

if not succeeded:
    print("No succeeded tasks with video URLs found.")
