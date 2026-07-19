import os

from app.runtime import RuntimeSettings, build_runtime_app

app = build_runtime_app(RuntimeSettings.from_mapping(os.environ))
