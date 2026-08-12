# Appian Parser Web Interface

A simple web UI for uploading and processing Appian application packages.

## Setup

```bash
# From the project root
cd web

# Install Flask
pip install -r requirements.txt

# Run the server
python app.py
```

Then open http://localhost:5000 in your browser.

## Features

- Drag & drop ZIP file upload
- Sequential job IDs for each upload
- Browse all output JSON files
- Syntax-highlighted JSON viewer
- Download individual files or all outputs as ZIP

## File Structure

```
web/
├── app.py              # Flask backend
├── requirements.txt    # Python dependencies
├── static/
│   └── index.html      # Frontend UI
└── uploads/            # Created automatically
    └── {job_id}/
        ├── {original}.zip
        └── output/
            ├── manifest.json
            ├── dependencies.json
            ├── documentation_context.json
            └── objects/
                └── ...
```
