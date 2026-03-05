# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information
import sphinx_rtd_theme


project = 'mcap-mcp-server'
copyright = '2026, Antoine Bodin'
author = 'Antoine Bodin'
release = "0.5.1"

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "myst_parser",
    "sphinx.ext.mathjax",         # Support LaTeX equations
    "sphinxcontrib.mermaid",      # Support Mermaid diagrams
]

# MyST Parser configuration for Mermaid and Math
myst_enable_extensions = [
    "colon_fence",      # Allows ::: fence syntax for Mermaid
    "dollarmath",       # Enables $...$ and $$...$$ for math
    "amsmath",          # Advanced math features
]

# Configure MyST to treat mermaid code fences as directives
myst_fence_as_directive = ["mermaid"]

# Suppress Pygments warnings for Mermaid (handled by sphinxcontrib.mermaid)
suppress_warnings = ["misc.highlighting_failure"]

# MathJax configuration for LaTeX rendering
mathjax3_config = {
    'tex': {
        'inlineMath': [['$', '$'], ['\\(', '\\)']],
        'displayMath': [['$$', '$$'], ['\\[', '\\]']],
    }
}

source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

templates_path = ["_templates"]
exclude_patterns = []

html_theme = "sphinx_rtd_theme"

html_theme_options = {
    "logo_only": False,             # Show logo and project name
    "prev_next_buttons_location": "bottom",
    "style_external_links": True,
    "collapse_navigation": False,
    "sticky_navigation": True,
    "navigation_depth": 4,
    "includehidden": True,
    "titles_only": False,
}

# html_logo = "_static/logo.png"
# html_favicon = "_static/favicon.png"

html_static_path = ["_static"]
html_css_files = ["custom.css"]
