# Personal checklist for working from another PC

This file is for my own use when I reopen the project on another computer.

## Before starting

1. Wait for OneDrive to finish syncing the project folder.
2. Open the project root folder.
3. Run `git pull` to get the latest changes.

## Virtual environment

Try the existing virtual environment first:

```powershell
.\.venv\Scripts\Activate.ps1
python --version
```

If activation works, install/update dependencies just to be safe:

```powershell
pip install -r requirements.txt
```

If activation fails or imports are broken, recreate the virtual environment:

```powershell
rmdir /s /q .venv
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Start the app

```powershell
python app.py
```

Open: `http://localhost:8080`

## Start OpenCode

Open OpenCode from the project root so it can read:

- `README.md`
- `AGENTS.md`

## Before ending the session

1. Check changes with `git status`
2. Commit only the intended files
3. Run `git push`
4. Wait for OneDrive sync to finish before shutting down the PC

## Important notes

- Git is the source of truth, not OneDrive
- `.venv` may exist on another PC but still be unusable
- `finance.db` stays local and is ignored by Git
