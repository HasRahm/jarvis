# Jarvis — Quick Reference

## GitHub
- **Repo:** https://github.com/HasRahm/jarvis
- **Account:** HasRahm (rahmanhasin5@gmail.com)

---

## Hermes Backend (runs on your PC)
| Key | Value |
|-----|-------|
| Port | `9000` |
| Local URL | `http://localhost:9000` |
| Health check | `http://localhost:9000/health` |
| Secret | `jarvis_hermes_2026` |

---

## Cloudflare Tunnel
- **URL changes every restart** — auto-published to Gist below
- **Discovery Gist:** https://gist.github.com/HasRahm/e99532bb52fd6b67e77f759d9921d5d8
- HUD reads this Gist on every load — phone never needs to remember the URL

---

## Vercel Frontend (deploy once)
Already deployed — auto-deploys on every `git push` to master.

| Page | URL |
|------|-----|
| Landing | https://jarvis-henna-nu.vercel.app/ |
| HUD (Mission Control) | https://jarvis-henna-nu.vercel.app/hud |
| Phone PWA | https://jarvis-henna-nu.vercel.app/phone |
| Design canvas | https://jarvis-henna-nu.vercel.app/design |
| Architecture | https://jarvis-henna-nu.vercel.app/architecture |

---

## First-time phone setup
1. Open https://jarvis-henna-nu.vercel.app/hud on phone
2. URL is auto-detected from Gist (shows "auto-detected ✓")
3. Enter secret: `jarvis_hermes_2026`
4. Click **▸ ESTABLISH LINK**
5. Done — never need to do this again

---

## Starting Jarvis (manual)
```powershell
powershell -ExecutionPolicy Bypass -File "C:\Users\hasin\jarvis\scripts\start_jarvis.ps1"
```
Starts Hermes + Cloudflare Tunnel + publishes URL to Gist.

## Auto-start (already installed)
`jarvis.bat` is in your Windows startup folder — Jarvis starts automatically every time you log in.
```
C:\Users\hasin\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\jarvis.bat
```

---

## Scripts
| Script | Purpose |
|--------|---------|
| `scripts/start_jarvis.ps1` | Start Hermes + tunnel + publish URL |
| `scripts/install_startup.ps1` | Re-install auto-start if ever removed |

---

## Environment Variables (Windows user env)
| Variable | Value |
|----------|-------|
| `GH_TOKEN` | Stored (used by startup script to update Gist) |

---

## Local URLs (while backend is running)
| Page | URL |
|------|-----|
| Health | http://localhost:9000/health |
| HUD | http://localhost:9000/hud |
| Phone PWA | http://localhost:9000/phone |
| Architecture | http://localhost:9000/architecture |
| Telemetry | http://localhost:9000/telemetry |
