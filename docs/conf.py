import os

extensions = [
    "sphinx_rtd_theme",
    "myst_parser",
]

html_theme = "sphinx_rtd_theme"
html_baseurl = os.environ.get("READTHEDOCS_CANONICAL_URL", "/")
project = "Zingor"
author = "Maxwell Joslyn"
project_copyright = "%Y Maxwell Joslyn"

myst_enable_extensions = ["colon_fence"]
