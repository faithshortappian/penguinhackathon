# Appian Expression Analyzer — Browser Extension

A Chrome/Edge browser extension that reads the Appian Expression Builder, analyzes SAIL expressions in real-time, and reports syntax errors with plain-English explanations.

## Features

- **Live expression detection** — Automatically finds and reads from Appian's CodeMirror-based expression editor
- **SAIL tokenizer** — Parses SAIL syntax including functions (`a!`, `fn!`, `rule!`), variables (`ri!`, `local!`, `pv!`), operators, and literals
- **Syntax error detection:**
  - Unmatched parentheses, brackets, and braces
  - Unclosed string literals and block comments
  - Invalid variable prefixes (typos like `ri1` instead of `ri!`)
  - Unknown function names (validated against known SAIL function list)
  - Missing required arguments
  - Dangling/double commas
  - Empty parentheses on functions requiring arguments
- **Expression summary** — Plain-English explanation of what the expression does
- **Side panel UI** — Shows diagnostics, function list, and variable references
- **Manual input** — Paste expressions directly for offline analysis
- **Backend integration** — Validates rule references against your Appian application context

## Project Structure

```
frontend/
├── manifest.json          # Extension manifest (Manifest V3)
├── background.js          # Service worker for API communication
├── content.js             # DOM observer for Appian expression editor
├── content.css            # Inline indicator styles
├── parser/
│   ├── tokenizer.js       # SAIL expression tokenizer
│   ├── analyzer.js        # Static analysis engine
│   └── sail-functions.js  # Known SAIL function registry
├── panel/
│   ├── panel.html         # Side panel markup
│   ├── panel.css          # Side panel styles
│   └── panel.js           # Panel logic + analysis runner
└── icons/                 # Extension icons (SVG source)
```

## Installation (Development)

1. Open Chrome/Edge and navigate to `chrome://extensions`
2. Enable "Developer mode"
3. Click "Load unpacked" and select this `frontend/` directory
4. Navigate to your Appian environment — the extension will activate on `*.appiancloud.com`

### Icon Generation

Chrome requires PNG icons. Convert the SVGs in `icons/` to 16x16, 48x48, and 128x128 PNGs:

```bash
# Using ImageMagick:
convert icons/icon16.svg icons/icon16.png
convert icons/icon48.svg icons/icon48.png
convert icons/icon128.svg icons/icon128.png
```

Or replace with any 16/48/128px PNG files named `icon16.png`, `icon48.png`, `icon128.png`.

## Usage

1. Open an Appian Designer page with an expression editor
2. Click the extension icon to open the side panel
3. The extension automatically detects the expression editor and begins analysis
4. Or paste a SAIL expression into the "Manual Input" textarea and click Analyze

## Backend Integration

This extension works with the FastAPI backend in `../backend/`. Start the backend:

```bash
cd ../backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The extension calls the backend for application context (record types, expression rules, constants) to validate cross-references like `rule!myRule` or `const!MY_CONSTANT`.

## How the Parser Works

### Tokenization
The tokenizer (`parser/tokenizer.js`) scans the source character-by-character and produces a stream of typed tokens:
- **FUNCTION** — Prefixed calls like `a!textField`, `fn!if`, `rule!myRule`
- **VARIABLE** — Prefixed references like `ri!input`, `local!items`, `pv!status`
- **STRING/NUMBER/BOOLEAN/NULL** — Literal values
- **OPERATOR** — Arithmetic and comparison operators
- **Delimiters** — Parentheses, brackets, braces, commas, colons

### Analysis
The analyzer (`parser/analyzer.js`) walks the token stream and checks:
1. Bracket balancing (stack-based matching)
2. String/comment closure
3. Function name validation against a known registry
4. Variable prefix validation
5. Structural issues (dangling commas, empty argument lists)

Results include a severity level (error/warning/info) and exact line/column location.

## Extending

- **Add more SAIL functions**: Edit `parser/sail-functions.js`
- **Add component parameter validation**: Extend the `COMPONENT_PARAMS` map
- **Connect to Appian APIs**: The backend already provides full application context — wire it through `background.js`
