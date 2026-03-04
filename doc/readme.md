# Documentation

Documentation for **mcap-mcp-server** — a generic SQL query interface for MCAP robotics data via the Model Context Protocol.

## Documentation Policy

> **Everything in this `doc/` folder must reflect the codebase — no more, no less.**

## Setup

### Prerequisites

- **Python 3** with pip

### Install Python Dependencies

```bash
cd doc
pip install -r requirements.txt
```

## Building Documentation

Build HTML documentation:

```bash
make html
```

The generated documentation will be in `build/html/`. Open `build/html/index.html` in a web browser.

## Adding Content

1. Create or edit Markdown files in `source/`
2. Add Mermaid diagrams using code fences:
   ````markdown
   ```{mermaid}
   graph TB
       A --> B
   ```
   ````
3. Add images by placing them in `source/_static/` and referencing with:
   ````markdown
   ```{image} _static/screenshots/example.png
   :width: 600px
   :alt: Description
   ```
   ````
4. Update `index.md` to include new pages in the table of contents
5. Rebuild: `make html`
