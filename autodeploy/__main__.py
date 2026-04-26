import os
from dotenv import load_dotenv

load_dotenv(".env")

from autodeploy.server import run

run(
    host="127.0.0.1",
    port=int(os.environ.get("PORT", 5000)),
)
