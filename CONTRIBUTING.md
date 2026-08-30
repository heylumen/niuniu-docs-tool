# Contributing to 牛牛文档工具

Thanks for your interest in contributing! 🎉

## Development Setup

```bash
# 1. Clone the repo
git clone <repo-url>
cd 牛牛文档工具

# 2. Create virtual environment
python -m venv .venv

# 3. Activate it (Windows)
.venv\Scripts\activate

# 4. Install dependencies
pip install -r requirements.txt

# 5. Run the app
python src/app_webview.py
```

## Before You Commit

All contributions must pass the pre-commit gate:

```bash
# Run unit tests (85 tests, all must pass)
python -m unittest discover -s tests -p "test_*.py" -v

# Run the review gate (11 static checks, EXIT must be 0)
python scripts/review_check.py
```

The gate checks for: syntax errors, swallowed exceptions, debug print residue, giant files, unit test coverage, Python↔JS contract drift, version hardcoding, dangerous functions, and hand-written CSV concatenation.

## Code Style

- **Python**: Follow PEP 8. No bare `except: pass` (use `contextlib.suppress` with a comment).
- **JavaScript**: Use `var` (not `let`/`const`) for consistency with the existing codebase.
- **CSS**: Use CSS variables (`:root` / `[data-theme="dark"]`), never hardcode colors.
- **Version**: The only source of truth is the `VERSION` file. Never hardcode version numbers in code.

## Architecture

| What you're changing | Where to look |
|---|---|
| UI / styles / interactions | `src/app.html` |
| Window control, file list, progress callbacks | `src/app_webview.py` (`Api` class) |
| 9 business functions (`exec_*`) | `src/core/api_business.py` (`BusinessApiMixin`) |
| Algorithms / data processing | `src/core/*.py` |

## Pull Request Process

1. Create a feature branch: `git checkout -b feature/your-feature`
2. Make your changes
3. Ensure tests and gate pass
4. Commit with a descriptive message
5. Open a Pull Request

## Reporting Bugs

Please include:
- Windows version and DPI scaling
- Python version (if running from source)
- Steps to reproduce
- Expected vs actual behavior
