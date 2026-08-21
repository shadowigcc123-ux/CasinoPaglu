#!/usr/bin/env python3
"""
Casino Royals Mini App — FastAPI server
=======================================

Runs the Telegram Mini App (web casino) INSIDE Telegram and shares the same
SQLite economy as casino_bot.py, so balances, history and stats are identical
between the chat bot and the web app.

14 games: Dice Royale, Crash, Mines, Blackjack, Roulette, Hi-Lo, Plinko,
Keno, Wheel of Fortune, Limbo, Coin Flip, Slots, Towers, Baccarat.

Run:  uvicorn miniapp:app --host 0.0.0.0 --port 8000
Deploy alongside casino_bot.py (this file imports its engine + DB).
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import math
import os
import secrets
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from math import comb
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qsl

_here = Path(__file__).resolve().parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

try:
    import casino_bot as CB  # shared engine: DB, fair RNG, economy
except Exception as exc:  # pragma: no cover
    raise RuntimeError(
        "casino_bot.py must be in the same directory as miniapp.py "
        "(the Mini App shares the bot's wallet engine)."
    ) from exc

try:
    from fastapi import FastAPI, Request
    from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
    from fastapi.staticfiles import StaticFiles
except ImportError:  # pragma: no cover
    print("Installing fastapi + uvicorn...", flush=True)
    import subprocess

    subprocess.run([sys.executable, "-m", "pip", "install", "fastapi", "uvicorn"], check=True)
    from fastapi import FastAPI, Request
    from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
    from fastapi.staticfiles import StaticFiles

LOGGER = CB.LOGGER
db_call = CB.db_call
fmt_amount = CB.fmt_amount
quantize_money = CB.quantize_money
utc_now = CB.utc_now
GameError = CB.GameError
InsufficientBalance = CB.InsufficientBalance

BOT_TOKEN = CB.BOT_TOKEN
DEMO_MODE = not bool(BOT_TOKEN)
APP_NAME = os.getenv("MINIAPP_NAME", "Casino Royals")
CURRENCY = os.getenv("MINIAPP_CURRENCY", "Coins")
STATIC_DIR = _here / "static"

# <EMBED-INDEX-BEGIN>
EMBEDDED_INDEX_HTML = "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n<meta charset=\"UTF-8\">\n<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no\">\n<title>Casino Royals</title>\n<style>\n:root{\n  --bg:#0a3527; --bg2:#0d4130; --panel:#113a29; --panel2:#164a36; --field:#0e3526;\n  --gold:#d4af37; --gold2:#e8c766; --golddeep:#9c7c22;\n  --cream:#f2ecdc; --muted:#a5c0ae; --line:rgba(212,175,55,.28);\n  --serif:Georgia,'Times New Roman',serif;\n  --sans:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;\n  --r:12px;\n}\n*{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent}\nhtml,body{height:100%}\nbody{\n  font-family:var(--sans);\n  background:radial-gradient(1100px 720px at 50% -12%, #17573f 0%, #0d4130 46%, #08291d 100%) fixed;\n  color:var(--cream); overflow-x:hidden;\n}\nbody::before{content:\"\";position:fixed;inset:0;pointer-events:none;opacity:.05;\n  background:repeating-linear-gradient(45deg,transparent 0 26px,#d4af37 26px 27px),repeating-linear-gradient(-45deg,transparent 0 26px,#d4af37 26px 27px);}\n#app{position:relative;max-width:480px;margin:0 auto;padding:14px 14px 44px}\n\n/* ---------- header ---------- */\nheader{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:6px 2px 16px}\n.brand{display:flex;align-items:center;gap:12px}\n.brand svg{filter:drop-shadow(0 2px 6px rgba(0,0,0,.5))}\n.brand h1{font-family:var(--serif);font-size:23px;font-weight:700;letter-spacing:1.5px;\n  background:linear-gradient(180deg,#f5e3a4 0%,var(--gold) 55%,#b08d2b 100%);\n  -webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}\n.brand small{display:block;font-size:9.5px;color:var(--muted);font-weight:600;letter-spacing:3.2px;-webkit-text-fill-color:var(--muted)}\n.chip{border:1px solid var(--line);background:linear-gradient(180deg,rgba(232,199,102,.10),rgba(0,0,0,.22));border-radius:10px;\n  padding:8px 14px;text-align:right;box-shadow:0 4px 14px rgba(0,0,0,.35)}\n.chip span{display:block;font-size:8.5px;letter-spacing:2.2px;color:var(--muted);font-weight:700}\n.chip b{font-family:var(--serif);font-size:17px;color:var(--gold2);font-weight:700}\n\n/* ---------- banner ---------- */\n.banner{display:none;margin:0 0 12px;padding:11px 14px;border-radius:10px;font-size:12px;font-weight:600;line-height:1.5;border:1px solid}\n.banner.demo{display:block;border-color:rgba(212,175,55,.4);background:rgba(212,175,55,.08);color:var(--gold2)}\n.banner.err{display:block;border-color:rgba(200,80,60,.5);background:rgba(160,50,40,.14);color:#f0b9ab}\n\n/* ---------- tabs ---------- */\nnav.tabs{display:flex;gap:4px;border:1px solid var(--line);border-radius:11px;padding:4px;margin-bottom:18px;\n  background:linear-gradient(180deg,rgba(255,255,255,.04),rgba(0,0,0,.24))}\nnav.tabs button{flex:1;border:none;background:transparent;padding:10px 4px;border-radius:8px;\n  font-size:12px;font-weight:700;letter-spacing:.6px;color:var(--muted);cursor:pointer;transition:.2s}\nnav.tabs button.on{background:linear-gradient(180deg,var(--gold2),var(--gold));color:#15291f;box-shadow:0 3px 10px rgba(0,0,0,.4)}\n\n/* ---------- section titles ---------- */\n.sec-title{display:flex;align-items:center;gap:10px;font-family:var(--serif);font-size:15px;font-weight:700;\n  letter-spacing:1.2px;margin:4px 2px 12px;color:var(--gold2)}\n.sec-title .rule{flex:1;height:1px;background:linear-gradient(90deg,var(--line),transparent)}\n\n/* ---------- game grid ---------- */\n.grid{display:grid;grid-template-columns:1fr 1fr;gap:11px}\n.tile{position:relative;background:linear-gradient(180deg,rgba(255,255,255,.05),rgba(0,0,0,.22)),var(--panel);\n  border:1px solid var(--line);border-radius:var(--r);padding:16px 14px 14px;cursor:pointer;overflow:hidden;transition:.25s;\n  animation:tileIn .4s ease backwards}\n.tile:nth-child(1){animation-delay:.02s}.tile:nth-child(2){animation-delay:.05s}.tile:nth-child(3){animation-delay:.08s}\n.tile:nth-child(4){animation-delay:.11s}.tile:nth-child(5){animation-delay:.14s}.tile:nth-child(6){animation-delay:.17s}\n.tile:nth-child(7){animation-delay:.2s}.tile:nth-child(8){animation-delay:.23s}.tile:nth-child(9){animation-delay:.26s}\n.tile:nth-child(10){animation-delay:.29s}.tile:nth-child(11){animation-delay:.32s}.tile:nth-child(12){animation-delay:.35s}\n.tile:nth-child(13){animation-delay:.38s}.tile:nth-child(14){animation-delay:.41s}\n@keyframes tileIn{from{transform:translateY(14px);opacity:0}to{transform:none;opacity:1}}\n.tile:hover{transform:translateY(-2px);border-color:rgba(212,175,55,.6);box-shadow:0 8px 22px rgba(0,0,0,.45)}\n.tile .mono{width:44px;height:44px;border:1px solid rgba(212,175,55,.55);border-radius:50%;margin-bottom:10px;\n  display:flex;align-items:center;justify-content:center;font-family:var(--serif);font-size:15px;font-weight:700;color:var(--gold2);\n  background:radial-gradient(circle at 35% 30%,rgba(232,199,102,.18),rgba(0,0,0,.3));letter-spacing:.5px}\n.tile .nm{font-size:14px;font-weight:700;letter-spacing:.3px}\n.tile .tg{position:absolute;top:10px;right:11px;font-size:8.5px;font-weight:800;letter-spacing:1.8px;color:var(--gold);opacity:.85}\n\n/* ---------- game panel ---------- */\n.panel{background:linear-gradient(180deg,rgba(255,255,255,.05),rgba(0,0,0,.24)),var(--panel);\n  border:1px solid var(--line);border-radius:16px;padding:18px;box-shadow:0 14px 40px rgba(0,0,0,.5);animation:panelIn .3s ease}\n@keyframes panelIn{from{transform:translateY(18px);opacity:0}to{transform:none;opacity:1}}\n.panel-head{display:flex;align-items:center;gap:12px;margin-bottom:16px}\n.back-btn{width:38px;height:38px;border-radius:9px;border:1px solid var(--line);background:rgba(0,0,0,.2);color:var(--gold2);\n  font-size:16px;cursor:pointer;transition:.2s;font-family:var(--serif)}\n.back-btn:hover{border-color:rgba(212,175,55,.6)}\n.panel-head .mono{width:44px;height:44px;border:1px solid rgba(212,175,55,.55);border-radius:50%;display:flex;align-items:center;\n  justify-content:center;font-family:var(--serif);font-size:15px;font-weight:700;color:var(--gold2);\n  background:radial-gradient(circle at 35% 30%,rgba(232,199,102,.18),rgba(0,0,0,.3))}\n.panel-head h2{font-family:var(--serif);font-size:19px;font-weight:700;letter-spacing:1px;color:var(--cream)}\n.panel-head small{display:block;font-size:9px;color:var(--muted);font-weight:700;letter-spacing:2px;margin-top:2px}\n\n.bet-row{display:flex;align-items:center;margin-bottom:10px}\n.bet-row label{width:36px;font-size:10px;letter-spacing:1.6px;color:var(--muted);font-weight:700}\n.bet-input{flex:1}\n.bet-input input{width:100%;padding:12px 14px;border-radius:9px;border:1px solid rgba(212,175,55,.3);background:var(--field);\n  font-size:16px;font-weight:700;color:var(--gold2);outline:none;transition:.2s;font-family:var(--serif)}\n.bet-input input:focus{border-color:var(--gold);box-shadow:0 0 0 3px rgba(212,175,55,.14)}\n.chips{display:flex;gap:6px;margin-bottom:14px}\n.chips button{flex:1;padding:8px 0;border-radius:8px;border:1px solid var(--line);background:rgba(0,0,0,.18);\n  color:var(--cream);font-weight:700;font-size:11.5px;letter-spacing:.6px;cursor:pointer;transition:.18s}\n.chips button:active{background:var(--gold);color:#15291f;border-color:var(--gold)}\n\n.ctrl-row{display:flex;gap:7px;flex-wrap:wrap;margin-bottom:14px}\n.ctrl{flex:1;min-width:74px;padding:11px 8px;border-radius:8px;border:1px solid var(--line);background:rgba(0,0,0,.18);\n  font-weight:700;font-size:12.5px;letter-spacing:.4px;color:var(--muted);cursor:pointer;transition:.18s;text-align:center}\n.ctrl.on{border-color:var(--gold);color:var(--gold2);background:linear-gradient(180deg,rgba(232,199,102,.14),rgba(212,175,55,.05));\n  box-shadow:inset 0 0 18px rgba(212,175,55,.08)}\n.payout-hint{font-size:12px;color:var(--muted);text-align:center;margin:2px 0 12px;font-weight:600;letter-spacing:.3px}\n.payout-hint b{color:var(--gold2)}\n\n.primary{width:100%;padding:14px;border:1px solid #f0d98a;border-radius:9px;\n  background:linear-gradient(180deg,var(--gold2),var(--gold) 60%,#c09a2b);color:#18281f;\n  font-size:14.5px;font-weight:800;letter-spacing:1.4px;cursor:pointer;box-shadow:0 5px 16px rgba(0,0,0,.4);transition:.2s;\n  text-transform:uppercase}\n.primary:active{transform:scale(.98)}\n.primary:disabled{opacity:.5;cursor:not-allowed}\n.primary.alt{background:rgba(0,0,0,.22);color:var(--gold2);border:1px solid rgba(212,175,55,.5);box-shadow:none}\n.hint-msg{display:none;margin-top:12px;padding:10px 12px;border-radius:8px;font-size:12px;font-weight:600;line-height:1.5;\n  border:1px solid rgba(200,80,60,.5);background:rgba(160,50,40,.14);color:#f0b9ab}\n.hint-msg.show{display:block}\n\n/* result */\n.result{margin-top:14px;padding:16px;border-radius:10px;text-align:center;animation:pop .4s cubic-bezier(.2,1.3,.4,1)}\n@keyframes pop{from{transform:scale(.9);opacity:0}to{transform:none;opacity:1}}\n.result .lbl{font-size:9.5px;letter-spacing:2.6px;font-weight:800;color:var(--muted)}\n.result .big{font-family:var(--serif);font-size:30px;font-weight:700;margin:5px 0;letter-spacing:.5px}\n.result.win{border:1px solid rgba(212,175,55,.5);background:linear-gradient(180deg,rgba(232,199,102,.16),rgba(212,175,55,.04))}\n.result.win .big{color:var(--gold2)}\n.result.win .lbl{color:var(--gold)}\n.result.lose{border:1px solid var(--line);background:rgba(0,0,0,.2)}\n.result.lose .big{color:var(--muted)}\n.result .sub{font-size:12.5px;color:var(--muted);font-weight:600}\n.result .sub b{color:var(--cream)}\n.fair{margin-top:14px;font-size:10.5px;color:var(--muted);text-align:center;word-break:break-all;line-height:1.6}\n.fair code{background:rgba(212,175,55,.08);border:1px solid var(--line);padding:2px 7px;border-radius:5px;color:var(--gold2);font-weight:700}\n\n/* ---------- game-specific ---------- */\n.mines-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:7px;margin-bottom:14px}\n.mcell{aspect-ratio:1;border-radius:8px;border:1px solid rgba(212,175,55,.2);cursor:pointer;transition:.15s;\n  background:linear-gradient(180deg,#174a36,#0f3a2a);display:flex;align-items:center;justify-content:center}\n.mcell:active{transform:scale(.9)}\n.mcell.rev{border-color:rgba(212,175,55,.6);background:#164a36}\n.mcell .gem{width:46%;aspect-ratio:1;transform:rotate(45deg);border-radius:3px;\n  background:linear-gradient(135deg,#f7e7b3,#d4af37 55%,#9c7c22);box-shadow:0 0 12px rgba(212,175,55,.6)}\n.mcell .boom{width:52%;aspect-ratio:1;border-radius:50%;border:2px solid #3a3a3a;\n  background:radial-gradient(circle at 35% 30%,#5d5d5d,#141414 70%)}\n.mcell.dead{border-color:rgba(200,80,60,.7);background:linear-gradient(180deg,#4a241d,#2a1410)}\n.mcell.dead .boom{border-color:#7a2c22}\n.crash-stage{position:relative;height:214px;border-radius:10px;border:1px solid var(--line);overflow:hidden;margin-bottom:14px;\n  background:linear-gradient(180deg,rgba(0,0,0,.35),rgba(0,0,0,.12)),var(--field)}\n.crash-stage::before{content:\"\";position:absolute;inset:0;opacity:.16;\n  background:repeating-linear-gradient(0deg,transparent 0 33px,rgba(212,175,55,.5) 33px 34px),\n             repeating-linear-gradient(90deg,transparent 0 33px,rgba(212,175,55,.5) 33px 34px)}\n.crash-mult{position:absolute;top:14px;left:0;right:0;text-align:center;font-family:var(--serif);font-size:36px;font-weight:700;\n  color:var(--gold2);text-shadow:0 0 22px rgba(212,175,55,.4);z-index:2}\n.rocket-wrap{position:absolute;left:50%;bottom:16px;transform:translateX(-50%);transition:bottom .5s linear;z-index:1}\n.trail{position:absolute;left:50%;bottom:6px;width:3px;border-radius:3px;transform:translateX(-50%);\n  background:linear-gradient(180deg,transparent,rgba(212,175,55,.75))}\n.cardzone{display:flex;justify-content:center;gap:9px;flex-wrap:wrap;margin:8px 0 14px}\n.pcard{width:54px;height:76px;border-radius:8px;background:linear-gradient(160deg,#f8f4e8,#e9e2cc);border:1px solid #cbbf9d;\n  display:flex;align-items:center;justify-content:center;font-family:var(--serif);font-size:24px;font-weight:700;color:#22201a;\n  box-shadow:0 5px 14px rgba(0,0,0,.45);animation:deal .3s ease}\n@keyframes deal{from{transform:translateY(-14px) rotate(-5deg);opacity:0}to{transform:none;opacity:1}}\n.pcard.back{background:repeating-linear-gradient(45deg,#174a36 0 6px,#0f3a2a 6px 12px);border:1px solid rgba(212,175,55,.45)}\n.hand-label{font-size:9.5px;font-weight:800;letter-spacing:2.6px;color:var(--muted);text-align:center;margin:6px 0 3px}\n.keno-grid{display:grid;grid-template-columns:repeat(10,1fr);gap:4px;margin-bottom:14px}\n.kcell{aspect-ratio:1;border-radius:6px;border:1px solid rgba(212,175,55,.2);background:rgba(0,0,0,.22);\n  font-size:10.5px;font-weight:700;color:var(--muted);cursor:pointer;transition:.13s;display:flex;align-items:center;justify-content:center;font-family:var(--serif)}\n.kcell.sel{background:linear-gradient(180deg,var(--gold2),var(--gold));color:#15291f;border-color:#f0d98a}\n.kcell.hit{border-color:rgba(212,175,55,.7);color:var(--gold2)}\n.kcell.both{background:linear-gradient(180deg,var(--gold2),var(--gold));color:#15291f}\n.wheel-wrap{position:relative;width:212px;height:212px;margin:4px auto 16px}\n.wheel-pointer{position:absolute;top:-9px;left:50%;transform:translateX(-50%);z-index:3;width:0;height:0;\n  border-left:9px solid transparent;border-right:9px solid transparent;border-top:14px solid var(--gold);filter:drop-shadow(0 2px 3px rgba(0,0,0,.5))}\n.wheel-svg{width:100%;height:100%;transition:transform 4.2s cubic-bezier(.15,.9,.25,1);filter:drop-shadow(0 8px 18px rgba(0,0,0,.5))}\n.plinko-board{position:relative;height:224px;border-radius:10px;border:1px solid var(--line);overflow:hidden;margin-bottom:14px;\n  background:linear-gradient(180deg,rgba(0,0,0,.3),rgba(0,0,0,.08)),var(--field)}\n.pball{position:absolute;top:-12px;left:48%;width:13px;height:13px;border-radius:50%;\n  background:radial-gradient(circle at 35% 30%,#f7e7b3,var(--gold) 60%,#9c7c22);box-shadow:0 0 12px rgba(212,175,55,.9);\n  transition:top .95s cubic-bezier(.35,.45,.5,1),left .95s cubic-bezier(.35,.45,.5,1)}\n.pbucket{position:absolute;bottom:0;height:32px;display:flex;align-items:center;justify-content:center;\n  font-size:9.5px;font-weight:800;color:var(--muted);border-top:1px solid var(--line);background:rgba(0,0,0,.25);letter-spacing:.5px}\n.pbucket.hit{background:linear-gradient(180deg,rgba(232,199,102,.35),rgba(212,175,55,.15));color:var(--gold2);border-top-color:var(--gold)}\n.slots-row{display:flex;justify-content:center;gap:10px;margin-bottom:14px}\n.sreel{width:76px;height:88px;border-radius:9px;border:1px solid rgba(212,175,55,.45);background:var(--field);overflow:hidden;position:relative;\n  box-shadow:inset 0 0 20px rgba(0,0,0,.6)}\n.sreel .strip{position:absolute;left:0;right:0;display:flex;flex-direction:column;align-items:center;transition:transform .6s cubic-bezier(.2,.8,.3,1)}\n.sreel .strip span{height:88px;display:flex;align-items:center;justify-content:center;font-family:var(--serif);font-size:38px;font-weight:700;color:var(--gold2);text-shadow:0 0 14px rgba(212,175,55,.35)}\n.sreel.spinning .strip{animation:sroll .35s linear infinite}\n@keyframes sroll{from{transform:translateY(0)}to{transform:translateY(-352px)}}\n.roul-wheel{width:196px;height:196px;border-radius:50%;margin:6px auto 16px;position:relative;\n  box-shadow:0 0 0 6px #102f21,0 0 0 8px rgba(212,175,55,.6),0 10px 26px rgba(0,0,0,.55)}\n.roul-wheel:before{content:\"\";position:absolute;inset:0;border-radius:50%;\n  background:conic-gradient(#b33a2e 0 18deg,#17181a 18deg 36deg,#b33a2e 36deg 54deg,#17181a 54deg 72deg,\n  #b33a2e 72deg 90deg,#17181a 90deg 108deg,#b33a2e 108deg 126deg,#17181a 126deg 144deg,\n  #b33a2e 144deg 162deg,#17181a 162deg 180deg,#b33a2e 180deg 198deg,#17181a 198deg 216deg,\n  #b33a2e 216deg 234deg,#17181a 234deg 252deg,#b33a2e 252deg 270deg,#17181a 270deg 288deg,\n  #b33a2e 288deg 306deg,#17181a 306deg 324deg,#2f6b46 324deg 342deg,#17181a 342deg 360deg)}\n.roul-wheel .ball{position:absolute;inset:0;transition:transform 4s cubic-bezier(.12,.8,.25,1);z-index:2}\n.roul-wheel .ball:before{content:\"\";position:absolute;top:6px;left:50%;transform:translateX(-50%);width:13px;height:13px;\n  border-radius:50%;background:radial-gradient(circle at 35% 30%,#fff,#e8c766 45%,#9c7c22);box-shadow:0 0 10px rgba(232,199,102,.9)}\n.roul-wheel .hub{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;z-index:3}\n.roul-wheel .hub span{width:52px;height:52px;border-radius:50%;border:1px solid rgba(212,175,55,.6);\n  background:radial-gradient(circle at 35% 30%,#f5e3a4,#c9a227 60%,#8a6d1f);display:flex;align-items:center;justify-content:center;\n  font-family:var(--serif);font-weight:700;font-size:13px;color:#4a3c10;letter-spacing:1px}\n.num-pad{display:grid;grid-template-columns:repeat(6,1fr);gap:5px;margin-bottom:12px}\n.num-pad button{padding:9px 0;border-radius:6px;border:1px solid var(--line);background:rgba(0,0,0,.2);font-family:var(--serif);\n  font-size:12px;font-weight:700;color:var(--muted);cursor:pointer;transition:.15s}\n.num-pad button.on{background:linear-gradient(180deg,var(--gold2),var(--gold));color:#15291f;border-color:#f0d98a}\n.coin-stage{display:flex;justify-content:center;margin:10px 0 16px}\n.coin{width:96px;height:96px;border-radius:50%;border:2px solid #f0d98a;display:flex;align-items:center;justify-content:center;\n  font-family:var(--serif);font-weight:700;font-size:21px;letter-spacing:1px;color:#5c4a12;\n  background:radial-gradient(circle at 35% 30%,#f7e7b3,#d4af37 55%,#8a6d1f);box-shadow:0 10px 26px rgba(0,0,0,.5)}\n.coin.flip{animation:coinFlip 1.4s ease-in-out}\n@keyframes coinFlip{0%{transform:rotateY(0)}50%{transform:rotateY(900deg)}100%{transform:rotateY(1800deg)}}\n.limbo-target{display:flex;gap:8px;align-items:center;margin-bottom:12px}\n.limbo-target label{font-size:10px;letter-spacing:1.6px;color:var(--muted);font-weight:700}\n.limbo-target input{flex:1;padding:12px 14px;border-radius:9px;border:1px solid rgba(212,175,55,.3);background:var(--field);\n  font-family:var(--serif);font-size:16px;font-weight:700;color:var(--gold2);outline:none}\n.limbo-target .val{min-width:56px;text-align:center;font-family:var(--serif);font-weight:700;color:var(--gold2);\n  border:1px solid var(--line);background:rgba(0,0,0,.2);border-radius:9px;padding:12px 0;font-size:15px}\n.keno-status{font-size:11px;color:var(--muted);font-weight:700;letter-spacing:.6px;text-align:center;margin-bottom:9px}\n.range-row{display:flex;align-items:center;gap:10px;margin-bottom:12px}\n.range-row input[type=range]{flex:1;accent-color:var(--gold)}\n.range-row .val{min-width:52px;text-align:center;font-family:var(--serif);font-weight:700;color:var(--gold2);\n  border:1px solid var(--line);background:rgba(0,0,0,.2);border-radius:8px;padding:8px 0;font-size:14px}\n\n/* ---------- lists ---------- */\n.list{display:flex;flex-direction:column;gap:9px}\n.row{display:flex;align-items:center;gap:12px;background:linear-gradient(180deg,rgba(255,255,255,.04),rgba(0,0,0,.22)),var(--panel);\n  border:1px solid var(--line);border-radius:11px;padding:12px 14px}\n.row .mono{width:36px;height:36px;border:1px solid rgba(212,175,55,.5);border-radius:50%;display:flex;align-items:center;\n  justify-content:center;font-family:var(--serif);font-size:12px;font-weight:700;color:var(--gold2);\n  background:radial-gradient(circle at 35% 30%,rgba(232,199,102,.16),rgba(0,0,0,.3));flex-shrink:0}\n.row .grow{flex:1;min-width:0}\n.row .t1{font-weight:700;font-size:13px;letter-spacing:.2px}\n.row .t2{font-size:10.5px;color:var(--muted);font-weight:600;margin-top:2px}\n.row .amt{font-family:var(--serif);font-weight:700;font-size:14px}\n.row .amt.pos{color:var(--gold2)}.row .amt.neg{color:var(--muted)}.row .amt.neu{color:var(--muted)}\n.rank{width:28px;height:28px;border-radius:7px;display:flex;align-items:center;justify-content:center;\n  font-family:var(--serif);font-weight:700;font-size:13px;border:1px solid var(--line);color:var(--muted);flex-shrink:0}\n.rank.gold{background:linear-gradient(180deg,var(--gold2),var(--gold));color:#15291f;border-color:#f0d98a}\n.empty{padding:36px 10px;text-align:center;color:var(--muted);font-weight:600;font-size:12.5px;line-height:1.6}\n.fair-card{background:linear-gradient(180deg,rgba(255,255,255,.04),rgba(0,0,0,.22)),var(--panel);\n  border:1px solid var(--line);border-radius:var(--r);padding:17px;margin-bottom:12px}\n.fair-card h3{font-family:var(--serif);font-size:15px;font-weight:700;letter-spacing:.8px;color:var(--gold2);margin-bottom:8px}\n.fair-card p{font-size:12.5px;color:var(--muted);line-height:1.65}\n.fair-card code{background:rgba(212,175,55,.08);border:1px solid var(--line);padding:1px 6px;border-radius:4px;color:var(--gold2)}\n.wallet-actions{display:flex;gap:10px;margin-bottom:16px}\n.wallet-actions a,.wallet-actions button{flex:1;text-decoration:none;text-align:center;padding:13px;border-radius:9px;\n  font-weight:800;font-size:12.5px;letter-spacing:1.2px;border:none;cursor:pointer;text-transform:uppercase}\n.wa-dep{background:linear-gradient(180deg,var(--gold2),var(--gold));color:#18281f;border:1px solid #f0d98a}\n.wa-wd{background:rgba(0,0,0,.22);color:var(--gold2);border:1px solid rgba(212,175,55,.5)!important}\n.stats-row{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:16px}\n.stat{background:linear-gradient(180deg,rgba(255,255,255,.04),rgba(0,0,0,.22)),var(--panel);\n  border:1px solid var(--line);border-radius:11px;padding:14px;text-align:center}\n.stat b{display:block;font-family:var(--serif);font-size:19px;color:var(--gold2);margin-bottom:4px;font-weight:700}\n.stat span{font-size:9px;color:var(--muted);font-weight:800;letter-spacing:1.8px}\n.view{display:none}\n.view.on{display:block}\n</style>\n</head>\n<body>\n<div id=\"app\">\n  <header>\n    <div class=\"brand\">\n      <svg viewBox=\"0 0 24 24\" width=\"30\" height=\"30\" fill=\"#d4af37\" aria-hidden=\"true\">\n        <path d=\"M2.5 7.5L6 11l6-7 6 7 3.5-3.5L20 20H4L2.5 7.5z\"/><rect x=\"3.4\" y=\"16.4\" width=\"17.2\" height=\"2.4\" rx=\"1.2\" fill=\"#e8c766\"/>\n      </svg>\n      <div>\n        <h1>CASINO ROYALS</h1>\n        <small>TABLE GAMES</small>\n      </div>\n    </div>\n    <div class=\"chip\"><span>BALANCE</span><b id=\"bal\">0</b></div>\n  </header>\n\n  <div class=\"banner demo\" id=\"bannerDemo\">Preview mode - offline demo balance. Inside Telegram your balance is shared with the bot wallet.</div>\n  <div class=\"banner err\" id=\"bannerErr\" style=\"display:none\"></div>\n\n  <nav class=\"tabs\" id=\"tabs\">\n    <button data-view=\"games\" class=\"on\">Games</button>\n    <button data-view=\"wallet\">Wallet</button>\n    <button data-view=\"board\">Leaderboard</button>\n    <button data-view=\"fair\">Fairness</button>\n  </nav>\n\n  <div class=\"view on\" id=\"view-games\">\n    <div class=\"sec-title\">Table Games<span class=\"rule\"></span></div>\n    <div class=\"grid\" id=\"grid\"></div>\n  </div>\n\n  <div class=\"view\" id=\"view-game\"><div class=\"panel\" id=\"panel\"></div></div>\n\n  <div class=\"view\" id=\"view-wallet\">\n    <div class=\"sec-title\">Wallet<span class=\"rule\"></span></div>\n    <div class=\"wallet-actions\">\n      <a class=\"wa-dep\" id=\"depBtn\" href=\"#\" onclick=\"return walletGo('deposit')\">Deposit</a>\n      <button class=\"wa-wd\" id=\"wdBtn\" onclick=\"walletGo('withdraw')\">Withdraw</button>\n    </div>\n    <div class=\"stats-row\">\n      <div class=\"stat\"><b id=\"stGames\">0</b><span>GAMES</span></div>\n      <div class=\"stat\"><b id=\"stWins\">0</b><span>W / L</span></div>\n      <div class=\"stat\"><b id=\"stWagered\">0</b><span>WAGERED</span></div>\n      <div class=\"stat\"><b id=\"stPaid\">0</b><span>PAID OUT</span></div>\n    </div>\n    <div class=\"sec-title\">Recent Rounds<span class=\"rule\"></span></div>\n    <div class=\"list\" id=\"history\"></div>\n  </div>\n\n  <div class=\"view\" id=\"view-board\">\n    <div class=\"sec-title\">Leaderboard<span class=\"rule\"></span></div>\n    <div class=\"list\" id=\"board\"></div>\n  </div>\n\n  <div class=\"view\" id=\"view-fair\">\n    <div class=\"sec-title\">Provably Fair<span class=\"rule\"></span></div>\n    <div class=\"fair-card\">\n      <h3>Verifiable results</h3>\n      <p>Before each round the server commits to a random seed and reveals its SHA-256 hash. Every outcome is derived from <code>hash(seed + nonce + salt)</code>, so a result can never be changed after you have played - not even by the house. Table games carry a 3% house edge (return to player of 97%).</p>\n    </div>\n    <div class=\"fair-card\">\n      <h3>House rules</h3>\n      <p>Minimum and maximum bets are set by the operator. Balances are shared with the Casino Royals Telegram bot - one wallet, everywhere. Payouts credit instantly; deposits and withdrawals are handled through the bot. Play only with funds you can afford to lose.</p>\n    </div>\n  </div>\n</div>\n\n<script>\n/* ============================== CORE STATE ============================== */\nconst S = {\n  demo:true, user:null, balance:0, cfg:null, game:null, session:null,\n  history:[], board:[], stats:{games:0,wins:0,losses:0,wagered:0,paid:0},\n  busy:false, bet:0\n};\nconst $=id=>document.getElementById(id);\nconst em=html=>html.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));\nconst fmt=n=>{n=Math.round(n*100)/100;let s=n.toFixed(2).replace(/\\.?0+$/,'');return s||'0'};\n\nfunction initData(){\n  if(window.Telegram&&Telegram.WebApp&&Telegram.WebApp.initData) return Telegram.WebApp.initData;\n  return 'user=%7B%22id%22%3A777000%2C%22first_name%22%3A%22Preview%20Player%22%7D';\n}\n\nasync function api(path,body){\n  try{\n    const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},\n      body:JSON.stringify(Object.assign({initData:initData()},body||{}))});\n    const j=await r.json();\n    if(!r.ok&&r.status!==401){return {ok:false,error:j.error||'Request failed',code:j.code};}\n    return j;\n  }catch(e){ return {offline:true}; }\n}\n\nfunction notify(msg){\n  const el=$('panelMsg');\n  if(!el)return;\n  el.textContent=msg; el.classList.add('show');\n  setTimeout(()=>el.classList.remove('show'),3500);\n}\n\n/* ============================== DEMO ENGINE ============================== */\n/* Local mirror of the server games so the preview stays playable offline. */\nconst DEMO={\n  deck(){let d=[];for(let i=0;i<52;i++){let v=(i%13)+2;d.push(v>14?14:v);}for(let i=d.length-1;i>0;i--){let j=Math.floor(Math.random()*(i+1));[d[i],d[j]]=[d[j],d[i]];}return d;},\n  bjVal(h){let t=0,a=0;h.forEach(c=>{if(c===14){a++;t+=1}else t+=Math.min(c,10);});return a>0&&t+10<=21?t+10:t;}\n};\nfunction demoFair(){return {seed_hash:[...Array(24)].map(()=>Math.floor(Math.random()*16).toString(16)).join(''),nonce:'0'};}\nfunction demoResult(game,action,data){\n  data=data||{};\n  const bet=parseFloat(data.bet)||0;\n  const rnd=()=>Math.random();\n  const fair=demoFair();\n  let won,payout=0,extra={};\n  switch(game){\n    case 'dice':{\n      const dir=data.direction==='under'?'under':'over', t=parseInt(data.target)||50;\n      const roll=1+Math.floor(rnd()*100);\n      won=dir==='over'?roll>t:roll<t;\n      const wins=dir==='over'?(100-t):(t-1);\n      const mult=wins>0?0.97*100/wins:0;\n      payout=won?bet*mult:0;\n      extra={roll,target:t,direction:dir,multiplier:mult};break;}\n    case 'crash':{\n      if(action==='play'){\n        const r=rnd(); const cp=r>=0.97?1:Math.max(1.01,Math.round((0.97/r)*100)/100);\n        S.session={game:'crash',bet,cp,started:Date.now()};\n        return {ok:true,session_id:1,crash_point:cp,bet,fair};}\n      const mult=Math.min(parseFloat(data.multiplier)||1,S.session.cp-0.01);\n      payout=bet*mult; won=true; extra={multiplier:mult,crash_point:S.session.cp};break;}\n    case 'mines':{\n      const mines=[3,5,10].includes(parseInt(data.mines))?parseInt(data.mines):3;\n      if(action==='new'){\n        let bombs=new Set(); while(bombs.size<mines) bombs.add(Math.floor(rnd()*25));\n        S.session={game:'mines',bet,mines,bombs:[...bombs],revealed:[]};\n        return {ok:true,session_id:1,grid:[...Array(25)].map((_,i)=>({i,revealed:false})),fair};}\n      const s=S.session;\n      if(action==='cashout'){\n        const m=minesMult(s.mines,s.revealed.length); payout=bet*m; won=true;\n        extra={multiplier:m,revealed:[...s.revealed]};break;}\n      const cell=parseInt(data.cell);\n      if(s.revealed.includes(cell)) return {ok:false,error:'Already revealed.'};\n      s.revealed.push(cell);\n      if(s.bombs.includes(cell)){won=false;payout=0;extra={bomb_at:cell,revealed:[...s.revealed]};break;}\n      if(s.revealed.length>=25-s.mines){const m=minesMult(s.mines,s.revealed.length);payout=bet*m;won=true;extra={cleared:true,multiplier:m,revealed:[...s.revealed]};break;}\n      return {ok:true,won:null,cell,revealed:[...s.revealed],multiplier:minesMult(s.mines,s.revealed.length),potential_payout:bet*minesMult(s.mines,s.revealed.length),bet,fair};}\n    case 'towers':{\n      const diff=data.difficulty||'easy'; const bad={easy:1,medium:2,hard:3}[diff];\n      if(action==='new'){S.session={game:'towers',bet,bad,row:0,layout:[...Array(8)].map(()=>{let b=new Set();while(b.size<bad)b.add(Math.floor(rnd()*3));return[...b];});return {ok:true,session_id:1,difficulty:diff,fair};}\n      const s=S.session;\n      if(action==='cashout'){const m=towMult(s.row,bad);payout=bet*m;won=true;extra={multiplier:m,row:s.row};break;}\n      const col=parseInt(data.col);\n      if(s.layout[s.row].includes(col)){won=false;payout=0;extra={row:s.row,col};break;}\n      s.row++;\n      const m=towMult(s.row,bad);\n      if(s.row>=8){payout=bet*m;won=true;extra={cleared:true,multiplier:m};break;}\n      return {ok:true,won:null,row:s.row,col,multiplier:m,potential_payout:bet*m,bet,fair};}\n    case 'blackjack':{\n      if(action==='new'){\n        let d=DEMO.deck(),p=[d.pop(),d.pop()],dl=[d.pop(),d.pop()];\n        S.session={game:'blackjack',bet,deck:d,player:p,dealer:dl,doubled:false};\n        return {ok:true,session_id:1,player:p.map(cl),dealer:[cl(dl[0]),'?'],player_value:DEMO.bjVal(p),fair};}\n      const s=S.session;\n      if(action==='hit'){s.player.push(s.deck.pop());\n        if(DEMO.bjVal(s.player)>21) return bjDemoSettle(s);\n        return {ok:true,player:s.player.map(cl),player_value:DEMO.bjVal(s.player),dealer:[cl(s.dealer[0]),'?'],fair};}\n      if(action==='double'){s.bet=bet*2;s.player.push(s.deck.pop());return bjDemoSettle(s);}\n      return bjDemoSettle(s);}\n    case 'baccarat':{\n      const side=data.side||'player';\n      const winner=['player','banker','tie'][Math.floor(rnd()*3)];\n      won=winner===side; const mult={player:2,banker:1.95,tie:9}[side];\n      payout=won?bet*mult:0;\n      extra={winner,player_cards:['A','7'],banker_cards:['K','8'],player_value:8,banker_value:8,side};break;}\n    case 'roulette':{\n      const spin=Math.floor(rnd()*37);\n      let choice=data.choice||'red';\n      const color=spin===0?'green':([1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36].includes(spin)?'red':'black');\n      let mult=0;\n      if(choice==='red'||choice==='black')mult=color===choice?2:0;\n      else if(choice==='green')mult=spin===0?14:0;\n      else if(choice==='even'||choice==='odd')mult=spin!==0&&(spin%2===0)===(choice==='even')?2:0;\n      else if(choice==='low')mult=spin>=1&&spin<=18?2:0;\n      else if(choice==='high')mult=spin>=19?2:0;\n      else if(/^\\d+$/.test(choice)){mult=spin===parseInt(choice)?36:0;}\n      won=mult>0; payout=won?bet*mult:0;\n      extra={spin,color,choice};break;}\n    case 'hilo':{\n      if(action==='new'){let d=DEMO.deck(),cur=d.pop();\n        S.session={game:'hilo',bet,deck:d,current:cur,mult:1,step:0};\n        return {ok:true,session_id:1,card:cl(cur),higher_mult:1.2,lower_mult:1.2,cards_left:d.length,fair};}\n      const s=S.session;\n      if(action==='cashout'){payout=bet*s.mult;won=true;extra={multiplier:s.mult,steps:s.step};break;}\n      const card=s.deck.pop();\n      const ok=(action==='higher'&&card>s.current)||(action==='lower'&&card<s.current);\n      if(!ok){won=false;payout=0;extra={drawn:cl(card),had:cl(s.current),tie:card===s.current};break;}\n      s.current=card;s.step++;s.mult*=1.05;\n      if(s.deck.length===0){payout=bet*s.mult;won=true;extra={deck_cleared:true,multiplier:s.mult};break;}\n      return {ok:true,won:null,card:cl(card),higher_mult:1.2,lower_mult:1.2,multiplier:s.mult,potential_payout:bet*s.mult,cards_left:s.deck.length,fair};}\n    case 'plinko':{\n      const risk=data.risk||'low';\n      const tabs={low:[5.4,2,1.1,0.95,0.48,0.95,1.1,2,5.4],medium:[12,3.1,1.3,0.65,0.3,0.65,1.3,3.1,12],high:[20,4.5,1.6,0.35,0.18,0.35,1.6,4.5,20]}[risk];\n      const bucket=Math.floor(rnd()*9); const mult=tabs[bucket];\n      payout=bet*mult; won=payout>0; extra={bucket,risk,multiplier:mult};break;}\n    case 'keno':{\n      const picks=(data.picks||[]).slice().sort((a,b)=>a-b);\n      let drawn=new Set(); while(drawn.size<10)drawn.add(1+Math.floor(rnd()*80));\n      const hits=picks.filter(p=>drawn.has(p));\n      const mult=hits.length>=2?Math.min(1000,0.97/(picks.length-1)*comb(80,10)/(comb(picks.length,hits.length)*comb(80-picks.length,10-hits.length))):0;\n      payout=bet*mult; won=payout>0;\n      extra={picks,drawn:[...drawn].sort((a,b)=>a-b),hits,multiplier:mult};break;}\n    case 'wheel':{\n      const segs=[0,0.9,1.3,1.7,2.6,4.3,8.5], weights=[30,42,14,7,4,2,1];\n      let r=rnd()*100,idx=0,acc=0;\n      for(let i=0;i<weights.length;i++){acc+=weights[i];if(r<acc){idx=i;break;}}\n      const mult=segs[idx]; payout=bet*mult; won=payout>0; extra={segment:idx,multiplier:mult};break;}\n    case 'limbo':{\n      const t=Math.max(1.01,Math.min(100000,parseFloat(data.target)||2));\n      const p=(1e8-t*1e6)/1e8, mult=0.97/p;\n      const roll=rnd(); won=roll>=p; payout=won?bet*mult:0;\n      extra={target:t,multiplier:mult};break;}\n    case 'coinflip':{\n      const side=data.side||'heads'; const landed=rnd()<0.5?'heads':'tails';\n      won=landed===side; payout=won?bet*1.94:0; extra={landed,side};break;}\n    case 'slots':{\n      const sym=['C','R','7','A','K','Q','J'];\n      const reel=[0,1,2].map(()=>sym[Math.floor(rnd()*sym.length)]);\n      const mult=reel.every(x=>x===reel[0])?{C:2,R:3,7:4,A:5,K:10,Q:20,J:50}[reel[0]]:0;\n      payout=bet*mult; won=payout>0; extra={reel,multiplier:mult};break;}\n  }\n  S.balance+=payout;\n  S.session=null;\n  return {ok:true,won:won!==null?won:undefined,payout,bet,...extra,fair};\n}\nfunction bjDemoSettle(s){\n  let dl=s.dealer;\n  while(DEMO.bjVal(dl)<17&&s.deck.length)dl.push(s.deck.pop());\n  const pv=DEMO.bjVal(s.player), dv=DEMO.bjVal(dl);\n  let payout=0, won=false, push=false;\n  const bet=s.bet;\n  const natural=s.player.length===2&&pv===21;\n  if(pv<=21&&(dv>21||pv>dv)){payout=bet*(natural?2.5:2);won=true;}\n  else if(pv<=21&&pv===dv){payout=bet;push=true;won=true;}\n  S.balance+=payout; S.session=null;\n  return {ok:true,won,push,payout,bet,player_cards:s.player.map(cl),dealer_cards:dl.map(cl),player_value:pv,dealer_value:dv,natural,fair:demoFair()};\n}\nfunction minesMult(mines,rev){if(!rev)return 1;return Math.round(0.97*comb(25,rev)/comb(25-mines,rev)*100)/100;}\nfunction towMult(row,bad){return Math.round(0.97*Math.pow(3/(3-bad),row)*100)/100;}\nfunction comb(n,k){let r=1;for(let i=0;i<k;i++)r=r*(n-i)/(i+1);return Math.round(r);}\nfunction cl(c){return c===14?'A':c===13?'K':c===12?'Q':c===11?'J':c===1?'A':String(c);}\n\n/* ============================== BOOTSTRAP ============================== */\nasync function boot(){\n  const cfg=await api('/api/config');\n  if(!cfg.offline){ S.cfg=cfg; S.demo=!!cfg.demoMode; $('bannerDemo').style.display=S.demo?'block':'none'; }\n  else { S.cfg={appName:'Casino Royals',currency:'Coins',minBet:1,maxBet:100,games:GAMES_META,botUsername:null}; S.demo=true; }\n  if(S.demo){ S.balance=1000; renderGrid(); renderStats(); }\n  else{\n    const init=await api('/api/init');\n    if(init.ok&&init.user){ S.user=init.user; S.balance=init.balance; S.history=init.history||[]; S.board=init.leaderboard||[];\n      S.stats=init.stats||S.stats; }\n    renderGrid(); renderStats();\n  }\n  $('bal').textContent=fmt(S.balance);\n  $('depBtn').href='https://t.me/'+(S.cfg.botUsername||'');\n}\n\n/* ============================== VIEWS ============================== */\ndocument.querySelectorAll('#tabs button').forEach(b=>b.onclick=()=>{\n  document.querySelectorAll('#tabs button').forEach(x=>x.classList.remove('on'));\n  b.classList.add('on');\n  document.querySelectorAll('.view').forEach(v=>v.classList.remove('on'));\n  $('view-'+b.dataset.view).classList.add('on');\n  if(b.dataset.view==='wallet') renderWallet();\n  if(b.dataset.view==='board') renderBoard();\n});\n\nfunction renderGrid(){\n  const games=S.cfg.games||GAMES_META;\n  $('grid').innerHTML=games.map(g=>`\n    <div class=\"tile\" onclick=\"openGame('${g.id}')\">\n      <span class=\"tg\">${g.tag.toUpperCase()}</span>\n      <div class=\"mono\">${g.mono}</div>\n      <div class=\"nm\">${g.name}</div>\n    </div>`).join('');\n}\n\nfunction openGame(id){\n  S.game=id; S.session=null;\n  const g=(S.cfg.games||GAMES_META).find(x=>x.id===id);\n  document.querySelectorAll('.view').forEach(v=>v.classList.remove('on'));\n  $('view-game').classList.add('on');\n  renderPanel(g);\n}\nfunction backGames(){\n  document.querySelectorAll('.view').forEach(v=>v.classList.remove('on'));\n  $('view-games').classList.add('on');\n}\n\n/* ============================== PANEL RENDERERS ============================== */\nfunction panelShell(g,inner,betCtrl=true){\n  const min=S.cfg.minBet||1, max=S.cfg.maxBet||100;\n  return `\n  <div class=\"panel-head\">\n    <button class=\"back-btn\" onclick=\"backGames()\">&larr;</button>\n    <div class=\"mono\">${g.mono}</div>\n    <div><h2>${g.name}</h2><small>PROVABLY FAIR</small></div>\n  </div>\n  ${betCtrl?`\n  <div class=\"bet-row\"><label>BET</label><div class=\"bet-input\">\n    <input type=\"number\" id=\"betIn\" min=\"${min}\" max=\"${max}\" step=\"1\" value=\"${Math.max(min,Math.min(max,S.bet||min))}\"></div></div>\n  <div class=\"chips\">\n    <button onclick=\"setBet('min')\">MIN</button>\n    <button onclick=\"setBet('x2')\">2x</button>\n    <button onclick=\"setBet('x5')\">5x</button>\n    <button onclick=\"setBet('max')\">MAX</button>\n  </div>`:''}\n  ${inner}\n  <div class=\"hint-msg\" id=\"panelMsg\"></div>\n  <div id=\"resultBox\"></div>\n  <div class=\"fair\" id=\"fairBox\"></div>`;\n}\nfunction setBet(kind){\n  const min=S.cfg.minBet||1, max=S.cfg.maxBet||100;\n  const cur=parseFloat($('betIn').value)||min;\n  $('betIn').value=fmt(kind==='min'?min:kind==='x2'?Math.min(max,cur*2):kind==='x5'?Math.min(max,cur*5):max);\n}\nfunction getBet(){ const v=parseFloat($('betIn')&&$('betIn').value); return isNaN(v)?0:v; }\n\nfunction renderPanel(g){\n  const m={dice:pnlDice,crash:pnlCrash,mines:pnlMines,towers:pnlTowers,blackjack:pnlBJ,baccarat:pnlBaccarat,\n    roulette:pnlRoulette,hilo:pnlHilo,plinko:pnlPlinko,keno:pnlKeno,wheel:pnlWheel,limbo:pnlLimbo,\n    coinflip:pnlCoin,slots:pnlSlots};\n  $('panel').innerHTML=panelShell(g,(m[g.id]||pnlDice)());\n  $('betIn')&&($('betIn').oninput=()=>{S.bet=parseFloat($('betIn').value)||0;});\n}\n\nfunction showResult(res){\n  const box=$('resultBox');\n  if(!box)return;\n  if(res&&res.ok===false){box.innerHTML=`<div class=\"result lose\"><div class=\"lbl\">ERROR</div><div class=\"sub\">${em(res.error||'Request failed')}</div></div>`;return;}\n  if(res&&res.won===null){return;}\n  if(res&&res.payout!==undefined){\n    S.balance=res.balance!==undefined?res.balance:S.balance;\n    const win=res.won&&res.payout>0;\n    const push=res.push;\n    box.innerHTML=`<div class=\"result ${win?'win':'lose'}\">\n      <div class=\"lbl\">${push?'PUSH':win?'YOU WIN':'ROUND LOST'}</div>\n      <div class=\"big\">${push?'RETURNED':(win?'+'+fmt(res.payout):'-'+fmt((res.bet||0)-(res.payout||0)||0))}</div>\n      <div class=\"sub\">Balance: <b>${fmt(S.balance)}</b></div></div>`;\n    $('bal').textContent=fmt(S.balance);\n  }\n  if(res&&res.fair){\n    $('fairBox').innerHTML=`Seed <code>${res.fair.seed_hash}...</code> Nonce <code>${res.fair.nonce}</code>`;\n  }\n}\nasync function doPlay(game,action,data){\n  if(S.busy)return; S.busy=true;\n  let res;\n  if(S.demo){ res=demoResult(game,action,data); if(res.offline)res={ok:false,error:'Offline'}; }\n  else res=await api('/api/play',{game,action,data});\n  S.busy=false;\n  if(res&&res.balance!==undefined){S.balance=res.balance;}\n  if(res&&res.ok&&res.result)res=Object.assign({balance:res.balance},res.result);\n  $('bal').textContent=fmt(S.balance);\n  return res;\n}\n\n/* ---------- DICE ---------- */\nlet diceDir='over',diceTarget=50;\nfunction pnlDice(){\n  return `\n  <div class=\"ctrl-row\">\n    <button class=\"ctrl on\" id=\"dOver\" onclick=\"diceDir='over';$('dOver').classList.add('on');$('dUnder').classList.remove('on');updDice()\">Over</button>\n    <button class=\"ctrl\" id=\"dUnder\" onclick=\"diceDir='under';$('dUnder').classList.add('on');$('dOver').classList.remove('on');updDice()\">Under</button>\n  </div>\n  <div class=\"range-row\"><input type=\"range\" id=\"dTarget\" min=\"1\" max=\"100\" value=\"50\" oninput=\"diceTarget=+this.value;updDice()\"><div class=\"val\" id=\"dTargetVal\">50</div></div>\n  <div class=\"payout-hint\" id=\"dHint\"></div>\n  <button class=\"primary\" onclick=\"playDice()\">Roll</button>`;\n}\nfunction updDice(){\n  $('dTargetVal').textContent=diceTarget;\n  const wins=diceDir==='over'?(100-diceTarget):(diceTarget-1);\n  const m=wins>0?0.97*100/wins:0;\n  $('dHint').innerHTML=`Payout <b>${fmt(m)}x</b> - win <b>${fmt(getBet()*m)}</b>`;\n}\nasync function playDice(){\n  const bet=getBet(); if(!bet)return notify('Enter a bet amount.');\n  const res=await doPlay('dice','play',{bet,direction:diceDir,target:diceTarget});\n  if(res&&res.roll!==undefined){\n    $('resultBox').insertAdjacentHTML('afterbegin',\n      `<div class=\"result ${res.won?'win':'lose'}\"><div class=\"lbl\">DICE</div><div class=\"big\">${res.roll}</div></div>`);\n  }\n  showResult(res);\n}\n\n/* ---------- CRASH ---------- */\nconst ROCKET_SVG='<svg viewBox=\"0 0 24 32\" width=\"30\" height=\"40\" aria-hidden=\"true\"><path d=\"M12 0c3 5 8 7 10 14-2 2-5 2-7 0 1 5-1 10-3 18-2-8-4-13-3-18-2 2-5 2-7 0C4 7 9 5 12 0z\" fill=\"#e8c766\"/><path d=\"M9.5 19c2 2 3 2 5 0-1 4-2 7-2.5 10-.5-3-1.5-6-2.5-10z\" fill=\"#f0d98a\"/></svg>';\nasync function playCrash(){\n  const bet=getBet(); if(!bet)return notify('Enter a bet amount.');\n  const res=await doPlay('crash','play',{bet});\n  if(!res||!res.ok){showResult(res);return;}\n  const cp=res.crash_point;\n  $('panel').innerHTML=panelShell(curGame(),`\n    <div class=\"crash-stage\">\n      <div class=\"trail\" id=\"trail\" style=\"height:150px\"></div>\n      <div class=\"rocket-wrap\" id=\"rocketWrap\">${ROCKET_SVG}</div>\n      <div class=\"crash-mult\" id=\"crashMult\">1.00x</div>\n    </div>\n    <button class=\"primary\" id=\"cashBtn\" onclick=\"cashCrash()\">Cash Out</button>\n    <div class=\"hint-msg\" id=\"panelMsg\"></div>\n    <div id=\"resultBox\"></div><div class=\"fair\" id=\"fairBox\"></div>`);\n  $('fairBox').innerHTML=`Seed <code>${res.fair.seed_hash}...</code> crash point hidden until cash out`;\n  const t0=Date.now(),dur=7000;\n  const iv=setInterval(()=>{\n    const t=Math.min(1,(Date.now()-t0)/dur);\n    const mult=Math.max(1,Math.pow(cp,t));\n    $('crashMult').textContent=fmt(mult)+'x';\n    $('rocketWrap').style.bottom=(8+t*160)+'px';\n    $('trail').style.height=(10+t*150)+'px';\n    if(t>=1||mult>=cp){\n      clearInterval(iv);\n      $('crashMult').textContent='Crashed at '+fmt(cp)+'x';\n      $('rocketWrap').innerHTML=ROCKET_SVG.replace('#e8c766','#7a2c22').replace('#f0d98a','#9c3a2e');\n      if(!S.session||!S.session.cashed){\n        showResult({ok:true,won:false,payout:0,bet,balance:S.balance,fair:res.fair});\n      }\n    }\n  },40);\n}\nasync function cashCrash(){\n  const btn=$('cashBtn'); if(!btn||btn.disabled)return; btn.disabled=true;\n  const cur=parseFloat($('crashMult').textContent)||1;\n  const res=await doPlay('crash','cashout',{session_id:S.session&&S.session.id||1,multiplier:cur});\n  S.session=null;\n  showResult(res);\n}\nfunction curGame(){return (S.cfg.games||GAMES_META).find(x=>x.id===S.game);}\n\n/* ---------- MINES ---------- */\nlet minesCount=3;\nfunction pnlMines(){\n  return `\n  <div class=\"ctrl-row\">\n    ${[3,5,10].map(m=>`<button class=\"ctrl ${m===minesCount?'on':''}\" onclick=\"minesCount=${m};renderPanel(curGame())\">${m} Bombs</button>`).join('')}\n  </div>\n  <div class=\"mines-grid\" id=\"mGrid\"></div>\n  <button class=\"primary\" id=\"mStart\" onclick=\"startMines()\">Start Round</button>`;\n}\nasync function startMines(){\n  const bet=getBet(); if(!bet)return notify('Enter a bet amount.');\n  const res=await doPlay('mines','new',{bet,mines:minesCount});\n  if(!res||!res.ok){showResult(res);return;}\n  S.session={id:res.session_id,game:'mines',bet};\n  drawMines(res.fair);\n}\nfunction drawMines(fair){\n  const g=$('mGrid'); g.innerHTML='';\n  for(let i=0;i<25;i++){\n    const c=document.createElement('div'); c.className='mcell'; c.id='mc'+i;\n    c.onclick=()=>revealMine(i);\n    g.appendChild(c);\n  }\n  if(fair)$('fairBox').innerHTML=`Seed <code>${fair.seed_hash}...</code>`;\n  $('mStart').remove();\n  $('panel').insertAdjacentHTML('beforeend',\n    `<button class=\"primary alt\" id=\"mCash\" style=\"margin-top:12px\" onclick=\"cashMines()\">Cash Out</button>`);\n}\nasync function revealMine(cell){\n  if(!S.session)return;\n  const res=await doPlay('mines','reveal',{session_id:S.session.id,cell});\n  if(res&&res.ok===false){showResult(res);return;}\n  const el=$('mc'+cell);\n  if(res.won===false){\n    el.innerHTML='<div class=\"boom\"></div>'; el.classList.add('dead');\n    (res.revealed||[]).forEach(r=>{const e=$('mc'+r);if(e&&e.children.length===0){e.innerHTML='<div class=\"gem\"></div>';e.classList.add('rev');}});\n    S.session=null; const c=$('mCash'); c&&c.remove();\n    showResult(res);\n  }else if(res.won===true){\n    el.innerHTML='<div class=\"gem\"></div>'; el.classList.add('rev');\n    S.session=null; const c=$('mCash'); c&&c.remove();\n    showResult(res);\n  }else{\n    el.innerHTML='<div class=\"gem\"></div>'; el.classList.add('rev');\n    $('resultBox').innerHTML=`<div class=\"result lose\"><div class=\"lbl\">MULTIPLIER</div><div class=\"big\">${fmt(res.multiplier)}x</div><div class=\"sub\">Cash out <b>${fmt(res.potential_payout)}</b></div></div>`;\n  }\n}\nasync function cashMines(){\n  if(!S.session)return;\n  const res=await doPlay('mines','cashout',{session_id:S.session.id});\n  S.session=null; const c=$('mCash'); c&&c.remove();\n  showResult(res);\n}\n\n/* ---------- TOWERS ---------- */\nlet towDiff='easy';\nfunction pnlTowers(){\n  return `\n  <div class=\"ctrl-row\">\n    ${['easy','medium','hard'].map(d=>`<button class=\"ctrl ${d===towDiff?'on':''}\" onclick=\"towDiff='${d}';renderPanel(curGame())\">${d[0].toUpperCase()+d.slice(1)}</button>`).join('')}\n  </div>\n  <div id=\"towBoard\" style=\"margin-bottom:14px\"></div>\n  <button class=\"primary\" id=\"towStart\" onclick=\"startTowers()\">Start Round</button>`;\n}\nfunction towCell(state,label,on){\n  const styles={\n    clr:\"background:linear-gradient(180deg,#174a36,#0f3a2a);border-color:rgba(212,175,55,.6)\",\n    cur:\"background:linear-gradient(180deg,#174a36,#0f3a2a);border-color:rgba(212,175,55,.3)\",\n    dead:\"background:linear-gradient(180deg,#4a241d,#2a1410);border-color:rgba(200,80,60,.7)\",\n    fut:\"background:linear-gradient(180deg,#174a36,#0f3a2a);border-color:rgba(212,175,55,.18)\"\n  }[state];\n  const inner=state==='clr'?'<div class=\"gem\"></div>':state==='dead'?'<div class=\"boom\"></div>':'';\n  return `<div class=\"mcell\" style=\"${styles};width:50px;${state==='cur'?'cursor:pointer':''}\" ${on}>${inner}</div>`;\n}\nfunction towRowsHTML(cleared,deadRow,deadCol){\n  let h='';\n  for(let r=7;r>=0;r--){\n    h+=`<div style=\"display:flex;gap:6px;justify-content:center;margin-bottom:6px\">`;\n    for(let c=0;c<3;c++){\n      const state=r<cleared?'clr':(r===cleared?'cur':(r===deadRow&&c===deadCol?'dead':'fut'));\n      const on=state==='cur'?`onclick=\"pickTower(${c})\"`:'';\n      h+=towCell(state,'',on);\n    }\n    h+='</div>';\n  }\n  return h;\n}\nasync function startTowers(){\n  const bet=getBet(); if(!bet)return notify('Enter a bet amount.');\n  const res=await doPlay('towers','new',{bet,difficulty:towDiff});\n  if(!res||!res.ok){showResult(res);return;}\n  S.session={id:res.session_id,game:'towers',bet,cleared:0};\n  $('towStart').remove();\n  $('towBoard').innerHTML=towRowsHTML(0,-1,-1);\n  $('fairBox').innerHTML=`Seed <code>${res.fair.seed_hash}...</code>`;\n  $('panel').insertAdjacentHTML('beforeend',\n    `<button class=\"primary alt\" id=\"towCash\" style=\"margin-top:12px\" onclick=\"cashTowers()\">Cash Out</button>`);\n}\nasync function pickTower(col){\n  if(!S.session)return;\n  const res=await doPlay('towers','pick',{session_id:S.session.id,col});\n  if(res&&res.ok===false){showResult(res);return;}\n  if(res.won===false){\n    $('towBoard').innerHTML=towRowsHTML(S.session.cleared,res.row,col);\n    S.session=null; const c=$('towCash');c&&c.remove(); showResult(res);\n  }else if(res.won===true){\n    $('towBoard').innerHTML=towRowsHTML(8,-1,-1);\n    S.session=null; const c=$('towCash');c&&c.remove(); showResult(res);\n  }else{\n    S.session.cleared=res.row;\n    $('towBoard').innerHTML=towRowsHTML(res.row,-1,-1);\n    $('resultBox').innerHTML=`<div class=\"result lose\"><div class=\"lbl\">MULTIPLIER</div><div class=\"big\">${fmt(res.multiplier)}x</div><div class=\"sub\">Cash out <b>${fmt(res.potential_payout)}</b></div></div>`;\n  }\n}\nasync function cashTowers(){\n  if(!S.session)return;\n  const res=await doPlay('towers','cashout',{session_id:S.session.id});\n  S.session=null; const c=$('towCash');c&&c.remove(); showResult(res);\n}\n\n/* ---------- BLACKJACK ---------- */\nfunction pnlBJ(){\n  return `\n  <div class=\"hand-label\">DEALER</div>\n  <div class=\"cardzone\" id=\"bjDealer\"></div>\n  <div class=\"hand-label\">YOUR HAND</div>\n  <div class=\"cardzone\" id=\"bjPlayer\"></div>\n  <div class=\"payout-hint\" id=\"bjHint\"></div>\n  <button class=\"primary\" id=\"bjStart\" onclick=\"startBJ()\">Deal</button>`;\n}\nasync function startBJ(){\n  const bet=getBet(); if(!bet)return notify('Enter a bet amount.');\n  const res=await doPlay('blackjack','new',{bet});\n  if(!res||!res.ok){showResult(res);return;}\n  S.session={id:res.session_id,game:'blackjack',bet};\n  $('bjDealer').innerHTML=res.dealer.map(c=>c==='?'?'<div class=\"pcard back\"></div>':`<div class=\"pcard\">${c}</div>`).join('');\n  $('bjPlayer').innerHTML=res.player.map(c=>`<div class=\"pcard\">${c}</div>`).join('');\n  $('bjHint').innerHTML=`Your hand: <b>${res.player_value}</b>`;\n  $('fairBox').innerHTML=`Seed <code>${res.fair.seed_hash}...</code>`;\n  $('bjStart').remove();\n  $('panel').insertAdjacentHTML('beforeend',`\n    <div class=\"ctrl-row\" style=\"margin-top:12px\">\n      <button class=\"ctrl on\" onclick=\"bjAct('hit')\">Hit</button>\n      <button class=\"ctrl\" onclick=\"bjAct('stand')\">Stand</button>\n      <button class=\"ctrl\" onclick=\"bjAct('double')\">Double</button>\n    </div>`);\n}\nasync function bjAct(act){\n  if(!S.session)return;\n  const res=await doPlay('blackjack',act,{session_id:S.session.id});\n  if(res&&res.ok===false){showResult(res);return;}\n  if(res.player!==undefined&&res.player_value!==undefined&&res.won===undefined){\n    $('bjPlayer').innerHTML=res.player.map(c=>`<div class=\"pcard\">${c}</div>`).join('');\n    $('bjHint').innerHTML=`Your hand: <b>${res.player_value}</b>`;\n    return;\n  }\n  if(res.player_cards){\n    $('bjDealer').innerHTML=res.dealer_cards.map(c=>`<div class=\"pcard\">${c}</div>`).join('');\n    $('bjPlayer').innerHTML=res.player_cards.map(c=>`<div class=\"pcard\">${c}</div>`).join('');\n    $('bjHint').innerHTML=`You <b>${res.player_value}</b> - Dealer <b>${res.dealer_value}</b>`;\n    S.session=null;\n    showResult(res);\n  }\n}\n\n/* ---------- BACCARAT ---------- */\nlet bacSide='player';\nfunction pnlBaccarat(){\n  return `\n  <div class=\"ctrl-row\">\n    <button class=\"ctrl on\" onclick=\"bacSide='player';updBac()\">Player 2x</button>\n    <button class=\"ctrl\" onclick=\"bacSide='banker';updBac()\">Banker 1.95x</button>\n    <button class=\"ctrl\" onclick=\"bacSide='tie';updBac()\">Tie 9x</button>\n  </div>\n  <div class=\"hand-label\">BANKER</div><div class=\"cardzone\" id=\"bacB\"></div>\n  <div class=\"hand-label\">PLAYER</div><div class=\"cardzone\" id=\"bacP\"></div>\n  <div class=\"payout-hint\" id=\"bacHint\"></div>\n  <button class=\"primary\" onclick=\"playBac()\">Deal</button>`;\n}\nfunction updBac(){$('bacHint').innerHTML=`Betting on <b>${bacSide}</b> at ${bacSide==='player'?'2x':bacSide==='banker'?'1.95x':'9x'}`;}\nasync function playBac(){\n  const bet=getBet(); if(!bet)return notify('Enter a bet amount.');\n  const res=await doPlay('baccarat','play',{bet,side:bacSide});\n  if(res&&res.player_cards){\n    $('bacB').innerHTML=res.banker_cards.map(c=>`<div class=\"pcard\">${c}</div>`).join('');\n    $('bacP').innerHTML=res.player_cards.map(c=>`<div class=\"pcard\">${c}</div>`).join('');\n    $('bacHint').innerHTML=`Player <b>${res.player_value}</b> - Banker <b>${res.banker_value}</b> - Winner: <b>${res.winner.toUpperCase()}</b>`;\n  }\n  showResult(res);\n}\n\n/* ---------- ROULETTE ---------- */\nlet roulChoice='red';\nfunction pnlRoulette(){\n  return `\n  <div class=\"roul-wheel\"><div class=\"ball\" id=\"roulBall\"></div><div class=\"hub\"><span>CR</span></div></div>\n  <div class=\"ctrl-row\">\n    <button class=\"ctrl on\" onclick=\"roulChoice='red';markRoul()\">Red</button>\n    <button class=\"ctrl\" onclick=\"roulChoice='black';markRoul()\">Black</button>\n    <button class=\"ctrl\" onclick=\"roulChoice='green';markRoul()\">Zero</button>\n    <button class=\"ctrl\" onclick=\"roulChoice='even';markRoul()\">Even</button>\n    <button class=\"ctrl\" onclick=\"roulChoice='odd';markRoul()\">Odd</button>\n    <button class=\"ctrl\" onclick=\"roulChoice='low';markRoul()\">1-18</button>\n    <button class=\"ctrl\" onclick=\"roulChoice='high';markRoul()\">19-36</button>\n  </div>\n  <div class=\"num-pad\" id=\"roulPad\"></div>\n  <button class=\"primary\" onclick=\"playRoul()\">Spin</button>`;\n}\nfunction markRoul(){\n  document.querySelectorAll('#view-game .ctrl').forEach(b=>{\n    const t=b.textContent.trim();\n    const map={'Red':'red','Black':'black','Zero':'green','Even':'even','Odd':'odd','1-18':'low','19-36':'high'};\n    b.classList.toggle('on',map[t]===roulChoice);\n  });\n  document.querySelectorAll('#roulPad button').forEach(b=>b.classList.toggle('on',b.textContent===roulChoice));\n}\nasync function playRoul(){\n  const bet=getBet(); if(!bet)return notify('Enter a bet amount.');\n  $('roulBall').style.transform='rotate(0deg)';\n  requestAnimationFrame(()=>{\n    $('roulBall').style.transform='rotate('+(1800+Math.random()*720)+'deg)';\n  });\n  const res=await doPlay('roulette','play',{bet,choice:roulChoice});\n  if(res&&res.spin!==undefined){\n    const deg=res.spin*(360/37);\n    setTimeout(()=>{ $('roulBall').style.transform='rotate('+(1800+deg)+'deg)'; },200);\n    setTimeout(()=>{\n      $('resultBox').insertAdjacentHTML('afterbegin',\n        `<div class=\"result ${res.won?'win':'lose'}\"><div class=\"lbl\">NUMBER</div><div class=\"big\">${res.spin} ${res.color.toUpperCase()}</div></div>`);\n    },1500);\n  }\n  setTimeout(()=>showResult(res),4200);\n}\n\n/* ---------- HI-LO ---------- */\nfunction pnlHilo(){\n  return `\n  <div class=\"cardzone\" id=\"hiloCard\"></div>\n  <div class=\"payout-hint\" id=\"hiloHint\"></div>\n  <button class=\"primary\" id=\"hiloStart\" onclick=\"startHilo()\">Deal Card</button>`;\n}\nasync function startHilo(){\n  const bet=getBet(); if(!bet)return notify('Enter a bet amount.');\n  const res=await doPlay('hilo','new',{bet});\n  if(!res||!res.ok){showResult(res);return;}\n  S.session={id:res.session_id,game:'hilo',bet};\n  $('hiloCard').innerHTML=`<div class=\"pcard\">${res.card}</div>`;\n  $('hiloHint').innerHTML=`Higher <b>${fmt(res.higher_mult)}x</b> - Lower <b>${fmt(res.lower_mult)}x</b> - chain <b>1x</b>`;\n  $('fairBox').innerHTML=`Seed <code>${res.fair.seed_hash}...</code>`;\n  $('hiloStart').remove();\n  $('panel').insertAdjacentHTML('beforeend',`\n    <div class=\"ctrl-row\" style=\"margin-top:12px\">\n      <button class=\"ctrl on\" onclick=\"hiloAct('higher')\">Higher</button>\n      <button class=\"ctrl\" onclick=\"hiloAct('lower')\">Lower</button>\n    </div>\n    <button class=\"primary alt\" onclick=\"hiloAct('cashout')\">Cash Out</button>`);\n}\nasync function hiloAct(act){\n  if(!S.session)return;\n  const res=await doPlay('hilo',act,{session_id:S.session.id});\n  if(res&&res.ok===false){showResult(res);return;}\n  if(res.card!==undefined&&res.won===undefined){\n    $('hiloCard').innerHTML=`<div class=\"pcard\">${res.card}</div>`;\n    $('hiloHint').innerHTML=`Higher <b>${fmt(res.higher_mult)}x</b> - Lower <b>${fmt(res.lower_mult)}x</b> - chain <b>${fmt(res.multiplier)}x</b> - cash out <b>${fmt(res.potential_payout)}</b>`;\n    return;\n  }\n  if(res.drawn!==undefined&&res.won===false){\n    $('hiloCard').innerHTML=`<div class=\"pcard\">${res.drawn}</div>`;\n    if(res.tie)$('hiloHint').innerHTML='Tie - round lost.';\n    S.session=null; showResult(res); return;\n  }\n  S.session=null; showResult(res);\n}\n\n/* ---------- PLINKO ---------- */\nlet plinkoRisk='low';\nfunction pnlPlinko(){\n  return `\n  <div class=\"ctrl-row\">\n    ${['low','medium','high'].map(r=>`<button class=\"ctrl ${r===plinkoRisk?'on':''}\" onclick=\"plinkoRisk='${r}';renderPanel(curGame())\">${r[0].toUpperCase()+r.slice(1)}</button>`).join('')}\n  </div>\n  <div class=\"plinko-board\" id=\"plinkoBoard\"></div>\n  <button class=\"primary\" onclick=\"playPlinko()\">Drop Ball</button>`;\n}\nfunction drawPlinko(){\n  const b=$('plinkoBoard'); b.innerHTML='';\n  const tabs={low:[5.4,2,1.1,0.95,0.48,0.95,1.1,2,5.4],medium:[12,3.1,1.3,0.65,0.3,0.65,1.3,3.1,12],high:[20,4.5,1.6,0.35,0.18,0.35,1.6,4.5,20]}[plinkoRisk];\n  tabs.forEach((m,i)=>{\n    const d=document.createElement('div'); d.className='pbucket'; d.id='pb'+i;\n    d.textContent=fmt(m)+'x'; d.style.left=(i*11.11)+'%'; d.style.width='11.11%';\n    b.appendChild(d);\n  });\n}\nasync function playPlinko(){\n  const bet=getBet(); if(!bet)return notify('Enter a bet amount.');\n  drawPlinko();\n  const ball=document.createElement('div'); ball.className='pball'; ball.id='pball';\n  $('plinkoBoard').appendChild(ball);\n  const res=await doPlay('plinko','play',{bet,risk:plinkoRisk});\n  const bucket=(res&&res.bucket!==undefined)?res.bucket:4;\n  setTimeout(()=>{\n    ball.style.left=((bucket*11.11)+2.5)+'%';\n    ball.style.top='190px';\n  },60);\n  setTimeout(()=>{\n    document.querySelectorAll('.pbucket').forEach((b,i)=>b.classList.toggle('hit',i===bucket));\n    showResult(res);\n  },1100);\n}\n\n/* ---------- KENO ---------- */\nlet kenoPicks=new Set();\nfunction pnlKeno(){\n  kenoPicks=new Set();\n  let cells='';\n  for(let i=1;i<=80;i++)cells+=`<div class=\"kcell\" id=\"k${i}\" onclick=\"toggleKeno(${i})\">${i}</div>`;\n  return `\n  <div class=\"keno-status\" id=\"kenoStatus\">Pick 1 to 10 numbers</div>\n  <div class=\"keno-grid\">${cells}</div>\n  <button class=\"primary\" onclick=\"playKeno()\">Play Keno</button>`;\n}\nfunction toggleKeno(n){\n  const el=$('k'+n);\n  if(kenoPicks.has(n)){kenoPicks.delete(n);el.classList.remove('sel');}\n  else if(kenoPicks.size<10){kenoPicks.add(n);el.classList.add('sel');}\n  $('kenoStatus').textContent=`Pick 1 to 10 numbers - selected ${kenoPicks.size}`;\n}\nasync function playKeno(){\n  if(!kenoPicks.size)return notify('Pick at least one number.');\n  const bet=getBet(); if(!bet)return notify('Enter a bet amount.');\n  const res=await doPlay('keno','play',{bet,picks:[...kenoPicks]});\n  if(res&&res.drawn){\n    res.drawn.forEach(n=>{\n      const el=$('k'+n);\n      el.classList.add(kenoPicks.has(n)?'both':'hit');\n    });\n    $('kenoStatus').textContent=`Hits: ${res.hits.length} - payout ${fmt(res.multiplier)}x`;\n  }\n  showResult(res);\n}\n\n/* ---------- WHEEL ---------- */\nconst WHEEL_SEGS=[{m:0,w:30,c:'#174a36'},{m:0.9,w:42,c:'#0f3a2a'},{m:1.3,w:14,c:'#2f6b46'},\n  {m:1.7,w:7,c:'#4a8a5e'},{m:2.6,w:4,c:'#b3903a'},{m:4.3,w:2,c:'#c9a227'},{m:8.5,w:1,c:'#8a6d1f'}];\nfunction pnlWheel(){\n  let total=WHEEL_SEGS.reduce((a,s)=>a+s.w,0);\n  let segs='',acc=0;\n  WHEEL_SEGS.forEach(s=>{\n    const a0=acc/total*360,a1=(acc+s.w)/total*360;\n    segs+=`<path d=\"${arc(105,105,100,a0,a1)}\" fill=\"${s.c}\" stroke=\"#0a3527\" stroke-width=\"2\"/>`;\n    const mid=(a0+a1)/2*Math.PI/180;\n    segs+=`<text x=\"${105+84*Math.sin(mid)}\" y=\"${105-84*Math.cos(mid)+4}\" text-anchor=\"middle\" font-family=\"Georgia,serif\" font-size=\"13\" font-weight=\"700\" fill=\"#f2ecdc\">${s.m}x</text>`;\n    acc+=s.w;\n  });\n  return `\n  <div class=\"wheel-wrap\">\n    <div class=\"wheel-pointer\"></div>\n    <svg class=\"wheel-svg\" id=\"wheelSvg\" viewBox=\"0 0 210 210\">${segs}</svg>\n  </div>\n  <button class=\"primary\" onclick=\"playWheel()\">Spin the Wheel</button>`;\n}\nfunction arc(cx,cy,r,a0,a1){\n  const p=(a)=>[cx+r*Math.sin(a*Math.PI/180),cy-r*Math.cos(a*Math.PI/180)];\n  const [x0,y0]=p(a0),[x1,y1]=p(a1);\n  const large=a1-a0>180?1:0;\n  return `M ${cx} ${cy} L ${x0} ${y0} A ${r} ${r} 0 ${large} 1 ${x1} ${y1} Z`;\n}\nasync function playWheel(){\n  const bet=getBet(); if(!bet)return notify('Enter a bet amount.');\n  const res=await doPlay('wheel','play',{bet});\n  const idx=(res&&res.segment!==undefined)?res.segment:0;\n  let total=WHEEL_SEGS.reduce((a,s)=>a+s.w,0),acc=0;\n  for(let i=0;i<idx;i++)acc+=WHEEL_SEGS[i].w;\n  const target=(acc+WHEEL_SEGS[idx].w/2)/total*360;\n  const rot=1800+(360-target)+90;\n  const svg=$('wheelSvg');\n  svg.style.transform='rotate(0deg)';\n  requestAnimationFrame(()=>{ svg.style.transform='rotate('+rot+'deg)'; });\n  setTimeout(()=>showResult(res),4300);\n}\n\n/* ---------- LIMBO ---------- */\nlet limboTarget=2;\nfunction pnlLimbo(){\n  const t=limboTarget, p=(1e8-t*1e6)/1e8, m=0.97/p;\n  return `\n  <div class=\"limbo-target\">\n    <label>TARGET</label>\n    <input type=\"number\" id=\"limboIn\" value=\"${limboTarget}\" step=\"0.01\" min=\"1.01\" oninput=\"limboTarget=parseFloat(this.value)||2;updLimbo()\">\n    <div class=\"val\" id=\"limboMult\">${fmt(m)}x</div>\n  </div>\n  <div class=\"payout-hint\">Win chance <b>${fmt(p*100)}%</b> - payout <b>${fmt(m)}x</b></div>\n  <button class=\"primary\" onclick=\"playLimbo()\">Launch</button>`;\n}\nfunction updLimbo(){\n  const t=Math.max(1.01,Math.min(100000,limboTarget));\n  const p=(1e8-t*1e6)/1e8, m=0.97/p;\n  $('limboMult').textContent=fmt(m)+'x';\n}\nasync function playLimbo(){\n  const bet=getBet(); if(!bet)return notify('Enter a bet amount.');\n  const res=await doPlay('limbo','play',{bet,target:limboTarget});\n  if(res&&res.multiplier!==undefined){\n    $('resultBox').insertAdjacentHTML('afterbegin',\n      `<div class=\"result ${res.won?'win':'lose'}\"><div class=\"lbl\">TARGET ${fmt(res.target)}x</div><div class=\"big\">${fmt(res.multiplier)}x</div></div>`);\n  }\n  showResult(res);\n}\n\n/* ---------- COIN FLIP ---------- */\nlet coinSide='heads';\nfunction pnlCoin(){\n  return `\n  <div class=\"coin-stage\"><div class=\"coin\" id=\"coinEl\">CR</div></div>\n  <div class=\"ctrl-row\">\n    <button class=\"ctrl on\" onclick=\"coinSide='heads'\">Heads</button>\n    <button class=\"ctrl\" onclick=\"coinSide='tails'\">Tails</button>\n  </div>\n  <div class=\"payout-hint\">Payout <b>1.94x</b></div>\n  <button class=\"primary\" onclick=\"playCoin()\">Flip</button>`;\n}\nasync function playCoin(){\n  const bet=getBet(); if(!bet)return notify('Enter a bet amount.');\n  $('coinEl').classList.remove('flip'); void $('coinEl').offsetWidth;\n  $('coinEl').classList.add('flip');\n  const res=await doPlay('coinflip','play',{bet,side:coinSide});\n  if(res&&res.landed){\n    setTimeout(()=>{\n      $('coinEl').textContent=res.landed==='heads'?'H':'T';\n      $('resultBox').insertAdjacentHTML('afterbegin',\n        `<div class=\"result ${res.won?'win':'lose'}\"><div class=\"lbl\">LANDED</div><div class=\"big\">${res.landed.toUpperCase()}</div></div>`);\n    },700);\n  }\n  setTimeout(()=>showResult(res),1500);\n}\n\n/* ---------- SLOTS ---------- */\nfunction pnlSlots(){\n  return `\n  <div class=\"slots-row\">\n    <div class=\"sreel\" id=\"sr0\"><div class=\"strip\"></div></div>\n    <div class=\"sreel\" id=\"sr1\"><div class=\"strip\"></div></div>\n    <div class=\"sreel\" id=\"sr2\"><div class=\"strip\"></div></div>\n  </div>\n  <button class=\"primary\" onclick=\"playSlots()\">Spin</button>`;\n}\nconst SLOT_SYM=['C','R','7','A','K','Q','J'];\nfunction fillReel(el,stopAt){\n  const strip=el.querySelector('.strip');\n  let syms=[];\n  for(let i=0;i<12;i++)syms.push(SLOT_SYM[Math.floor(Math.random()*SLOT_SYM.length)]);\n  syms[10]=stopAt;\n  strip.innerHTML=syms.map(s=>`<span>${s}</span>`).join('');\n}\nasync function playSlots(){\n  const bet=getBet(); if(!bet)return notify('Enter a bet amount.');\n  const res=await doPlay('slots','play',{bet});\n  const reel=(res&&res.reel)?res.reel:[SLOT_SYM[0],SLOT_SYM[0],SLOT_SYM[0]];\n  [0,1,2].forEach(i=>{const el=$('sr'+i);el.classList.add('spinning');fillReel(el,reel[i]);});\n  setTimeout(()=>{\n    [0,1,2].forEach(i=>{\n      const el=$('sr'+i); el.classList.remove('spinning');\n      el.querySelector('.strip').style.transform='translateY(-'+(10*88)+'px)';\n    });\n    showResult(res);\n  },1600);\n}\n\n/* ============================== WALLET / BOARD ============================== */\nfunction renderWallet(){\n  $('stGames').textContent=S.stats.games||0;\n  $('stWins').textContent=(S.stats.wins||0)+' / '+(S.stats.losses||0);\n  $('stWagered').textContent=fmt(S.stats.wagered||0);\n  $('stPaid').textContent=fmt(S.stats.paid||0);\n  const hist=S.history||[];\n  $('history').innerHTML=hist.length?hist.map(h=>{\n    const win=(h.payout||0)>0;\n    return `<div class=\"row\"><div class=\"mono\">${monoFor(h.game)}</div>\n      <div class=\"grow\"><div class=\"t1\">${gameName(h.game)}</div><div class=\"t2\">${h.status}${h.created_at?' - '+h.created_at.slice(0,16).replace('T',' '):''}</div></div>\n      <div class=\"amt ${win?'pos':'neg'}\">${win?'+':'-'}${fmt(h.payout||0)}</div></div>`;\n  }).join(''):`<div class=\"empty\">No rounds yet.<br>Take a seat at one of the tables.</div>`;\n}\nfunction renderBoard(){\n  const b=S.board||[];\n  $('board').innerHTML=b.length?b.map((u,i)=>`\n    <div class=\"row\"><div class=\"rank ${i<3?'gold':''}\">${i+1}</div>\n    <div class=\"grow\"><div class=\"t1\">${em(u.first_name||u.username||'Player')}</div><div class=\"t2\">@${em(u.username||'anonymous')}</div></div>\n    <div class=\"amt\">${fmt(u.balance)}</div></div>`).join(''):`<div class=\"empty\">The leaderboard populates once players connect through the bot.</div>`;\n}\nfunction walletGo(kind){\n  if(S.demo)return notify('Deposits and withdrawals are handled by the bot after deployment.');\n  const u=S.cfg.botUsername;\n  if(!u)return notify('Bot username not configured. Set TELEGRAM_BOT_TOKEN.');\n  window.open('https://t.me/'+u+(kind==='deposit'?'?start=deposit':''),'_blank');\n  return false;\n}\nfunction monoFor(g){const m={dice:'D',crash:'C',mines:'M',towers:'T',blackjack:'BJ',baccarat:'BA',roulette:'R',hilo:'HL',plinko:'P',keno:'K',wheel:'W',limbo:'L',coinflip:'CF',slots:'S'};return m[g]||'G';}\nfunction gameName(g){const m={dice:'Dice',crash:'Crash',mines:'Mines',towers:'Towers',blackjack:'Blackjack',baccarat:'Baccarat',roulette:'Roulette',hilo:'Hi-Lo',plinko:'Plinko',keno:'Keno',wheel:'Wheel of Fortune',limbo:'Limbo',coinflip:'Coin Flip',slots:'Slots'};return m[g]||g;}\nconst GAMES_META=[\n  {id:'dice',name:'Dice',mono:'D',tag:'Instant'},\n  {id:'crash',name:'Crash',mono:'C',tag:'Live'},\n  {id:'mines',name:'Mines',mono:'M',tag:'Skill'},\n  {id:'towers',name:'Towers',mono:'T',tag:'Skill'},\n  {id:'blackjack',name:'Blackjack',mono:'BJ',tag:'Cards'},\n  {id:'baccarat',name:'Baccarat',mono:'BA',tag:'Cards'},\n  {id:'roulette',name:'Roulette',mono:'R',tag:'Classic'},\n  {id:'hilo',name:'Hi-Lo',mono:'HL',tag:'Cards'},\n  {id:'plinko',name:'Plinko',mono:'P',tag:'Instant'},\n  {id:'keno',name:'Keno',mono:'K',tag:'Instant'},\n  {id:'wheel',name:'Wheel of Fortune',mono:'W',tag:'Instant'},\n  {id:'limbo',name:'Limbo',mono:'L',tag:'Instant'},\n  {id:'coinflip',name:'Coin Flip',mono:'CF',tag:'Instant'},\n  {id:'slots',name:'Slots',mono:'S',tag:'Classic'},\n];\n\n/* roulette number pad injection after render */\nconst _origRenderPanel=renderPanel;\nrenderPanel=function(g){\n  _origRenderPanel(g);\n  if(g.id==='roulette'){\n    let h='';\n    for(let n=0;n<=36;n++)h+=`<button onclick=\"roulChoice='${n}';markRoul()\">${n}</button>`;\n    $('roulPad').innerHTML=h;\n  }\n};\n\nboot();\n</script>\n</body>\n</html>\n"
# <EMBED-INDEX-END>

_sess_lock = threading.Lock()
MINI_SESSIONS: Dict[int, Dict[str, Any]] = {}  # live in-memory game state

# ---------------------------------------------------------------------------
# Fair engine (imported from casino_bot where shared; miniapp-only games here)
# ---------------------------------------------------------------------------

fair_roll = CB._solo_fair_roll
mines_mult = CB._mines_multiplier
dice_mult = CB._dice_multiplier
crash_point = CB._crash_point
slots_spin = CB._slots_spin
roulette_spin = CB._roulette_spin
roulette_payout = CB._roulette_payout
fresh_deck = CB._fresh_deck
bj_value = CB._bj_value
hilo_mult = CB._hilo_multiplier
new_seed = CB._solo_new_seed


def p_outcome(seed: str, nonce: int, salt: str) -> float:
    """Deterministic float in [0,1) derived from (seed, nonce, salt)."""
    return fair_roll(seed, nonce, salt)


def shuffled(seed: str, nonce: int, items: List[Any]) -> List[Any]:
    return CB._solo_shuffle(seed, nonce, items)


# --- Plinko (8 rows, 9 buckets) ---
PLINKO_ROWS = 8
PLINKO_TABLES = {
    "low": [Decimal("5.4"), Decimal("2.0"), Decimal("1.1"), Decimal("0.95"), Decimal("0.48"),
            Decimal("0.95"), Decimal("1.1"), Decimal("2.0"), Decimal("5.4")],
    "medium": [Decimal("12.0"), Decimal("3.1"), Decimal("1.3"), Decimal("0.65"), Decimal("0.30"),
               Decimal("0.65"), Decimal("1.3"), Decimal("3.1"), Decimal("12.0")],
    "high": [Decimal("20.0"), Decimal("4.5"), Decimal("1.6"), Decimal("0.35"), Decimal("0.18"),
             Decimal("0.35"), Decimal("1.6"), Decimal("4.5"), Decimal("20.0")],
}


def plinko_bucket(seed: str, nonce: int) -> int:
    rights = sum(1 for i in range(PLINKO_ROWS) if p_outcome(seed, nonce, f"plinko:{i}") >= 0.5)
    return rights


# --- Keno ---
# Tiers pay from 2+ hits with a shared weight budget (house edge is stable at
# every tier; the extreme tiers are capped at 1000x payout).
def keno_multiplier(picks: int, hits: int) -> Decimal:
    if hits < 2:
        return Decimal("0")
    total = comb(80, 10)
    ways = comb(picks, hits) * comb(80 - picks, 10 - hits)
    if ways <= 0:
        return Decimal("0")
    tiers = picks - 1  # paying tiers: 2 .. picks
    weight = Decimal(1) / Decimal(tiers)
    mult = Decimal("0.97") * weight * Decimal(total) / Decimal(ways)
    return min(Decimal("1000"), quantize_money(mult))


def keno_draw(seed: str, nonce: int) -> List[int]:
    return sorted(shuffled(seed, nonce, list(range(1, 81)))[:10])


# --- Wheel of Fortune ---
WHEEL_MULTIPLIERS = [Decimal("0"), Decimal("0.9"), Decimal("1.3"), Decimal("1.7"),
                     Decimal("2.6"), Decimal("4.3"), Decimal("8.5")]
WHEEL_WEIGHTS = [30, 42, 14, 7, 4, 2, 1]


def wheel_spin(seed: str, nonce: int) -> int:
    r = p_outcome(seed, nonce, "wheel")
    total = sum(WHEEL_WEIGHTS)
    acc = 0.0
    for idx, w in enumerate(WHEEL_WEIGHTS):
        acc += w / total
        if r < acc:
            return idx
    return len(WHEEL_MULTIPLIERS) - 1


# --- Limbo ---
def limbo_multiplier(target: Decimal) -> Decimal:
    t = float(max(Decimal("1.01"), min(Decimal("100000"), target)))
    p = (1e8 - t * 1e6) / 1e8
    return quantize_money(Decimal("0.97") / Decimal(str(p)))


# --- Towers (8 rows x 3 cols) ---
TOWER_DIFFICULTY = {"easy": 1, "medium": 2, "hard": 3}


def towers_multiplier(rows_cleared: int, bad_per_row: int) -> Decimal:
    step = Decimal(3) / Decimal(3 - bad_per_row)
    return quantize_money(Decimal("0.97") * (step ** rows_cleared))


def towers_layout(seed: str, nonce: int, bad_per_row: int) -> List[List[int]]:
    rows = []
    for r in range(8):
        cols = shuffled(seed, nonce, list(range(3)))
        rows.append(sorted(cols[:bad_per_row]))
    return rows


# --- Baccarat ---
def _bac_value(hand: List[int]) -> int:
    return sum(min(c, 10) % 10 for c in hand) % 10


def baccarat_round(seed: str, nonce: int) -> Dict[str, Any]:
    deck = shuffled(seed, nonce, (list(range(1, 10)) * 4 + [0] * 16))
    player = [deck.pop(0), deck.pop(0)]
    banker = [deck.pop(0), deck.pop(0)]
    pv, bv = _bac_value(player), _bac_value(banker)
    if pv < 8 and bv < 8:
        if pv <= 5:
            player.append(deck.pop(0))
            pv = _bac_value(player)
        if bv <= 5 or (bv == 6 and pv in (6, 7)):
            if (bv <= 2) or (bv == 3 and pv != 8) or (bv == 4 and pv in (2, 3, 4, 5, 6, 7)) \
                    or (bv == 5 and pv in (4, 5, 6, 7)) or (bv == 6 and pv in (6, 7)):
                banker.append(deck.pop(0))
                bv = _bac_value(banker)
    if pv > bv:
        winner = "player"
    elif bv > pv:
        winner = "banker"
    else:
        winner = "tie"
    return {"player": player, "banker": banker, "pv": pv, "bv": bv, "winner": winner}


BAC_MULTIPLIERS = {"player": Decimal("2.00"), "banker": Decimal("1.95"), "tie": Decimal("9.00")}

# --- Card labels ---
CARD_GLYPH = {1: "A", 11: "J", 12: "Q", 13: "K"}


def card_label(c: int) -> str:
    if c == 0:
        return "10"
    return CARD_GLYPH.get(c, str(c))


# ---------------------------------------------------------------------------
# Telegram initData auth
# ---------------------------------------------------------------------------

def validate_init_data(init_data: str) -> Optional[Dict[str, Any]]:
    """Returns the parsed Telegram WebApp user payload, or None if invalid."""
    if DEMO_MODE:
        # No token configured: local/demo usage (also drives the in-app preview).
        data = {}
        try:
            data = dict(parse_qsl(init_data, keep_blank_values=True))
        except Exception:
            data = {}
        user_raw = data.get("user") or "{}"
        try:
            user = json.loads(user_raw)
        except Exception:
            user = {}
        if not isinstance(user, dict) or "id" not in user:
            user = {"id": 777000, "first_name": "Preview Player", "username": "preview"}
        return {"user": user, "demo": True}

    if not init_data:
        return None
    pairs = parse_qsl(init_data, keep_blank_values=True)
    data = dict(pairs)
    received_hash = data.pop("hash", "")
    if not received_hash:
        return None
    data_check_string = "\n".join(f"{k}={v}" for k, v in pairs if k != "hash")
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode("utf-8"), hashlib.sha256).digest()
    calc = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, received_hash):
        return None
    try:
        auth_date = int(data.get("auth_date", "0"))
        if auth_date and time.time() - auth_date > 86400:
            return None
        user = json.loads(data.get("user", "{}"))
    except Exception:
        return None
    if "id" not in user:
        return None
    return {"user": user, "demo": False}


def user_from_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    u = payload["user"]
    uid = int(u["id"])
    username = str(u.get("username") or "")
    first_name = str(u.get("first_name") or "Player")
    return {"id": uid, "username": username, "name": first_name, "demo": payload.get("demo", False)}


# ---------------------------------------------------------------------------
# Economy helpers (shared SQLite via casino_bot)
# ---------------------------------------------------------------------------

def mini_limits() -> Dict[str, float]:
    mn, mx = CB.solo_limits()
    return {"min": float(mn), "max": float(mx)}


def mini_debit(uid: int, amount: Decimal, game: str) -> None:
    CB.solo_debit(uid, amount, game)


def mini_credit(uid: int, amount: Decimal, game: str) -> None:
    CB.solo_credit(uid, amount, game)


def mini_history_insert(uid: int, game: str, bet: Decimal, payout: Decimal, status: str,
                        seed: str, nonce: int, result: Dict[str, Any]) -> None:
    CB.solo_history_insert(uid, game, bet, payout, status, seed, nonce, result)


def mini_session_insert(uid: int, game: str, bet: Decimal, seed: str, nonce: int,
                        state: Dict[str, Any]) -> int:
    return CB._solo_insert_session(uid, game, bet, seed, nonce, state, 0, 0)


def mini_session(sid: int) -> Optional[Dict[str, Any]]:
    return CB._solo_session(sid)


def mini_session_update(sid: int, status: Optional[str] = None, state: Optional[Dict[str, Any]] = None) -> None:
    CB._solo_update_session(sid, status=status, state=state)


def fair_block(seed: str, nonce: int) -> Dict[str, str]:
    return {
        "seed_hash": hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24],
        "nonce": str(nonce),
    }


# ---------------------------------------------------------------------------
# Game resolution
# ---------------------------------------------------------------------------

class MiniGameError(Exception):
    def __init__(self, message: str, code: str = "bad_request"):
        super().__init__(message)
        self.message = message
        self.code = code


def _parse_bet(data: Dict[str, Any]) -> Decimal:
    try:
        bet = quantize_money(str(data.get("bet", "")))
    except Exception:
        raise MiniGameError("Invalid bet amount.")
    mn, mx = CB.solo_limits()
    if bet < mn:
        raise MiniGameError(f"Minimum bet is {fmt_amount(mn)} {CURRENCY}.")
    if bet > mx:
        raise MiniGameError(f"Maximum bet is {fmt_amount(mx)} {CURRENCY}.")
    return bet


def resolve_game(uid: int, game: str, action: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve one game action against the shared economy. Raises MiniGameError
    / InsufficientBalance on failure. Returns a result dict (already settled)."""
    data = data or {}
    if game == "dice":
        if action != "play":
            raise MiniGameError("Unknown action.")
        bet = _parse_bet(data)
        direction = str(data.get("direction", "over")).lower()
        if direction not in ("over", "under"):
            raise MiniGameError("Direction must be 'over' or 'under'.")
        try:
            target = int(data.get("target", 50))
        except Exception:
            raise MiniGameError("Invalid target.")
        if not 1 <= target <= 100:
            raise MiniGameError("Target must be 1-100.")
        seed, nonce = new_seed(), 0
        roll = int(p_outcome(seed, nonce, "dice") * 100) + 1
        won = (roll > target) if direction == "over" else (roll < target)
        mult = dice_mult(target, direction)
        payout = quantize_money(bet * mult) if won else Decimal("0")
        mini_debit(uid, bet, "dice")
        if payout > 0:
            mini_credit(uid, payout, "dice")
        result = {"roll": roll, "target": target, "direction": direction, "multiplier": float(mult),
                  "won": won, "payout": float(payout), "bet": float(bet)}
        mini_history_insert(uid, "dice", bet, payout, "won" if won else "lost", seed, nonce, result)
        return {**result, "fair": fair_block(seed, nonce)}

    if game == "crash":
        if action == "play":
            bet = _parse_bet(data)
            seed, nonce = new_seed(), 0
            cp = crash_point(seed, nonce)
            mini_debit(uid, bet, "crash")
            state = {"bet": float(bet), "crash_point": float(cp), "cashed": False, "started": time.time()}
            sid = mini_session_insert(uid, "crash", bet, seed, nonce, state)
            MINI_SESSIONS[sid] = state
            return {"ok": True, "session_id": sid, "crash_point": float(cp),
                    "bet": float(bet), "fair": fair_block(seed, nonce)}
        if action == "cashout":
            try:
                sid = int(data.get("session_id"))
            except Exception:
                raise MiniGameError("Missing session.")
            sess = mini_session(sid)
            if sess is None or int(sess["user_id"]) != uid or str(sess["status"]) != "active":
                raise MiniGameError("Session not active.", "session_gone")
            state = json.loads(sess["state"])
            cp = Decimal(str(state["crash_point"]))
            requested = quantize_money(str(data.get("multiplier", "1")))
            if requested < Decimal("1.00"):
                requested = Decimal("1.00")
            if requested >= cp:
                requested = quantize_money((cp - Decimal("0.01")) if cp > Decimal("1.01") else Decimal("1.00"))
            bet = Decimal(str(sess["bet"]))
            payout = quantize_money(bet * requested)
            state["cashed"] = True
            state["cashed_at"] = float(requested)
            mini_session_update(sid, status="won", state=state)
            mini_credit(uid, payout, "crash")
            result = {"won": True, "multiplier": float(requested), "crash_point": float(cp),
                      "payout": float(payout), "bet": float(bet)}
            mini_history_insert(uid, "crash", bet, payout, "won", sess["seed"], int(sess["nonce"]), result)
            MINI_SESSIONS.pop(sid, None)
            return {**result, "fair": fair_block(sess["seed"], int(sess["nonce"]))}
        raise MiniGameError("Unknown action.")

    if game == "mines":
        if action == "new":
            bet = _parse_bet(data)
            try:
                mines = int(data.get("mines", 3))
            except Exception:
                mines = 3
            if mines not in (3, 5, 10):
                raise MiniGameError("Mines must be 3, 5 or 10.")
            seed, nonce = new_seed(), 0
            bombs = sorted(shuffled(seed, nonce, list(range(25)))[:mines])
            mini_debit(uid, bet, "mines")
            state = {"mines_count": mines, "bombs": bombs, "revealed": [], "bet": float(bet)}
            sid = mini_session_insert(uid, "mines", bet, seed, nonce, state)
            MINI_SESSIONS[sid] = state
            return {"ok": True, "session_id": sid, "grid": [{"i": i, "revealed": False} for i in range(25)],
                    "fair": fair_block(seed, nonce)}
        if action in ("reveal", "cashout"):
            try:
                sid = int(data.get("session_id"))
            except Exception:
                raise MiniGameError("Missing session.")
            sess = mini_session(sid)
            if sess is None or int(sess["user_id"]) != uid or str(sess["status"]) != "active":
                raise MiniGameError("Session not active.", "session_gone")
            state = json.loads(sess["state"])
            bet = Decimal(str(sess["bet"]))
            bombs = set(state["bombs"])
            if action == "reveal":
                try:
                    cell = int(data.get("cell"))
                except Exception:
                    raise MiniGameError("Missing cell.")
                if cell in state["revealed"]:
                    raise MiniGameError("Already revealed.")
                if cell in bombs:
                    state["revealed"].append(cell)
                    mini_session_update(sid, status="lost", state=state)
                    result = {"won": False, "bomb_at": cell, "payout": 0, "bet": float(bet),
                              "revealed": list(state["revealed"])}
                    mini_history_insert(uid, "mines", bet, Decimal("0"), "lost", sess["seed"], int(sess["nonce"]), result)
                    MINI_SESSIONS.pop(sid, None)
                    return {**result, "fair": fair_block(sess["seed"], int(sess["nonce"]))}
                state["revealed"].append(cell)
                wins_available = 25 - int(state["mines_count"])
                if len(state["revealed"]) >= wins_available:
                    mult = mines_mult(int(state["mines_count"]), len(state["revealed"]))
                    payout = quantize_money(bet * mult)
                    mini_session_update(sid, status="won", state=state)
                    mini_credit(uid, payout, "mines")
                    result = {"won": True, "cleared": True, "multiplier": float(mult), "payout": float(payout),
                              "bet": float(bet), "revealed": list(state["revealed"])}
                    mini_history_insert(uid, "mines", bet, payout, "won", sess["seed"], int(sess["nonce"]), result)
                    MINI_SESSIONS.pop(sid, None)
                    return {**result, "fair": fair_block(sess["seed"], int(sess["nonce"]))}
                mini_session_update(sid, state=state)
                mult = mines_mult(int(state["mines_count"]), len(state["revealed"]))
                return {"ok": True, "won": None, "cell": cell, "revealed": list(state["revealed"]),
                        "multiplier": float(mult), "potential_payout": float(quantize_money(bet * mult)),
                        "bet": float(bet), "fair": fair_block(sess["seed"], int(sess["nonce"]))}
            # cashout
            if not state["revealed"]:
                raise MiniGameError("Reveal at least one gem first.")
            mult = mines_mult(int(state["mines_count"]), len(state["revealed"]))
            payout = quantize_money(bet * mult)
            mini_session_update(sid, status="won", state=state)
            mini_credit(uid, payout, "mines")
            result = {"won": True, "cleared": False, "multiplier": float(mult), "payout": float(payout),
                      "bet": float(bet), "revealed": list(state["revealed"])}
            mini_history_insert(uid, "mines", bet, payout, "won", sess["seed"], int(sess["nonce"]), result)
            MINI_SESSIONS.pop(sid, None)
            return {**result, "fair": fair_block(sess["seed"], int(sess["nonce"]))}
        raise MiniGameError("Unknown action.")

    if game == "towers":
        if action == "new":
            bet = _parse_bet(data)
            diff = str(data.get("difficulty", "easy")).lower()
            if diff not in TOWER_DIFFICULTY:
                raise MiniGameError("Difficulty must be easy, medium or hard.")
            bad = TOWER_DIFFICULTY[diff]
            seed, nonce = new_seed(), 0
            layout = towers_layout(seed, nonce, bad)
            mini_debit(uid, bet, "towers")
            state = {"bet": float(bet), "bad_per_row": bad, "layout": layout, "row": 0}
            sid = mini_session_insert(uid, "towers", bet, seed, nonce, state)
            MINI_SESSIONS[sid] = state
            return {"ok": True, "session_id": sid, "difficulty": diff, "fair": fair_block(seed, nonce)}
        if action in ("pick", "cashout"):
            try:
                sid = int(data.get("session_id"))
            except Exception:
                raise MiniGameError("Missing session.")
            sess = mini_session(sid)
            if sess is None or int(sess["user_id"]) != uid or str(sess["status"]) != "active":
                raise MiniGameError("Session not active.", "session_gone")
            state = json.loads(sess["state"])
            bet = Decimal(str(sess["bet"]))
            bad = int(state["bad_per_row"])
            if action == "pick":
                try:
                    col = int(data.get("col"))
                except Exception:
                    raise MiniGameError("Missing column.")
                if not 0 <= col <= 2:
                    raise MiniGameError("Column must be 0-2.")
                row = int(state["row"])
                if col in state["layout"][row]:
                    mini_session_update(sid, status="lost", state=state)
                    result = {"won": False, "payout": 0, "bet": float(bet), "row": row, "col": col}
                    mini_history_insert(uid, "towers", bet, Decimal("0"), "lost", sess["seed"], int(sess["nonce"]), result)
                    MINI_SESSIONS.pop(sid, None)
                    return {**result, "fair": fair_block(sess["seed"], int(sess["nonce"]))}
                state["row"] = row + 1
                mini_session_update(sid, state=state)
                mult = towers_multiplier(row + 1, bad)
                if row + 1 >= 8:
                    payout = quantize_money(bet * mult)
                    mini_session_update(sid, status="won", state=state)
                    mini_credit(uid, payout, "towers")
                    result = {"won": True, "cleared": True, "multiplier": float(mult), "payout": float(payout),
                              "bet": float(bet), "row": 8}
                    mini_history_insert(uid, "towers", bet, payout, "won", sess["seed"], int(sess["nonce"]), result)
                    MINI_SESSIONS.pop(sid, None)
                    return {**result, "fair": fair_block(sess["seed"], int(sess["nonce"]))}
                return {"ok": True, "won": None, "row": row + 1, "col": col, "multiplier": float(mult),
                        "potential_payout": float(quantize_money(bet * mult)), "bet": float(bet),
                        "fair": fair_block(sess["seed"], int(sess["nonce"]))}
            if int(state["row"]) == 0:
                raise MiniGameError("Climb at least one row first.")
            mult = towers_multiplier(int(state["row"]), bad)
            payout = quantize_money(bet * mult)
            mini_session_update(sid, status="won", state=state)
            mini_credit(uid, payout, "towers")
            result = {"won": True, "cleared": False, "multiplier": float(mult), "payout": float(payout),
                      "bet": float(bet), "row": int(state["row"])}
            mini_history_insert(uid, "towers", bet, payout, "won", sess["seed"], int(sess["nonce"]), result)
            MINI_SESSIONS.pop(sid, None)
            return {**result, "fair": fair_block(sess["seed"], int(sess["nonce"]))}
        raise MiniGameError("Unknown action.")

    if game == "blackjack":
        if action == "new":
            bet = _parse_bet(data)
            seed, nonce = new_seed(), 0
            deck = fresh_deck(seed, nonce)
            player = [deck.pop(0), deck.pop(0)]
            dealer = [deck.pop(0), deck.pop(0)]
            mini_debit(uid, bet, "blackjack")
            state = {"deck": deck, "player": player, "dealer": dealer, "bet": float(bet), "doubled": False}
            sid = mini_session_insert(uid, "blackjack", bet, seed, nonce, state)
            MINI_SESSIONS[sid] = state
            pv, _ = bj_value(player)
            if pv == 21:
                return _bj_settle(sid, uid)
            return {"ok": True, "session_id": sid,
                    "player": [card_label(c) for c in player], "dealer": [card_label(dealer[0]), "?"],
                    "player_value": pv, "fair": fair_block(seed, nonce)}
        if action in ("hit", "stand", "double"):
            try:
                sid = int(data.get("session_id"))
            except Exception:
                raise MiniGameError("Missing session.")
            sess = mini_session(sid)
            if sess is None or int(sess["user_id"]) != uid or str(sess["status"]) != "active":
                raise MiniGameError("Session not active.", "session_gone")
            state = json.loads(sess["state"])
            bet = Decimal(str(sess["bet"]))
            seed, nonce = sess["seed"], int(sess["nonce"])
            if action == "hit":
                deck = state["deck"]
                state["player"].append(deck.pop(0))
                state["deck"] = deck
                pv, _ = bj_value(state["player"])
                if pv > 21:
                    mini_session_update(sid, state=state)
                    return _bj_settle(sid, uid)
                mini_session_update(sid, state=state)
                return {"ok": True, "player": [card_label(c) for c in state["player"]],
                        "player_value": pv, "dealer": [card_label(state["dealer"][0]), "?"],
                        "fair": fair_block(seed, nonce)}
            if action == "double":
                if len(state["player"]) != 2 or state["doubled"]:
                    raise MiniGameError("Double only on your first two cards.")
                mini_debit(uid, bet, "blackjack")
                state["bet"] = float(quantize_money(bet * 2))
                state["doubled"] = True
                deck = state["deck"]
                state["player"].append(deck.pop(0))
                state["deck"] = deck
                mini_session_update(sid, state=state)
                return _bj_settle(sid, uid)
            mini_session_update(sid, state=state)
            return _bj_settle(sid, uid)
        raise MiniGameError("Unknown action.")

    if game == "hilo":
        if action == "new":
            bet = _parse_bet(data)
            seed, nonce = new_seed(), 0
            deck = fresh_deck(seed, nonce)
            current = deck.pop(0)
            mini_debit(uid, bet, "hilo")
            state = {"deck": deck, "current": current, "mult": 1.0, "bet": float(bet), "step": 0}
            sid = mini_session_insert(uid, "hilo", bet, seed, nonce, state)
            MINI_SESSIONS[sid] = state
            hi = hilo_mult(deck, current, "higher")
            lo = hilo_mult(deck, current, "lower")
            return {"ok": True, "session_id": sid, "card": card_label(current),
                    "higher_mult": float(hi), "lower_mult": float(lo), "cards_left": len(deck),
                    "fair": fair_block(seed, nonce)}
        if action in ("higher", "lower", "cashout"):
            try:
                sid = int(data.get("session_id"))
            except Exception:
                raise MiniGameError("Missing session.")
            sess = mini_session(sid)
            if sess is None or int(sess["user_id"]) != uid or str(sess["status"]) != "active":
                raise MiniGameError("Session not active.", "session_gone")
            state = json.loads(sess["state"])
            bet = Decimal(str(sess["bet"]))
            seed, nonce = sess["seed"], int(sess["nonce"])
            if action == "cashout":
                if int(state["step"]) == 0:
                    raise MiniGameError("Play at least one step first.")
                mult = Decimal(str(state["mult"]))
                payout = quantize_money(bet * mult)
                mini_session_update(sid, status="won", state=state)
                mini_credit(uid, payout, "hilo")
                result = {"won": True, "multiplier": float(mult), "payout": float(payout), "bet": float(bet),
                          "steps": int(state["step"])}
                mini_history_insert(uid, "hilo", bet, payout, "won", seed, nonce, result)
                MINI_SESSIONS.pop(sid, None)
                return {**result, "fair": fair_block(seed, nonce)}
            deck = state["deck"]
            current = state["current"]
            chosen = hilo_mult(deck, current, action)
            if chosen <= 0:
                raise MiniGameError("No winning cards left — cash out!")
            card = deck.pop(0)
            if (action == "higher" and card > current) or (action == "lower" and card < current):
                state["current"] = card
                state["step"] += 1
                state["mult"] = float(quantize_money(Decimal(str(state["mult"])) * chosen))
                state["deck"] = deck
                if not deck:
                    mult = Decimal(str(state["mult"]))
                    payout = quantize_money(bet * mult)
                    mini_session_update(sid, status="won", state=state)
                    mini_credit(uid, payout, "hilo")
                    result = {"won": True, "deck_cleared": True, "multiplier": float(mult),
                              "payout": float(payout), "bet": float(bet), "steps": int(state["step"])}
                    mini_history_insert(uid, "hilo", bet, payout, "won", seed, nonce, result)
                    MINI_SESSIONS.pop(sid, None)
                    return {**result, "fair": fair_block(seed, nonce)}
                mini_session_update(sid, state=state)
                hi = hilo_mult(deck, card, "higher")
                lo = hilo_mult(deck, card, "lower")
                return {"ok": True, "won": None, "card": card_label(card), "drawn": card_label(card),
                        "higher_mult": float(hi), "lower_mult": float(lo), "multiplier": float(state["mult"]),
                        "potential_payout": float(quantize_money(bet * Decimal(str(state["mult"])))),
                        "cards_left": len(deck), "fair": fair_block(seed, nonce)}
            mini_session_update(sid, status="lost", state=state)
            result = {"won": False, "payout": 0, "bet": float(bet), "drawn": card_label(card),
                      "had": card_label(current), "tie": card == current}
            mini_history_insert(uid, "hilo", bet, Decimal("0"), "lost", seed, nonce, result)
            MINI_SESSIONS.pop(sid, None)
            return {**result, "fair": fair_block(seed, nonce)}
        raise MiniGameError("Unknown action.")

    if game == "roulette":
        if action != "play":
            raise MiniGameError("Unknown action.")
        bet = _parse_bet(data)
        choice = str(data.get("choice", "")).strip().lower()
        number = None
        if choice.isdigit():
            number = int(choice)
            if not 0 <= number <= 36:
                raise MiniGameError("Number must be 0-36.")
            choice = "number"
        if choice not in CB._ROULETTE_MULTIPLIERS:
            raise MiniGameError("Bad roulette choice.")
        seed, nonce = new_seed(), 0
        spin = roulette_spin(seed, nonce)
        won = spin == number if choice == "number" else roulette_payout(choice, spin) > 0
        payout = quantize_money(bet * Decimal("36")) if (choice == "number" and won) else (
            quantize_money(bet * roulette_payout(choice, spin)) if won else Decimal("0"))
        mini_debit(uid, bet, "roulette")
        if payout > 0:
            mini_credit(uid, payout, "roulette")
        result = {"spin": spin, "color": CB._roulette_color(spin), "choice": choice,
                  "won": won, "payout": float(payout), "bet": float(bet)}
        mini_history_insert(uid, "roulette", bet, payout, "won" if won else "lost", seed, nonce, result)
        return {**result, "fair": fair_block(seed, nonce)}

    if game == "coinflip":
        if action != "play":
            raise MiniGameError("Unknown action.")
        bet = _parse_bet(data)
        side = str(data.get("side", "")).lower()
        if side not in ("heads", "tails"):
            raise MiniGameError("Side must be heads or tails.")
        seed, nonce = new_seed(), 0
        landed = "heads" if p_outcome(seed, nonce, "coin") < 0.5 else "tails"
        won = landed == side
        payout = quantize_money(bet * Decimal("1.94")) if won else Decimal("0")
        mini_debit(uid, bet, "coinflip")
        if payout > 0:
            mini_credit(uid, payout, "coinflip")
        result = {"landed": landed, "side": side, "won": won, "payout": float(payout), "bet": float(bet)}
        mini_history_insert(uid, "coinflip", bet, payout, "won" if won else "lost", seed, nonce, result)
        return {**result, "fair": fair_block(seed, nonce)}

    if game == "slots":
        if action != "play":
            raise MiniGameError("Unknown action.")
        bet = _parse_bet(data)
        seed, nonce = new_seed(), 0
        reel, mult = slots_spin(seed, nonce)
        payout = quantize_money(bet * mult) if mult > 0 else Decimal("0")
        mini_debit(uid, bet, "slots")
        if payout > 0:
            mini_credit(uid, payout, "slots")
        result = {"reel": reel, "multiplier": float(mult), "won": payout > 0,
                  "payout": float(payout), "bet": float(bet)}
        mini_history_insert(uid, "slots", bet, payout, "won" if payout > 0 else "lost", seed, nonce, result)
        return {**result, "fair": fair_block(seed, nonce)}

    if game == "plinko":
        if action != "play":
            raise MiniGameError("Unknown action.")
        bet = _parse_bet(data)
        risk = str(data.get("risk", "low")).lower()
        if risk not in PLINKO_TABLES:
            raise MiniGameError("Risk must be low, medium or high.")
        seed, nonce = new_seed(), 0
        bucket = plinko_bucket(seed, nonce)
        mult = PLINKO_TABLES[risk][bucket]
        payout = quantize_money(bet * mult) if mult > 0 else Decimal("0")
        mini_debit(uid, bet, "plinko")
        if payout > 0:
            mini_credit(uid, payout, "plinko")
        result = {"bucket": bucket, "risk": risk, "multiplier": float(mult), "won": payout > 0,
                  "payout": float(payout), "bet": float(bet)}
        mini_history_insert(uid, "plinko", bet, payout, "won" if payout > 0 else "lost", seed, nonce, result)
        return {**result, "fair": fair_block(seed, nonce)}

    if game == "keno":
        if action != "play":
            raise MiniGameError("Unknown action.")
        bet = _parse_bet(data)
        try:
            picks = sorted({int(p) for p in (data.get("picks") or [])})
        except Exception:
            picks = []
        if not 1 <= len(picks) <= 10 or any(not 1 <= p <= 80 for p in picks):
            raise MiniGameError("Pick 1-10 unique numbers between 1 and 80.")
        seed, nonce = new_seed(), 0
        drawn = keno_draw(seed, nonce)
        hits = sorted(set(picks) & set(drawn))
        mult = keno_multiplier(len(picks), len(hits))
        payout = quantize_money(bet * mult) if mult > 0 else Decimal("0")
        mini_debit(uid, bet, "keno")
        if payout > 0:
            mini_credit(uid, payout, "keno")
        result = {"picks": picks, "drawn": drawn, "hits": hits, "multiplier": float(mult),
                  "won": payout > 0, "payout": float(payout), "bet": float(bet)}
        mini_history_insert(uid, "keno", bet, payout, "won" if payout > 0 else "lost", seed, nonce, result)
        return {**result, "fair": fair_block(seed, nonce)}

    if game == "wheel":
        if action != "play":
            raise MiniGameError("Unknown action.")
        bet = _parse_bet(data)
        seed, nonce = new_seed(), 0
        idx = wheel_spin(seed, nonce)
        mult = WHEEL_MULTIPLIERS[idx]
        payout = quantize_money(bet * mult) if mult > 0 else Decimal("0")
        mini_debit(uid, bet, "wheel")
        if payout > 0:
            mini_credit(uid, payout, "wheel")
        result = {"segment": idx, "multiplier": float(mult), "won": payout > 0,
                  "payout": float(payout), "bet": float(bet)}
        mini_history_insert(uid, "wheel", bet, payout, "won" if payout > 0 else "lost", seed, nonce, result)
        return {**result, "fair": fair_block(seed, nonce)}

    if game == "limbo":
        if action != "play":
            raise MiniGameError("Unknown action.")
        bet = _parse_bet(data)
        try:
            target = quantize_money(str(data.get("target", "2")))
        except Exception:
            raise MiniGameError("Invalid target.")
        if not Decimal("1.01") <= target <= Decimal("100000"):
            raise MiniGameError("Target must be 1.01 - 100000.")
        seed, nonce = new_seed(), 0
        mult = limbo_multiplier(target)
        p = float((Decimal("0.97") / mult))
        roll = p_outcome(seed, nonce, "limbo")
        won = roll >= p
        payout = quantize_money(bet * mult) if won else Decimal("0")
        mini_debit(uid, bet, "limbo")
        if payout > 0:
            mini_credit(uid, payout, "limbo")
        result = {"target": float(target), "multiplier": float(mult), "won": won,
                  "payout": float(payout), "bet": float(bet)}
        mini_history_insert(uid, "limbo", bet, payout, "won" if won else "lost", seed, nonce, result)
        return {**result, "fair": fair_block(seed, nonce)}

    if game == "baccarat":
        if action != "play":
            raise MiniGameError("Unknown action.")
        bet = _parse_bet(data)
        side = str(data.get("side", "")).lower()
        if side not in BAC_MULTIPLIERS:
            raise MiniGameError("Side must be player, banker or tie.")
        seed, nonce = new_seed(), 0
        round_ = baccarat_round(seed, nonce)
        won = round_["winner"] == side
        mult = BAC_MULTIPLIERS[side]
        payout = quantize_money(bet * mult) if won else Decimal("0")
        mini_debit(uid, bet, "baccarat")
        if payout > 0:
            mini_credit(uid, payout, "baccarat")
        result = {"winner": round_["winner"], "player_cards": [card_label(c) for c in round_["player"]],
                  "banker_cards": [card_label(c) for c in round_["banker"]],
                  "player_value": round_["pv"], "banker_value": round_["bv"],
                  "side": side, "won": won, "payout": float(payout), "bet": float(bet)}
        mini_history_insert(uid, "baccarat", bet, payout, "won" if won else "lost", seed, nonce, result)
        return {**result, "fair": fair_block(seed, nonce)}

    raise MiniGameError(f"Unknown game: {game}")


def _bj_settle(sid: int, uid: int) -> Dict[str, Any]:
    sess = mini_session(sid)
    if sess is None or int(sess["user_id"]) != uid or str(sess["status"]) != "active":
        raise MiniGameError("Session not active.", "session_gone")
    state = json.loads(sess["state"])
    bet = Decimal(str(sess["bet"]))
    seed, nonce = sess["seed"], int(sess["nonce"])
    deck = state["deck"]
    dealer = state["dealer"]
    dv, _ = bj_value(dealer)
    while dv < 17 and deck:
        dealer.append(deck.pop(0))
        dv, _ = bj_value(dealer)
    state["dealer"] = dealer
    state["deck"] = deck
    pv, _ = bj_value(state["player"])
    is_natural = len(state["player"]) == 2 and pv == 21
    if pv > 21:
        payout, status = Decimal("0"), "lost"
    elif dv > 21:
        payout, status = quantize_money(bet * (Decimal("2.5") if is_natural else Decimal("2"))), "won"
    elif pv > dv:
        payout, status = quantize_money(bet * (Decimal("2.5") if is_natural else Decimal("2"))), "won"
    elif pv == dv:
        payout, status = bet, "push"
    else:
        payout, status = Decimal("0"), "lost"
    mini_session_update(sid, status="won" if payout > 0 else "lost", state=state)
    if payout > 0:
        mini_credit(uid, payout, "blackjack")
    result = {"player_cards": [card_label(c) for c in state["player"]],
              "dealer_cards": [card_label(c) for c in dealer],
              "player_value": pv, "dealer_value": dv,
              "won": payout > 0, "push": status == "push", "natural": is_natural,
              "payout": float(payout), "bet": float(bet)}
    mini_history_insert(uid, "blackjack", bet, payout, "won" if payout > 0 else "lost", seed, nonce, result)
    MINI_SESSIONS.pop(sid, None)
    return {**result, "fair": fair_block(seed, nonce)}


# ---------------------------------------------------------------------------
# Session cleaner (mirrors the bot's, guarded against double refunds)
# ---------------------------------------------------------------------------

async def mini_cleanup_loop() -> None:
    def _stale() -> List[int]:
        conn = CB._solo_conn()
        try:
            CB._solo_ensure_tables(conn)
            rows = conn.execute(
                "SELECT id FROM solo_sessions WHERE status = 'active' AND created_at < ?",
                (crypto_utc_string(datetime.now(timezone.utc) - timedelta(minutes=10)),),
            ).fetchall()
            return [int(r["id"]) for r in rows]
        finally:
            conn.close()

    while True:
        try:
            ids = await db_call(_stale)
            for sid in ids:
                if sid in MINI_SESSIONS:
                    continue
                await db_call(CB.solo_try_expire, sid)
        except Exception:
            LOGGER.exception("Mini App cleanup loop error")
        await asyncio.sleep(90)


def crypto_utc_string(value: Optional[datetime] = None) -> str:
    value = value or datetime.now(timezone.utc)
    return value.strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

app = FastAPI(title="Casino Royals Mini App", docs_url=None, redoc_url=None)

GAME_META = [
    {"id": "dice", "name": "Dice", "mono": "D", "tag": "Instant"},
    {"id": "crash", "name": "Crash", "mono": "C", "tag": "Live"},
    {"id": "mines", "name": "Mines", "mono": "M", "tag": "Skill"},
    {"id": "towers", "name": "Towers", "mono": "T", "tag": "Skill"},
    {"id": "blackjack", "name": "Blackjack", "mono": "BJ", "tag": "Cards"},
    {"id": "baccarat", "name": "Baccarat", "mono": "BA", "tag": "Cards"},
    {"id": "roulette", "name": "Roulette", "mono": "R", "tag": "Classic"},
    {"id": "hilo", "name": "Hi-Lo", "mono": "HL", "tag": "Cards"},
    {"id": "plinko", "name": "Plinko", "mono": "P", "tag": "Instant"},
    {"id": "keno", "name": "Keno", "mono": "K", "tag": "Instant"},
    {"id": "wheel", "name": "Wheel of Fortune", "mono": "W", "tag": "Instant"},
    {"id": "limbo", "name": "Limbo", "mono": "L", "tag": "Instant"},
    {"id": "coinflip", "name": "Coin Flip", "mono": "CF", "tag": "Instant"},
    {"id": "slots", "name": "Slots", "mono": "S", "tag": "Classic"},
]

_bot_username: Optional[str] = None


async def _fetch_bot_username() -> None:
    global _bot_username
    if not BOT_TOKEN:
        return
    try:
        import urllib.request

        with urllib.request.urlopen(
            f"https://api.telegram.org/bot{BOT_TOKEN}/getMe", timeout=10
        ) as resp:
            payload = json.loads(resp.read().decode())
            if payload.get("ok"):
                _bot_username = str(payload["result"].get("username") or "")
    except Exception:
        LOGGER.debug("Could not fetch bot username")


@app.on_event("startup")
async def _startup() -> None:
    await _fetch_bot_username()
    asyncio.get_event_loop().create_task(mini_cleanup_loop())


@app.get("/", response_class=HTMLResponse)
async def index():
    # Serves static/index.html when present (local/dev), otherwise the
    # embedded copy baked into this file, so a hosting panel that only
    # accepts miniapp.py works without any extra files.
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return HTMLResponse(EMBEDDED_INDEX_HTML)


@app.get("/api/config")
@app.post("/api/config")
async def api_config() -> JSONResponse:
    limits = await db_call(mini_limits)
    return JSONResponse({
        "appName": APP_NAME,
        "currency": CURRENCY,
        "demoMode": DEMO_MODE,
        "minBet": limits["min"],
        "maxBet": limits["max"],
        "games": GAME_META,
        "botUsername": _bot_username,
    })


def _user_overview(uid: int) -> Dict[str, Any]:
    info = CB.solo_balance(uid)
    def _stats() -> Dict[str, Any]:
        conn = CB._solo_conn()
        try:
            CB._solo_ensure_tables(conn)
            row = conn.execute(
                "SELECT COUNT(*) AS games, COALESCE(SUM(bet),0) AS wagered, COALESCE(SUM(payout),0) AS paid, "
                "SUM(CASE WHEN status='won' THEN 1 ELSE 0 END) AS wins, "
                "SUM(CASE WHEN status='lost' THEN 1 ELSE 0 END) AS losses "
                "FROM solo_history WHERE user_id = ?",
                (uid,),
            ).fetchone()
            hist = conn.execute(
                "SELECT game, bet, payout, status, created_at FROM solo_history WHERE user_id = ? "
                "ORDER BY id DESC LIMIT 20",
                (uid,),
            ).fetchall()
            return {"stats": dict(row), "history": [dict(h) for h in hist]}
        finally:
            conn.close()

    data = _stats()
    return {
        "balance": info["balance"],
        "held": info["held"],
        "available": info["available"],
        "stats": data["stats"],
        "history": data["history"],
    }


@app.post("/api/init")
async def api_init(request: Request) -> JSONResponse:
    body = await request.json()
    payload = validate_init_data(str(body.get("initData") or ""))
    if payload is None:
        return JSONResponse({"ok": False, "error": "Invalid Telegram data."}, status_code=401)
    user = user_from_payload(payload)
    await db_call(CB.DB.ensure_user, user["id"], user["username"], user["name"])
    overview = await db_call(_user_overview, user["id"])
    def _leaders() -> List[Dict[str, Any]]:
        conn = CB._solo_conn()
        try:
            rows = conn.execute(
                "SELECT user_id, first_name, username, balance FROM users "
                "WHERE user_id != ? AND balance > 0 ORDER BY balance DESC LIMIT 10",
                (CB.SOLO_HOUSE_ID,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    leaders = await db_call(_leaders)
    return JSONResponse({"ok": True, "user": user, **overview, "leaderboard": leaders})


@app.post("/api/play")
async def api_play(request: Request) -> JSONResponse:
    body = await request.json()
    payload = validate_init_data(str(body.get("initData") or ""))
    if payload is None:
        return JSONResponse({"ok": False, "error": "Invalid Telegram data."}, status_code=401)
    user = user_from_payload(payload)
    await db_call(CB.DB.ensure_user, user["id"], user["username"], user["name"])
    game = str(body.get("game") or "")
    action = str(body.get("action") or "play")
    data = body.get("data") or {}

    def _run() -> Dict[str, Any]:
        try:
            result = resolve_game(user["id"], game, action, data)
        except MiniGameError as exc:
            return {"ok": False, "error": exc.message, "code": exc.code}
        except InsufficientBalance as exc:
            return {"ok": False, "error": str(exc), "code": "insufficient_balance"}
        except GameError as exc:
            return {"ok": False, "error": str(exc), "code": "game_error"}
        overview = _user_overview(user["id"])
        return {"ok": True, "result": result, "balance": overview["balance"],
                "available": overview["available"]}

    out = await db_call(_run)
    status = 200 if out.get("ok") else 400
    return JSONResponse(out, status_code=status)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
