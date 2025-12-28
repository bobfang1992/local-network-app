# Repository Guidelines

## Project Structure & Module Organization
- `backend/` contains the FastAPI server, network scanning logic, and SQLite persistence (`backend/main.py`, `backend/network_scanner.py`, `backend/database.py`).
- `frontend/` is a React + Vite client; UI code lives in `frontend/src/` and styles in `frontend/src/App.css`.
- Root scripts (`start-*.sh`, `status.sh`, `stop-all.sh`) orchestrate local dev and process control.
- Docs live at the repo root (`README.md`, `ARCHITECTURE.md`, `WEBSOCKET_ARCHITECTURE.md`).
- Runtime data is stored outside the repo at `~/.local-network/db/devices.db`.

## Build, Test, and Development Commands
- `./start-all.sh`: start backend (with sudo) and frontend, logging to `~/.local-network/*.log`.
- `./start-backend.sh`: start backend only (requires a `.venv` in `backend/`).
- `./start-frontend.sh`: start the Vite dev server.
- `./status.sh` / `./stop-all.sh`: check or stop running services.
- Backend setup (one-time): `cd backend && uv venv && source .venv/bin/activate && uv pip install -r requirements.txt`.
- Backend dev mode: `cd backend && sudo ./dev.sh` (auto-restart on file changes).
- Frontend: `cd frontend && npm install`, then `npm run dev` or `npm run build`.

## Coding Style & Naming Conventions
- Frontend uses ESLint (`frontend/eslint.config.js`); run `npm run lint`.
- JavaScript/JSX uses 2-space indentation and single quotes (see `frontend/src/App.jsx`).
- Python code follows standard PEP 8 conventions; prefer `snake_case` and small, descriptive functions.

## Testing Guidelines
- No automated test suite is configured yet.
- Verify changes manually by running the backend and frontend and exercising the UI and scan flow.

## Commit & Pull Request Guidelines
- Commit messages in history use short, imperative phrases (e.g., "Add port scanning...").
- Include a concise summary and testing notes in PR descriptions.
- Update `CHANGELOG.md` when user-facing behavior changes.

## Security & Configuration Notes
- Network scanning requires sudo. Use `backend/start-with-sudo.sh` or `sudo ./start-all.sh`.
- Passwordless sudo setup is available via `backend/setup-passwordless-sudo.sh`.
