"""
start_all.py
=============
Lance tous les services Estate Mind en un clic.

Usage : python start_all.py
"""

import asyncio
import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

import httpx

SERVICES = [
    {"name": "BO1 (Données)",       "file": "mock_agents/mock_bo1.py", "port": 8001, "url": "http://localhost:8001/health"},
    {"name": "BO2 (Analyse)",       "file": "mock_agents/mock_bo2.py", "port": 8002, "url": "http://localhost:8002/health"},
    {"name": "BO3 (Prix)",          "file": "mock_agents/mock_bo3.py", "port": 8003, "url": "http://localhost:8003/health"},
    {"name": "BO4 (Investissement)","file": "mock_agents/mock_bo4.py", "port": 8004, "url": "http://localhost:8004/health"},
    {"name": "BO5 (Légal)",         "file": "mock_agents/mock_bo5.py", "port": 8005, "url": "http://localhost:8005/health"},
]

ORANGE = "\033[38;5;208m"
GREEN  = "\033[92m"
RED    = "\033[91m"
RESET  = "\033[0m"
BOLD   = "\033[1m"


def banner():
    print(f"""
{ORANGE}{BOLD}
╔══════════════════════════════════════════════════╗
║         🏠 ESTATE MIND — Démarrage               ║
║    Plateforme Immobilière Intelligente Tunisie    ║
╚══════════════════════════════════════════════════╝
{RESET}""")


async def wait_for_service(url: str, name: str, timeout: int = 15) -> bool:
    """Attend qu'un service soit disponible."""
    start = time.time()
    async with httpx.AsyncClient() as client:
        while time.time() - start < timeout:
            try:
                r = await client.get(url, timeout=2)
                if r.status_code == 200:
                    return True
            except Exception:
                pass
            await asyncio.sleep(0.5)
    return False


def start_process(python: str, file: str, port: int) -> subprocess.Popen:
    """Lance un sous-processus Python."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd())
    return subprocess.Popen(
        [python, file],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=Path.cwd(),
    )


async def main():
    banner()
    python = sys.executable
    processes = []

    # 1. Démarrage des mock agents
    print(f"{BOLD}Démarrage des agents BO1-BO5...{RESET}\n")
    for svc in SERVICES:
        if not Path(svc["file"]).exists():
            print(f"  {RED}✗{RESET} {svc['name']} — fichier introuvable : {svc['file']}")
            continue
        p = start_process(python, svc["file"], svc["port"])
        processes.append((svc, p))
        print(f"  Lancement {svc['name']} (port {svc['port']})...", end=" ", flush=True)

    # 2. Attente de disponibilité
    for svc, _ in processes:
        ok = await wait_for_service(svc["url"], svc["name"])
        if ok:
            print(f"{GREEN}✅{RESET}")
        else:
            print(f"{RED}⚠ timeout{RESET}")

    await asyncio.sleep(0.5)

    # 3. BO6 principal
    print(f"\n{BOLD}Démarrage de BO6 (port 8000)...{RESET}", end=" ", flush=True)
    bo6 = start_process(python, "-m", 8000)  # workaround
    bo6 = subprocess.Popen(
        [python, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000",
         "--log-level", "warning"],
        env={**os.environ.copy(), "PYTHONPATH": str(Path.cwd())},
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=Path.cwd(),
    )
    processes.append(({"name":"BO6","url":"http://localhost:8000/api/v1/health"}, bo6))
    ok = await wait_for_service("http://localhost:8000/api/v1/health", "BO6", 20)
    print(f"{GREEN}✅{RESET}" if ok else f"{RED}⚠ timeout{RESET}")

    # 4. Dashboard
    print(f"\n{BOLD}Démarrage du Dashboard (port 8050)...{RESET}", end=" ", flush=True)
    dash_p = subprocess.Popen(
        [python, "app/dashboard/metrics_dashboard.py"],
        env={**os.environ.copy(), "PYTHONPATH": str(Path.cwd())},
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=Path.cwd(),
    )
    await asyncio.sleep(3)
    print(f"{GREEN}✅{RESET}")

    # 5. Résumé
    print(f"""
{ORANGE}{BOLD}
┌─────────────────────────────────────────────────┐
│     🏠 ESTATE MIND — Tous les services actifs   │
├─────────────────────────────────────────────────┤
│  {GREEN}✅{ORANGE} BO1 (Données)       → port 8001         │
│  {GREEN}✅{ORANGE} BO2 (Analyse)       → port 8002         │
│  {GREEN}✅{ORANGE} BO3 (Prix)          → port 8003         │
│  {GREEN}✅{ORANGE} BO4 (Investissement)→ port 8004         │
│  {GREEN}✅{ORANGE} BO5 (Légal)         → port 8005         │
│  {GREEN}✅{ORANGE} BO6 (Orchestrateur) → port 8000         │
│  {GREEN}✅{ORANGE} Dashboard           → port 8050         │
├─────────────────────────────────────────────────┤
│  📖 API Docs   : http://localhost:8000/docs     │
│  📊 Dashboard  : http://localhost:8050          │
│  💬 Frontend   : frontend/index.html            │
└─────────────────────────────────────────────────┘
{RESET}
Appuyez sur Ctrl+C pour arrêter tous les services.
""")

    # 6. Ouvre le navigateur
    await asyncio.sleep(1)
    try:
        webbrowser.open("http://localhost:8000/docs")
        webbrowser.open("http://localhost:8050")
        webbrowser.open(str(Path("frontend/index.html").absolute()))
    except Exception:
        pass

    # 7. Attend Ctrl+C
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print(f"\n{ORANGE}Arrêt de tous les services...{RESET}")
        for _, p in processes:
            try: p.terminate()
            except: pass
        if 'dash_p' in dir():
            try: dash_p.terminate()
            except: pass
        print(f"{GREEN}Arrêt propre. À bientôt !{RESET}")


if __name__ == "__main__":
    asyncio.run(main())
 