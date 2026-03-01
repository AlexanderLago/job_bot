# Job Bot — Project Conventions

## Project
Streamlit app that tailors resumes to job postings using Claude / Gemini AI.
Run with: `streamlit run app.py` (activate job_bot conda env first)

## Key Files
- `app.py` — main Streamlit app, all UI and logic
- `utils/pdf_builder.py` — ReportLab PDF resume generation
- `utils/docx_builder.py` — python-docx DOCX resume generation
- `requirements.txt` — pip dependencies
- `~/.job_bot/saved_state.json` — runtime persistence (not in repo)

## Architecture
- All session data lives in `st.session_state`
- Disk persistence via `_patch_saved()` / `_load_saved()` helpers at top of app.py
- AI tailoring: send master resume + JD to Claude/Gemini, parse JSON response
- Resume builders receive a structured `dict` and return `bytes`

## Code Style
- Python 3.11, no formatter enforced
- Keep all Streamlit UI logic in app.py
- Keep builder logic in utils/
- Avoid adding comments to lines you didn't change

## Git
- Branch: main (deploy to Streamlit Cloud on push)
- Never commit `saved_state.json` or any API keys
- Commit messages explain WHY

## Do Not Touch
- `requirements.txt` — only change if adding/removing a dependency
- The `_condense_resume()` helper controls one-page fitting — ask before changing
