# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

import importlib.metadata

project = "eos"
copyright = "2025, UNC Robotics"
author = "Angelos Angelopoulos"
release = importlib.metadata.version("eos")

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx_design",
    "sphinx_copybutton",
    "sphinx_click",
]

exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

templates_path = ["_templates"]

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "pydata_sphinx_theme"
html_title = "EOS - Experiment Orchestration System"
html_static_path = ["_static"]
html_css_files = [
    "custom.css",
]

html_show_sourcelink = False

html_theme_options = {
    "logo": {
        "text": "Experiment Orchestration System",
        "image_light": "_static/img/eos-logo.png",
        "image_dark": "_static/img/eos-logo.png",
    },
    "navigation_with_keys": True,
    "navbar_align": "left",
    "show_toc_level": 1,
    "pygments_light_style": "default",
    "pygments_dark_style": "github-dark",
    "icon_links": [
        {
            "name": "GitHub",
            "url": "https://github.com/UNC-Robotics/eos",
            "icon": "fa-brands fa-github",
        },
        {
            "name": "LLM-friendly docs",
            "url": "llms.txt",
            "icon": "fa-solid fa-robot",
        },
    ],
}

html_context = {"default_mode": "auto"}
