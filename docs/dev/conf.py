"""Sphinx configuration for the laserbox developer documentation.

Build with::

    sphinx-build -b html docs/dev docs/dev/_build/html

or, from inside ``docs/dev``::

    make html
"""
import os
import sys

# Make the ``src`` package importable for autodoc (repo root is two levels up).
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, REPO_ROOT)

# -- Project information ------------------------------------------------------
project = "laserbox"
author = "rjr"
copyright = "2026, rjr"

# -- General configuration ---------------------------------------------------
extensions = [
    "myst_parser",            # author narrative pages in Markdown
    "sphinx.ext.autodoc",     # pull API docs from source docstrings
    "sphinx.ext.napoleon",    # understand Google-style docstrings
    "sphinx.ext.viewcode",    # link API entries to highlighted source
    "sphinx.ext.intersphinx",
]

# RPi.GPIO only exists on the Raspberry Pi; mock it so autodoc can import the
# hardware modules on a dev box. pygame/numpy are real dependencies and present.
autodoc_mock_imports = ["RPi"]

autodoc_default_options = {
    "members": True,
    "undoc-members": True,
    "show-inheritance": True,
    "member-order": "bysource",
}

napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_include_init_with_doc = True

myst_enable_extensions = ["colon_fence", "deflist", "fieldlist"]
myst_heading_anchors = 3

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "pygame": ("https://www.pygame.org/docs", None),
}

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# -- HTML output -------------------------------------------------------------
html_theme = "furo"
html_title = "laserbox developer docs"
