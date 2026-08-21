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
    from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, RedirectResponse
    from fastapi.staticfiles import StaticFiles
except ImportError:  # pragma: no cover
    print("Installing fastapi + uvicorn...", flush=True)
    import subprocess

    subprocess.run([sys.executable, "-m", "pip", "install", "fastapi", "uvicorn"], check=True)
    from fastapi import FastAPI, Request
    from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, RedirectResponse
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
EMBEDDED_INDEX_HTML = "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n<meta charset=\"UTF-8\">\n<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no\">\n<title>Casino Royals</title>\n<style>\n:root{\n  --bg:#eef4ff; --bg2:#dce9ff; --ink:#0f172a; --muted:#5b6b8c;\n  --blue:#2563eb; --blue2:#3b82f6; --cyan:#06b6d4; --gold:#f59e0b; --gold2:#fbbf24;\n  --card:rgba(255,255,255,.82); --line:rgba(59,130,246,.22);\n  --glow:0 0 24px rgba(59,130,246,.38); --glowS:0 0 12px rgba(59,130,246,.25);\n  --grad:linear-gradient(135deg,#2563eb,#06b6d4);\n  --serif:Georgia,'Times New Roman',serif;\n  --sans:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;\n  --r:18px;\n}\n*{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent}\nhtml,body{height:100%}\nbody{\n  font-family:var(--sans);\n  background:linear-gradient(160deg,#f6faff,#dce9ff 55%,#cfe0ff) fixed;\n  color:var(--ink); overflow-x:hidden;\n}\n.orb{position:fixed;border-radius:50%;filter:blur(64px);opacity:.55;pointer-events:none;z-index:0;animation:float 13s ease-in-out infinite}\n.orb1{width:360px;height:360px;background:radial-gradient(circle,#7ab3ff,transparent 70%);top:-100px;left:-90px}\n.orb2{width:320px;height:320px;background:radial-gradient(circle,#4dd7ee,transparent 70%);bottom:-80px;right:-80px;animation-delay:-6s}\n.orb3{width:260px;height:260px;background:radial-gradient(circle,#b9a0ff,transparent 70%);top:40%;left:60%;animation-delay:-3s}\n@keyframes float{0%,100%{transform:translateY(0) scale(1)}50%{transform:translateY(26px) scale(1.06)}}\n#app{position:relative;z-index:1;max-width:560px;margin:0 auto;padding:14px 16px 48px}\n\n/* ============================ INTRO ANIMATION ============================ */\n#intro{position:fixed;inset:0;z-index:99;display:flex;align-items:center;justify-content:center;flex-direction:column;\n  background:radial-gradient(900px 600px at 50% 38%,#1e3a8a 0%,#0b1e4b 55%,#060f2b 100%);\n  transition:opacity .6s ease,transform .6s ease;overflow:hidden}\n#intro.gone{opacity:0;transform:translateY(-100%);pointer-events:none}\n#intro .beam{position:absolute;top:0;bottom:0;width:130px;left:-140px;transform:skewX(-18deg);\n  background:linear-gradient(90deg,transparent,rgba(96,165,250,.32),transparent);animation:beamMove 1.6s ease-in-out infinite}\n@keyframes beamMove{0%{left:-140px}100%{left:110%}}\n#intro .intro-crown{width:118px;height:118px;filter:drop-shadow(0 0 26px rgba(251,191,36,.75));animation:crownIn 1s cubic-bezier(.2,1.4,.4,1) backwards}\n@keyframes crownIn{from{transform:scale(.2) rotate(-14deg);opacity:0}to{transform:scale(1) rotate(0);opacity:1}}\n#intro .intro-title{margin-top:26px;font-family:var(--serif);font-size:34px;font-weight:700;letter-spacing:6px;color:#fff;display:flex}\n#intro .intro-title span{display:inline-block;animation:letterIn .7s cubic-bezier(.2,1.3,.4,1) backwards;text-shadow:0 0 18px rgba(125,170,255,.8)}\n#intro .intro-title span.gold{background:linear-gradient(180deg,#ffe9a8,#f59e0b 60%,#b45309);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}\n@keyframes letterIn{from{transform:translateY(30px) scale(.6);opacity:0}to{transform:none;opacity:1}}\n#intro .intro-sub{margin-top:14px;font-size:11px;letter-spacing:5px;color:#9db9ef;font-weight:700;animation:fadeUp .8s .9s backwards}\n#intro .intro-ring{margin-top:30px;width:150px;height:3px;border-radius:3px;overflow:hidden;background:rgba(255,255,255,.12)}\n#intro .intro-ring i{display:block;height:100%;width:40%;border-radius:3px;background:linear-gradient(90deg,#3b82f6,#22d3ee);\n  animation:ringLoad 1.4s ease forwards}\n@keyframes ringLoad{from{width:4%}to{width:100%}}\n#intro .intro-hint{position:absolute;bottom:34px;font-size:10.5px;letter-spacing:2px;color:rgba(157,185,239,.65);font-weight:700;animation:fadeUp 1s 1.2s backwards}\n@keyframes fadeUp{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}\n\n/* ============================ HEADER ============================ */\nheader{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:6px 2px 18px}\n.brand{display:flex;align-items:center;gap:12px}\n.brand svg{filter:drop-shadow(0 2px 8px rgba(245,158,11,.45));animation:crownGlow 2.8s ease-in-out infinite}\n@keyframes crownGlow{0%,100%{filter:drop-shadow(0 0 2px rgba(245,158,11,.3))}50%{filter:drop-shadow(0 0 12px rgba(245,158,11,.85))}}\n.brand h1{font-family:var(--serif);font-size:24px;font-weight:800;letter-spacing:1.2px;\n  background:linear-gradient(135deg,#1d4ed8,#06b6d4);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}\n.brand small{display:block;font-size:9.5px;color:var(--muted);font-weight:800;letter-spacing:3.4px;-webkit-text-fill-color:var(--muted)}\n.head-right{display:flex;align-items:center;gap:8px}\n.chip{background:var(--card);backdrop-filter:blur(16px);border:1px solid var(--line);border-radius:14px;padding:9px 16px;\n  box-shadow:var(--glowS);text-align:right}\n.chip span{display:block;font-size:8.5px;letter-spacing:2.4px;color:var(--muted);font-weight:800}\n.chip b{font-size:19px;color:var(--blue);font-weight:800}\n.chip b.pulse{animation:balPulse .45s ease}\n@keyframes balPulse{0%{transform:scale(1)}35%{transform:scale(1.16);color:var(--cyan)}100%{transform:scale(1)}}\n.icon-btn{width:42px;height:42px;border-radius:13px;border:1px solid var(--line);background:var(--card);backdrop-filter:blur(16px);\n  display:flex;align-items:center;justify-content:center;cursor:pointer;box-shadow:var(--glowS);transition:.2s}\n.icon-btn:hover{box-shadow:var(--glow)}\n\n/* ============================ BANNER / TABS ============================ */\n.banner{display:none;margin:0 0 12px;padding:11px 14px;border-radius:12px;font-size:12px;font-weight:600;line-height:1.5;border:1px solid}\n.banner.demo{display:block;border-color:rgba(245,158,11,.4);background:rgba(255,247,224,.85);color:#8a5a06}\n.banner.err{display:block;border-color:rgba(239,68,68,.4);background:rgba(254,242,242,.9);color:#b91c1c}\nnav.tabs{display:flex;gap:5px;background:var(--card);backdrop-filter:blur(16px);border:1px solid var(--line);border-radius:16px;\n  padding:5px;margin-bottom:18px;box-shadow:0 8px 24px rgba(37,99,235,.1)}\nnav.tabs button{flex:1;border:none;background:transparent;padding:11px 4px;border-radius:12px;\n  font-size:12.5px;font-weight:800;letter-spacing:.5px;color:var(--muted);cursor:pointer;transition:.25s}\nnav.tabs button.on{background:var(--grad);color:#fff;box-shadow:0 4px 16px rgba(37,99,235,.45)}\n\n/* ============================ SECTIONS / TILES ============================ */\n.sec-title{display:flex;align-items:center;gap:10px;font-size:15.5px;font-weight:800;margin:4px 2px 14px;color:var(--ink)}\n.sec-title .bar{width:5px;height:20px;border-radius:5px;background:var(--grad);box-shadow:0 0 12px rgba(59,130,246,.6)}\n.sec-title .rule{flex:1;height:1px;background:linear-gradient(90deg,var(--line),transparent)}\n.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}\n.tile{position:relative;background:var(--card);backdrop-filter:blur(16px);border:1px solid var(--line);border-radius:var(--r);\n  padding:20px 14px 16px;cursor:pointer;overflow:hidden;transition:.28s;animation:tileIn .45s ease backwards;box-shadow:0 6px 18px rgba(37,99,235,.07)}\n.tile:nth-child(1){animation-delay:.03s}.tile:nth-child(2){animation-delay:.06s}.tile:nth-child(3){animation-delay:.09s}\n.tile:nth-child(4){animation-delay:.12s}.tile:nth-child(5){animation-delay:.15s}.tile:nth-child(6){animation-delay:.18s}\n.tile:nth-child(7){animation-delay:.21s}.tile:nth-child(8){animation-delay:.24s}.tile:nth-child(9){animation-delay:.27s}\n.tile:nth-child(10){animation-delay:.3s}.tile:nth-child(11){animation-delay:.33s}.tile:nth-child(12){animation-delay:.36s}\n.tile:nth-child(13){animation-delay:.39s}.tile:nth-child(14){animation-delay:.42s}\n@keyframes tileIn{from{transform:translateY(18px) scale(.95)}to{transform:none}}\n.tile:hover{transform:translateY(-4px);border-color:rgba(59,130,246,.5);box-shadow:0 12px 30px rgba(37,99,235,.22)}\n.tile:active{transform:scale(.97)}\n.tile .icon-ring{width:58px;height:58px;border-radius:50%;margin:0 auto 12px;display:flex;align-items:center;justify-content:center;\n  background:linear-gradient(160deg,#ffffff,#e8f0ff);border:1px solid var(--line);box-shadow:0 0 0 5px rgba(59,130,246,.06),0 0 18px rgba(59,130,246,.22);\n  transition:.28s}\n.tile:hover .icon-ring{box-shadow:0 0 0 7px rgba(59,130,246,.1),0 0 28px rgba(59,130,246,.5);transform:scale(1.07) rotate(-4deg)}\n.tile .icon-ring svg{width:30px;height:30px;color:var(--blue)}\n.tile .nm{font-size:15px;font-weight:800;text-align:center;letter-spacing:.2px}\n.tile .tg{position:absolute;top:11px;right:11px;font-size:8px;font-weight:800;letter-spacing:1.8px;padding:4px 9px;border-radius:99px;\n  background:linear-gradient(135deg,rgba(37,99,235,.1),rgba(6,182,212,.12));color:var(--blue)}\n.tile::after{content:\"\";position:absolute;top:0;left:-80%;width:55%;height:100%;transform:skewX(-22deg);\n  background:linear-gradient(90deg,transparent,rgba(125,170,255,.28),transparent);transition:left .7s ease;pointer-events:none}\n.tile:hover::after{left:130%}\n\n/* ============================ PANEL ============================ */\n.panel{background:var(--card);backdrop-filter:blur(18px);border:1px solid var(--line);border-radius:24px;padding:20px;\n  box-shadow:0 18px 50px rgba(37,99,235,.16);animation:panelIn .3s ease}\n@keyframes panelIn{from{transform:translateY(20px) scale(.97);opacity:0}to{transform:none;opacity:1}}\n.panel-head{display:flex;align-items:center;gap:13px;margin-bottom:18px}\n.back-btn{width:44px;height:44px;border-radius:14px;border:1px solid var(--line);background:#fff;color:var(--blue);\n  font-size:19px;cursor:pointer;transition:.2s;font-family:var(--serif);box-shadow:var(--glowS)}\n.back-btn:hover{box-shadow:var(--glow)}\n.panel-head .icon-ring{width:50px;height:50px;border-radius:50%;display:flex;align-items:center;justify-content:center;flex-shrink:0;\n  background:linear-gradient(160deg,#fff,#e8f0ff);border:1px solid var(--line);box-shadow:0 0 16px rgba(59,130,246,.3)}\n.panel-head .icon-ring svg{width:26px;height:26px;color:var(--blue)}\n.panel-head h2{font-size:20px;font-weight:800;letter-spacing:.4px}\n.panel-head small{display:block;font-size:9px;color:var(--muted);font-weight:800;letter-spacing:2.2px;margin-top:3px}\n\n.bet-row{display:flex;align-items:center;gap:10px;margin-bottom:12px}\n.bet-row label{font-size:10px;letter-spacing:2px;color:var(--muted);font-weight:800}\n.bet-input{flex:1}\n.bet-input input{width:100%;padding:15px 16px;border-radius:14px;border:1.5px solid var(--line);background:#fff;\n  font-size:17px;font-weight:800;color:var(--ink);outline:none;transition:.2s}\n.bet-input input:focus{border-color:var(--blue2);box-shadow:0 0 0 4px rgba(59,130,246,.14),var(--glow)}\n.chips{display:flex;gap:7px;margin-bottom:16px}\n.chips button{flex:1;padding:11px 0;border-radius:12px;border:1px solid var(--line);background:#fff;color:var(--blue);\n  font-weight:800;font-size:12.5px;letter-spacing:.4px;cursor:pointer;transition:.18s}\n.chips button:active{background:var(--grad);color:#fff;box-shadow:var(--glow)}\n\n.ctrl-row{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px}\n.ctrl{flex:1;min-width:82px;padding:13px 8px;border-radius:13px;border:1.5px solid var(--line);background:#fff;\n  font-weight:800;font-size:13px;color:var(--muted);cursor:pointer;transition:.18s;text-align:center;letter-spacing:.3px}\n.ctrl.on{border-color:var(--blue2);color:var(--blue);background:linear-gradient(135deg,rgba(37,99,235,.09),rgba(6,182,212,.09));\n  box-shadow:var(--glow)}\n.payout-hint{font-size:13px;color:var(--muted);text-align:center;margin:2px 0 14px;font-weight:700}\n.payout-hint b{color:var(--blue)}\n\n.primary{width:100%;padding:19px;border:none;border-radius:16px;background:var(--grad);color:#fff;\n  font-size:17px;font-weight:800;letter-spacing:1.6px;cursor:pointer;box-shadow:0 8px 26px rgba(37,99,235,.45),0 0 22px rgba(6,182,212,.28);\n  transition:.22s;position:relative;overflow:hidden;text-transform:uppercase}\n.primary:hover{box-shadow:0 10px 32px rgba(37,99,235,.6),0 0 34px rgba(6,182,212,.45);transform:translateY(-1px)}\n.primary:active{transform:scale(.97)}\n.primary:disabled{opacity:.5;cursor:not-allowed;box-shadow:none}\n.primary::after{content:\"\";position:absolute;top:0;left:-80%;width:50%;height:100%;transform:skewX(-20deg);\n  background:linear-gradient(90deg,transparent,rgba(255,255,255,.4),transparent);transition:left .6s ease}\n.primary:hover::after{left:130%}\n.primary.alt{background:#fff;color:var(--blue);border:1.5px solid var(--line);box-shadow:var(--glowS)}\n.primary.alt:hover{box-shadow:var(--glow)}\n.hint-msg{display:none;margin-top:12px;padding:11px 13px;border-radius:11px;font-size:12.5px;font-weight:700;line-height:1.5;\n  border:1px solid rgba(239,68,68,.4);background:rgba(254,242,242,.92);color:#b91c1c}\n.hint-msg.show{display:block}\n\n/* result */\n.result{margin-top:16px;padding:18px;border-radius:16px;text-align:center;animation:pop .45s cubic-bezier(.2,1.4,.4,1)}\n@keyframes pop{from{transform:scale(.85);opacity:0}to{transform:none;opacity:1}}\n.result .lbl{font-size:10px;letter-spacing:3px;font-weight:800;color:var(--muted)}\n.result .big{font-size:32px;font-weight:900;margin:6px 0;letter-spacing:.5px}\n.result.win{border:1px solid rgba(59,130,246,.4);background:linear-gradient(135deg,rgba(37,99,235,.12),rgba(6,182,212,.06));box-shadow:0 0 26px rgba(59,130,246,.3)}\n.result.win .big{color:var(--blue)}\n.result.win .lbl{color:var(--cyan)}\n.result.lose{border:1px solid var(--line);background:rgba(241,245,255,.9)}\n.result.lose .big{color:var(--muted)}\n.result .sub{font-size:13px;color:var(--muted);font-weight:700}\n.result .sub b{color:var(--ink)}\n.fair{margin-top:14px;font-size:10.5px;color:var(--muted);text-align:center;word-break:break-all;line-height:1.6}\n.fair code{background:rgba(37,99,235,.07);border:1px solid var(--line);padding:2px 7px;border-radius:6px;color:var(--blue);font-weight:800}\n\n/* ============================ GAME BOARDS ============================ */\n.board{background:#fff;border:1px solid var(--line);border-radius:16px;padding:14px;margin-bottom:16px;box-shadow:inset 0 2px 10px rgba(37,99,235,.06)}\n.mines-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:7px;margin-bottom:16px}\n.mcell{aspect-ratio:1;border-radius:11px;border:1px solid rgba(59,130,246,.22);cursor:pointer;transition:.16s;\n  background:linear-gradient(160deg,#ffffff,#dce9ff);display:flex;align-items:center;justify-content:center;box-shadow:0 2px 8px rgba(37,99,235,.1)}\n.mcell:active{transform:scale(.88)}\n.mcell.rev{border-color:rgba(59,130,246,.6);background:#fff;box-shadow:0 0 16px rgba(59,130,246,.4)}\n.mcell .gem{width:46%;aspect-ratio:1;transform:rotate(45deg);border-radius:3px;\n  background:linear-gradient(135deg,#dbeafe,#3b82f6 55%,#1d4ed8);box-shadow:0 0 14px rgba(59,130,246,.7);animation:gemIn .35s cubic-bezier(.2,1.5,.4,1)}\n@keyframes gemIn{from{transform:rotate(45deg) scale(0)}to{transform:rotate(45deg) scale(1)}}\n.mcell .boom{width:54%;aspect-ratio:1;border-radius:50%;border:2px solid #334155;\n  background:radial-gradient(circle at 35% 30%,#64748b,#0f172a 70%)}\n.mcell.dead{border-color:rgba(239,68,68,.7);background:linear-gradient(160deg,#fee2e2,#fecaca);box-shadow:0 0 20px rgba(239,68,68,.6);animation:shake .45s}\n@keyframes shake{0%,100%{transform:translateX(0)}20%{transform:translateX(-5px)}40%{transform:translateX(5px)}60%{transform:translateX(-4px)}80%{transform:translateX(4px)}}\n\n/* crash arena */\n.crash-stage{position:relative;height:320px;border-radius:18px;border:1px solid var(--line);overflow:hidden;margin-bottom:16px;\n  background:linear-gradient(180deg,#8ec9ff 0%,#cfe5ff 55%,#e8f3ff 100%);box-shadow:inset 0 0 40px rgba(37,99,235,.15)}\n.crash-stage .cloud{position:absolute;background:rgba(255,255,255,.85);border-radius:99px;filter:blur(1px);animation:cloudDrift 22s linear infinite}\n@keyframes cloudDrift{from{transform:translateX(-160px)}to{transform:translateX(560px)}}\n.crash-stage canvas{position:absolute;inset:0;width:100%;height:100%}\n.crash-mult{position:absolute;top:14px;left:0;right:0;text-align:center;font-size:44px;font-weight:900;color:#fff;\n  text-shadow:0 0 18px rgba(37,99,235,.9),0 2px 6px rgba(0,0,0,.35);z-index:3;letter-spacing:.5px}\n.crash-bet{position:absolute;bottom:12px;left:14px;z-index:3;font-size:12px;font-weight:800;color:#1e3a8a;\n  background:rgba(255,255,255,.75);border-radius:9px;padding:6px 10px;backdrop-filter:blur(4px)}\n.crash-stage.boom{animation:stageShake .5s}\n@keyframes stageShake{0%,100%{transform:translate(0)}15%{transform:translate(-7px,3px)}35%{transform:translate(6px,-4px)}55%{transform:translate(-5px,2px)}75%{transform:translate(4px,-2px)}}\n\n/* cards */\n.cardzone{display:flex;justify-content:center;gap:10px;flex-wrap:wrap;margin:8px 0 16px;min-height:84px}\n.pcard{width:60px;height:84px;border-radius:10px;background:linear-gradient(160deg,#ffffff,#f1f6ff);border:1.5px solid rgba(59,130,246,.3);\n  display:flex;align-items:center;justify-content:center;font-family:var(--serif);font-size:26px;font-weight:700;color:#0f172a;\n  box-shadow:0 6px 16px rgba(37,99,235,.16);animation:dealIn .35s ease}\n@keyframes dealIn{from{transform:translateY(-18px) rotate(-7deg) scale(.8);opacity:0}to{transform:none;opacity:1}}\n.pcard.back{background:repeating-linear-gradient(45deg,#3b82f6 0 7px,#2563eb 7px 14px);border:1.5px solid #1d4ed8}\n.pcard.flip-in{animation:flipIn .45s ease}\n@keyframes flipIn{0%{transform:rotateY(90deg)}100%{transform:rotateY(0)}}\n.hand-label{font-size:9.5px;font-weight:800;letter-spacing:2.6px;color:var(--muted);text-align:center;margin:6px 0 3px}\n\n/* keno */\n.keno-grid{display:grid;grid-template-columns:repeat(10,1fr);gap:4px;margin-bottom:16px}\n.kcell{aspect-ratio:1;border-radius:7px;border:1px solid rgba(59,130,246,.22);background:#fff;font-family:var(--serif);\n  font-size:11px;font-weight:700;color:var(--muted);cursor:pointer;transition:.14s;display:flex;align-items:center;justify-content:center}\n.kcell.sel{background:var(--grad);color:#fff;border-color:transparent;box-shadow:var(--glowS);animation:kpop .2s}\n.kcell.hit{border-color:rgba(59,130,246,.6);color:var(--blue);background:linear-gradient(160deg,#fff,#dbeafe)}\n.kcell.both{background:linear-gradient(135deg,#fbbf24,#f59e0b);color:#fff;animation:kpop .4s}\n@keyframes kpop{0%{transform:scale(.4)}70%{transform:scale(1.15)}100%{transform:scale(1)}}\n\n/* plinko */\n.plinko-board{position:relative;height:300px;border-radius:16px;border:1px solid var(--line);background:linear-gradient(180deg,#fff,#eef4ff);\n  overflow:hidden;margin-bottom:16px;box-shadow:inset 0 2px 12px rgba(37,99,235,.07)}\n.ppeg{position:absolute;width:9px;height:9px;border-radius:50%;background:var(--grad);box-shadow:0 0 6px rgba(59,130,246,.6);transform:translate(-50%,-50%)}\n.pball{position:absolute;top:26px;left:50%;width:14px;height:14px;border-radius:50%;margin-left:-7px;\n  background:radial-gradient(circle at 35% 30%,#fde68a,#f59e0b 60%,#b45309);box-shadow:0 0 12px rgba(245,158,11,.9);z-index:2;transition:left .5s cubic-bezier(.4,.2,.5,1),top .5s cubic-bezier(.4,.2,.5,1)}\n.pbucket{position:absolute;bottom:0;height:36px;display:flex;align-items:center;justify-content:center;\n  font-size:9.5px;font-weight:800;color:var(--muted);border-top:1px solid var(--line);background:rgba(255,255,255,.8);letter-spacing:.4px}\n.pbucket.hit{background:linear-gradient(135deg,#fbbf24,#f59e0b);color:#fff;box-shadow:var(--glowS)}\n\n/* wheel */\n.wheel-wrap{position:relative;width:230px;height:230px;margin:4px auto 18px}\n.wheel-pointer{position:absolute;top:-10px;left:50%;transform:translateX(-50%);z-index:3;width:0;height:0;\n  border-left:10px solid transparent;border-right:10px solid transparent;border-top:16px solid var(--blue);filter:drop-shadow(0 2px 4px rgba(37,99,235,.5))}\n.wheel-svg{width:100%;height:100%;transition:transform 4.4s cubic-bezier(.15,.85,.25,1);filter:drop-shadow(0 10px 22px rgba(37,99,235,.35))}\n\n/* roulette */\n.roul-wheel{width:210px;height:210px;border-radius:50%;margin:6px auto 18px;position:relative;\n  box-shadow:0 0 0 7px #fff,0 0 0 9px rgba(59,130,246,.45),0 12px 30px rgba(37,99,235,.3)}\n.roul-wheel:before{content:\"\";position:absolute;inset:0;border-radius:50%;\n  background:conic-gradient(#dc2626 0 18deg,#111827 18deg 36deg,#dc2626 36deg 54deg,#111827 54deg 72deg,\n  #dc2626 72deg 90deg,#111827 90deg 108deg,#dc2626 108deg 126deg,#111827 126deg 144deg,\n  #dc2626 144deg 162deg,#111827 162deg 180deg,#dc2626 180deg 198deg,#111827 198deg 216deg,\n  #dc2626 216deg 234deg,#111827 234deg 252deg,#dc2626 252deg 270deg,#111827 270deg 288deg,\n  #dc2626 288deg 306deg,#111827 306deg 324deg,#16a34a 324deg 342deg,#111827 342deg 360deg)}\n.roul-wheel .ball{position:absolute;inset:0;transition:transform 4.2s cubic-bezier(.12,.8,.25,1);z-index:2}\n.roul-wheel .ball:before{content:\"\";position:absolute;top:7px;left:50%;transform:translateX(-50%);width:14px;height:14px;\n  border-radius:50%;background:radial-gradient(circle at 35% 30%,#fff,#93c5fd 45%,#2563eb);box-shadow:0 0 10px rgba(59,130,246,.9)}\n.roul-wheel .hub{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;z-index:3}\n.roul-wheel .hub span{width:56px;height:56px;border-radius:50%;border:1px solid rgba(59,130,246,.5);background:var(--grad);\n  display:flex;align-items:center;justify-content:center;font-weight:800;font-size:12px;color:#fff;letter-spacing:1px;box-shadow:var(--glow)}\n.num-pad{display:grid;grid-template-columns:repeat(6,1fr);gap:5px;margin-bottom:14px}\n.num-pad button{padding:10px 0;border-radius:8px;border:1px solid var(--line);background:#fff;font-weight:800;font-size:12px;color:var(--muted);cursor:pointer;transition:.15s}\n.num-pad button.on{background:var(--grad);color:#fff;border-color:transparent;box-shadow:var(--glowS)}\n\n/* coin */\n.coin-stage{display:flex;justify-content:center;margin:10px 0 18px;perspective:600px}\n.coin{width:110px;height:110px;border-radius:50%;border:3px solid #b45309;display:flex;align-items:center;justify-content:center;\n  font-family:var(--serif);font-weight:800;font-size:26px;color:#7c4a03;background:radial-gradient(circle at 35% 30%,#fef3c7,#f59e0b 60%,#b45309);\n  box-shadow:0 14px 30px rgba(180,83,9,.35),0 0 22px rgba(245,158,11,.45);transform-style:preserve-3d}\n.coin.flip{animation:coinFlip 1.5s ease-in-out}\n@keyframes coinFlip{0%{transform:rotateY(0)}50%{transform:rotateY(1080deg)}100%{transform:rotateY(2160deg)}}\n\n/* slots */\n.slots-row{display:flex;justify-content:center;gap:12px;margin-bottom:18px;padding:14px;\n  background:linear-gradient(160deg,#fff,#e4edff);border:1px solid var(--line);border-radius:16px;box-shadow:inset 0 2px 12px rgba(37,99,235,.08)}\n.sreel{width:86px;height:104px;border-radius:12px;border:2px solid rgba(59,130,246,.5);background:#fff;overflow:hidden;position:relative;\n  box-shadow:0 0 18px rgba(59,130,246,.3)}\n.sreel .strip{position:absolute;left:0;right:0;display:flex;flex-direction:column;align-items:center;transition:transform .7s cubic-bezier(.2,.8,.3,1)}\n.sreel .strip span{height:104px;display:flex;align-items:center;justify-content:center;font-family:var(--serif);font-size:44px;font-weight:800;color:var(--blue);text-shadow:0 0 16px rgba(59,130,246,.4)}\n.sreel.spinning .strip{animation:sroll .3s linear infinite}\n@keyframes sroll{from{transform:translateY(0)}to{transform:translateY(-416px)}}\n.sreel.win{animation:winGlow .6s ease 3}\n@keyframes winGlow{0%,100%{box-shadow:0 0 18px rgba(59,130,246,.3)}50%{box-shadow:0 0 40px rgba(245,158,11,.9);border-color:#f59e0b}}\n\n/* dice roll */\n.dice-stage{display:flex;justify-content:center;align-items:center;margin:6px 0 18px}\n.dice-num{width:120px;height:120px;border-radius:24px;border:2px solid rgba(59,130,246,.4);background:#fff;\n  display:flex;align-items:center;justify-content:center;font-size:52px;font-weight:900;color:var(--blue);\n  box-shadow:0 10px 26px rgba(37,99,235,.25),0 0 26px rgba(59,130,246,.3);transition:transform .2s}\n.dice-num.rolling{animation:diceShake .5s linear infinite}\n@keyframes diceShake{0%{transform:rotate(0) scale(1)}25%{transform:rotate(9deg) scale(1.06)}50%{transform:rotate(-9deg) scale(1.06)}75%{transform:rotate(6deg) scale(1.02)}100%{transform:rotate(0) scale(1)}}\n.dice-num.land{animation:landPop .5s cubic-bezier(.2,1.6,.4,1)}\n@keyframes landPop{0%{transform:scale(1.25)}100%{transform:scale(1)}}\n\n/* limbo */\n.limbo-beam{position:relative;height:260px;border-radius:16px;border:1px solid var(--line);overflow:hidden;margin-bottom:16px;\n  background:linear-gradient(180deg,#0b1e4b 0%,#1e3a8a 55%,#2563eb 100%);box-shadow:inset 0 0 40px rgba(0,0,0,.35)}\n.limbo-dot{position:absolute;left:50%;width:16px;height:16px;margin-left:-8px;border-radius:50%;\n  background:radial-gradient(circle at 35% 30%,#fff,#7ab3ff 50%,#2563eb);box-shadow:0 0 16px rgba(125,170,255,1);transition:bottom 1s cubic-bezier(.3,.5,.4,1)}\n.limbo-num{position:absolute;top:12px;left:0;right:0;text-align:center;font-size:36px;font-weight:900;color:#fff;text-shadow:0 0 20px rgba(125,170,255,.9)}\n\n/* limbo target */\n.limbo-target{display:flex;gap:8px;align-items:center;margin-bottom:14px}\n.limbo-target label{font-size:10px;letter-spacing:1.6px;color:var(--muted);font-weight:800}\n.limbo-target input{flex:1;padding:14px 15px;border-radius:13px;border:1.5px solid var(--line);font-size:16px;font-weight:800;outline:none}\n.limbo-target input:focus{border-color:var(--blue2);box-shadow:0 0 0 4px rgba(59,130,246,.14)}\n.limbo-target .val{min-width:60px;text-align:center;font-weight:800;color:var(--blue);border:1.5px solid var(--line);border-radius:13px;padding:14px 0;font-size:15px;background:#fff}\n.keno-status{font-size:11.5px;color:var(--muted);font-weight:800;letter-spacing:.5px;text-align:center;margin-bottom:10px}\n.range-row{display:flex;align-items:center;gap:10px;margin-bottom:14px}\n.range-row input[type=range]{flex:1;accent-color:var(--blue)}\n.range-row .val{min-width:56px;text-align:center;font-weight:800;color:var(--blue);border:1.5px solid var(--line);border-radius:11px;padding:9px 0;font-size:14px;background:#fff}\n\n/* ============================ LISTS ============================ */\n.list{display:flex;flex-direction:column;gap:10px}\n.row{display:flex;align-items:center;gap:12px;background:var(--card);backdrop-filter:blur(14px);border:1px solid var(--line);\n  border-radius:14px;padding:13px 15px;box-shadow:0 4px 14px rgba(37,99,235,.07)}\n.row .icon-ring{width:40px;height:40px;border-radius:50%;display:flex;align-items:center;justify-content:center;flex-shrink:0;\n  background:linear-gradient(160deg,#fff,#e8f0ff);border:1px solid var(--line);box-shadow:var(--glowS)}\n.row .icon-ring svg{width:21px;height:21px;color:var(--blue)}\n.row .grow{flex:1;min-width:0}\n.row .t1{font-weight:800;font-size:13.5px}\n.row .t2{font-size:10.5px;color:var(--muted);font-weight:700;margin-top:2px}\n.row .amt{font-weight:900;font-size:14px}\n.row .amt.pos{color:var(--blue)}.row .amt.neg{color:var(--muted)}\n.rank{width:30px;height:30px;border-radius:9px;display:flex;align-items:center;justify-content:center;\n  font-weight:900;font-size:13px;border:1px solid var(--line);color:var(--blue);background:#fff;flex-shrink:0}\n.rank.gold{background:linear-gradient(135deg,#fbbf24,#f59e0b);color:#fff;border-color:transparent;box-shadow:var(--glowS)}\n.empty{padding:38px 10px;text-align:center;color:var(--muted);font-weight:700;font-size:13px;line-height:1.7}\n.fair-card{background:var(--card);backdrop-filter:blur(14px);border:1px solid var(--line);border-radius:16px;padding:18px;margin-bottom:13px;box-shadow:0 4px 14px rgba(37,99,235,.07)}\n.fair-card h3{font-size:15px;font-weight:800;color:var(--blue);margin-bottom:8px;letter-spacing:.4px}\n.fair-card p{font-size:12.5px;color:var(--muted);line-height:1.7}\n.fair-card code{background:rgba(37,99,235,.07);border:1px solid var(--line);padding:1px 6px;border-radius:5px;color:var(--blue);font-weight:800}\n.wallet-actions{display:flex;gap:11px;margin-bottom:18px}\n.wallet-actions a,.wallet-actions button{flex:1;text-decoration:none;text-align:center;padding:16px;border-radius:14px;\n  font-weight:800;font-size:13px;letter-spacing:1.2px;border:none;cursor:pointer;text-transform:uppercase}\n.wa-dep{background:var(--grad);color:#fff;box-shadow:var(--glow)}\n.wa-wd{background:#fff;color:var(--blue);border:1.5px solid var(--line)!important;box-shadow:var(--glowS)}\n.stats-row{display:grid;grid-template-columns:1fr 1fr;gap:11px;margin-bottom:18px}\n.stat{background:var(--card);backdrop-filter:blur(14px);border:1px solid var(--line);border-radius:15px;padding:15px;text-align:center;box-shadow:0 4px 14px rgba(37,99,235,.07)}\n.stat b{display:block;font-size:20px;color:var(--blue);margin-bottom:4px;font-weight:900}\n.stat span{font-size:9px;color:var(--muted);font-weight:800;letter-spacing:2px}\n.view{display:none}\n.view.on{display:block;animation:viewIn .3s ease}\n@keyframes viewIn{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}\n\n/* toast */\n#toast{position:fixed;left:50%;bottom:24px;transform:translateX(-50%) translateY(80px);z-index:50;\n  background:#0f172a;color:#fff;padding:13px 22px;border-radius:14px;font-size:13px;font-weight:700;\n  box-shadow:0 10px 30px rgba(0,0,0,.4),0 0 20px rgba(59,130,246,.4);transition:transform .35s cubic-bezier(.2,1.2,.4,1);max-width:86%;text-align:center}\n#toast.show{transform:translateX(-50%) translateY(0)}\n</style>\n</head>\n<body>\n<div class=\"orb orb1\"></div><div class=\"orb orb2\"></div><div class=\"orb orb3\"></div>\n\n<!-- INTRO -->\n<div id=\"intro\">\n  <div class=\"beam\"></div>\n  <svg class=\"intro-crown\" viewBox=\"0 0 24 24\" width=\"118\" height=\"118\" fill=\"none\" stroke=\"#fbbf24\" stroke-width=\"1.4\" stroke-linejoin=\"round\">\n    <path d=\"M2.5 7.5L6 11l6-7 6 7 3.5-3.5L20 20H4L2.5 7.5z\" fill=\"url(#g1)\"/>\n    <rect x=\"3.4\" y=\"16.6\" width=\"17.2\" height=\"2.6\" rx=\"1.3\" fill=\"#f59e0b\"/>\n    <circle cx=\"12\" cy=\"8.4\" r=\"1.1\" fill=\"#fff\"/>\n    <defs><linearGradient id=\"g1\" x1=\"2\" y1=\"4\" x2=\"22\" y2=\"20\"><stop offset=\"0\" stop-color=\"#ffe9a8\"/><stop offset=\".55\" stop-color=\"#f59e0b\"/><stop offset=\"1\" stop-color=\"#b45309\"/></linearGradient></defs>\n  </svg>\n  <div class=\"intro-title\" id=\"introTitle\"></div>\n  <div class=\"intro-sub\">ROYAL TABLE GAMES</div>\n  <div class=\"intro-ring\"><i></i></div>\n  <div class=\"intro-hint\">TAP TO SKIP</div>\n</div>\n\n<div id=\"app\">\n  <header>\n    <div class=\"brand\">\n      <svg viewBox=\"0 0 24 24\" width=\"34\" height=\"34\" fill=\"none\" stroke=\"#f59e0b\" stroke-width=\"1.5\" stroke-linejoin=\"round\">\n        <path d=\"M2.5 7.5L6 11l6-7 6 7 3.5-3.5L20 20H4L2.5 7.5z\" fill=\"#fbbf24\"/>\n        <rect x=\"3.4\" y=\"16.6\" width=\"17.2\" height=\"2.6\" rx=\"1.3\" fill=\"#f59e0b\"/>\n      </svg>\n      <div>\n        <h1>CASINO ROYALS</h1>\n        <small>TABLE GAMES</small>\n      </div>\n    </div>\n    <div class=\"head-right\">\n      <div class=\"chip\"><span>BALANCE</span><b id=\"bal\">0</b></div>\n      <button class=\"icon-btn\" id=\"muteBtn\" onclick=\"toggleMute()\" aria-label=\"sound\"></button>\n    </div>\n  </header>\n\n  <div class=\"banner demo\" id=\"bannerDemo\">Preview mode - offline demo balance. Inside Telegram your balance is shared with the bot wallet.</div>\n  <div class=\"banner err\" id=\"bannerErr\" style=\"display:none\"></div>\n\n  <nav class=\"tabs\" id=\"tabs\">\n    <button data-view=\"games\" class=\"on\">Games</button>\n    <button data-view=\"wallet\">Wallet</button>\n    <button data-view=\"board\">Leaderboard</button>\n    <button data-view=\"fair\">Fairness</button>\n  </nav>\n\n  <div class=\"view on\" id=\"view-games\">\n    <div class=\"sec-title\"><span class=\"bar\"></span>Table Games<span class=\"rule\"></span></div>\n    <div class=\"grid\" id=\"grid\"></div>\n  </div>\n\n  <div class=\"view\" id=\"view-game\"><div class=\"panel\" id=\"panel\"></div></div>\n\n  <div class=\"view\" id=\"view-wallet\">\n    <div class=\"sec-title\"><span class=\"bar\"></span>Wallet<span class=\"rule\"></span></div>\n    <div class=\"wallet-actions\">\n      <a class=\"wa-dep\" id=\"depBtn\" href=\"#\" onclick=\"return walletGo('deposit')\">Deposit</a>\n      <button class=\"wa-wd\" id=\"wdBtn\" onclick=\"walletGo('withdraw')\">Withdraw</button>\n    </div>\n    <div class=\"stats-row\">\n      <div class=\"stat\"><b id=\"stGames\">0</b><span>GAMES</span></div>\n      <div class=\"stat\"><b id=\"stWins\">0</b><span>W / L</span></div>\n      <div class=\"stat\"><b id=\"stWagered\">0</b><span>WAGERED</span></div>\n      <div class=\"stat\"><b id=\"stPaid\">0</b><span>PAID OUT</span></div>\n    </div>\n    <div class=\"sec-title\"><span class=\"bar\"></span>Recent Rounds<span class=\"rule\"></span></div>\n    <div class=\"list\" id=\"history\"></div>\n  </div>\n\n  <div class=\"view\" id=\"view-board\">\n    <div class=\"sec-title\"><span class=\"bar\"></span>Leaderboard<span class=\"rule\"></span></div>\n    <div class=\"list\" id=\"board\"></div>\n  </div>\n\n  <div class=\"view\" id=\"view-fair\">\n    <div class=\"sec-title\"><span class=\"bar\"></span>Provably Fair<span class=\"rule\"></span></div>\n    <div class=\"fair-card\">\n      <h3>Verifiable results</h3>\n      <p>Before each round the server commits to a random seed and reveals its SHA-256 hash. Every outcome is derived from <code>hash(seed + nonce + salt)</code>, so a result can never be changed after you have played - not even by the house. Table games carry a 3% house edge (return to player of 97%).</p>\n    </div>\n    <div class=\"fair-card\">\n      <h3>House rules</h3>\n      <p>Minimum and maximum bets are set by the operator. Balances are shared with the Casino Royals Telegram bot - one wallet, everywhere. Payouts credit instantly; deposits and withdrawals are handled through the bot. Play only with funds you can afford to lose.</p>\n    </div>\n  </div>\n</div>\n\n<div id=\"toast\"></div>\n<script>\n/* ============================== SOUND ENGINE ============================== */\nconst sfx=(function(){\n  let ctx=null,muted=localStorage.getItem('cr_muted')==='1';\n  function ensure(){\n    if(!ctx){try{ctx=new (window.AudioContext||window.webkitAudioContext)();}catch(e){ctx=null;}}\n    if(ctx&&ctx.state==='suspended'){try{ctx.resume();}catch(e){}}\n  }\n  function tone(freq,dur,type,vol,delay,slideTo){\n    if(muted)return;ensure();if(!ctx)return;\n    const t0=ctx.currentTime+(delay||0);\n    const o=ctx.createOscillator(),g=ctx.createGain();\n    o.type=type||'sine';o.frequency.setValueAtTime(freq,t0);\n    if(slideTo)o.frequency.exponentialRampToValueAtTime(slideTo,t0+dur);\n    g.gain.setValueAtTime(0.0001,t0);\n    g.gain.exponentialRampToValueAtTime(vol||0.15,t0+0.012);\n    g.gain.exponentialRampToValueAtTime(0.0001,t0+dur);\n    o.connect(g);g.connect(ctx.destination);\n    o.start(t0);o.stop(t0+dur+0.05);\n  }\n  function noise(dur,vol,fc,delay){\n    if(muted)return;ensure();if(!ctx)return;\n    const t0=ctx.currentTime+(delay||0);\n    const len=Math.max(1,Math.floor(ctx.sampleRate*dur));\n    const buf=ctx.createBuffer(1,len,ctx.sampleRate);\n    const d=buf.getChannelData(0);\n    for(let i=0;i<len;i++)d[i]=(Math.random()*2-1)*(1-i/len);\n    const src=ctx.createBufferSource();src.buffer=buf;\n    const f=ctx.createBiquadFilter();f.type='lowpass';f.frequency.value=fc||900;\n    const g=ctx.createGain();g.gain.setValueAtTime(vol||0.2,t0);\n    g.gain.exponentialRampToValueAtTime(0.0001,t0+dur);\n    src.connect(f);f.connect(g);g.connect(ctx.destination);\n    src.start(t0);\n  }\n  return {\n    get muted(){return muted;},\n    toggle(){muted=!muted;localStorage.setItem('cr_muted',muted?'1':'0');return muted;},\n    unlock(){ensure();},\n    click(){tone(700,0.06,'square',0.06);tone(1050,0.05,'sine',0.08,0.02);},\n    tick(){tone(2200,0.03,'square',0.05);},\n    coin(){tone(1250,0.12,'sine',0.14);tone(1875,0.22,'sine',0.12,0.09);},\n    deal(){noise(0.12,0.12,2400);tone(520,0.06,'triangle',0.06,0.03);},\n    roll(){tone(320,0.5,'sawtooth',0.05,0,420);noise(0.25,0.06,1200,0.05);},\n    win(){tone(523,0.14,'triangle',0.16);tone(659,0.14,'triangle',0.16,0.11);tone(784,0.14,'triangle',0.16,0.22);tone(1046,0.4,'triangle',0.2,0.33);tone(1568,0.5,'sine',0.12,0.45);},\n    bigwin(){[523,659,784,1046,1318,1568].forEach((f,i)=>tone(f,0.22,'triangle',0.18,i*0.09));noise(0.5,0.05,3000,0.5);},\n    lose(){tone(300,0.25,'sawtooth',0.1,0,150);tone(150,0.45,'sawtooth',0.12,0.18,70);},\n    boom(){noise(0.5,0.4,700);tone(90,0.5,'sawtooth',0.25,0,40);},\n    cash(){tone(880,0.08,'square',0.1);tone(1320,0.08,'square',0.1,0.07);tone(1760,0.16,'square',0.12,0.14);},\n    fanfare(){[392,523,659,784].forEach((f,i)=>tone(f,0.3,'triangle',0.14,i*0.16));[1046,1318].forEach((f,i)=>tone(f,0.5,'triangle',0.16,0.7+i*0.12));}\n  };\n})();\nfunction toggleMute(){\n  const m=sfx.toggle();\n  document.getElementById('muteBtn').innerHTML=m?ICON.muteOn:ICON.muteOff;\n  if(!m)sfx.unlock();\n}\nfunction hap(kind){try{const w=window.Telegram&&Telegram.WebApp;if(w&&w.HapticFeedback){w.HapticFeedback.impactOccurred(kind||'light');}}catch(e){}}\n\n/* ============================== ICONS / LOGOS ============================== */\nconst ICON={\n  crown:'<svg viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.6\" stroke-linejoin=\"round\"><path d=\"M2.5 7.5L6 11l6-7 6 7 3.5-3.5L20 20H4L2.5 7.5z\" fill=\"rgba(245,158,11,.25)\"/><rect x=\"3.4\" y=\"16.6\" width=\"17.2\" height=\"2.6\" rx=\"1.3\" fill=\"currentColor\"/></svg>',\n  dice:'<svg viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.7\"><rect x=\"4\" y=\"4\" width=\"16\" height=\"16\" rx=\"4\"/><circle cx=\"9\" cy=\"9\" r=\"1.4\" fill=\"currentColor\" stroke=\"none\"/><circle cx=\"15\" cy=\"9\" r=\"1.4\" fill=\"currentColor\" stroke=\"none\"/><circle cx=\"12\" cy=\"12\" r=\"1.4\" fill=\"currentColor\" stroke=\"none\"/><circle cx=\"9\" cy=\"15\" r=\"1.4\" fill=\"currentColor\" stroke=\"none\"/><circle cx=\"15\" cy=\"15\" r=\"1.4\" fill=\"currentColor\" stroke=\"none\"/></svg>',\n  crash:'<svg viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.7\" stroke-linejoin=\"round\"><path d=\"M12 2c2.5 3.5 6 5 7.5 11-1.6 1.6-4 1.6-5.5.4.7 4-.7 7.5-2 10-1.3-2.5-2.7-6-2-10-1.5 1.2-3.9 1.2-5.5-.4C6 7 9.5 5.5 12 2z\" fill=\"rgba(59,130,246,.18)\"/></svg>',\n  mines:'<svg viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.7\"><circle cx=\"12\" cy=\"14\" r=\"7.5\"/><path d=\"M12 6.5c-1.5-2.5-2.5-3.5-4-4\" stroke-linecap=\"round\"/><path d=\"M14 8.5l2.2-1.6\"/><circle cx=\"9.4\" cy=\"12\" r=\"1.3\" fill=\"currentColor\" stroke=\"none\"/><circle cx=\"14.6\" cy=\"12\" r=\"1.3\" fill=\"currentColor\" stroke=\"none\"/><circle cx=\"12\" cy=\"16.6\" r=\"1.3\" fill=\"currentColor\" stroke=\"none\"/></svg>',\n  towers:'<svg viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.7\" stroke-linejoin=\"round\"><rect x=\"6\" y=\"14\" width=\"12\" height=\"3\" rx=\"1\"/><rect x=\"8\" y=\"10\" width=\"8\" height=\"3\" rx=\"1\"/><rect x=\"10\" y=\"6\" width=\"4\" height=\"3\" rx=\"1\"/><rect x=\"10.8\" y=\"2.4\" width=\"2.4\" height=\"2.6\" rx=\"1.2\"/></svg>',\n  blackjack:'<svg viewBox=\"0 0 24 24\" fill=\"currentColor\"><path d=\"M12 2.5C9 9 4.5 10.5 4.5 15.2 4.5 19 8 22 12 22s7.5-3 7.5-6.8C19.5 10.5 15 9 12 2.5z\"/></svg>',\n  baccarat:'<svg viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.7\"><rect x=\"3.5\" y=\"4.5\" width=\"13\" height=\"17\" rx=\"2.4\" transform=\"rotate(-9 10 13)\"/><rect x=\"7.5\" y=\"3.4\" width=\"13\" height=\"17\" rx=\"2.4\" transform=\"rotate(8 14 12)\"/></svg>',\n  roulette:'<svg viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.7\"><circle cx=\"12\" cy=\"12\" r=\"9\"/><circle cx=\"12\" cy=\"12\" r=\"2.4\" fill=\"currentColor\" stroke=\"none\"/><path d=\"M12 3v5M12 16v5M3 12h5M16 12h5M5.6 5.6l3.6 3.6M14.8 14.8l3.6 3.6M18.4 5.6l-3.6 3.6M9.2 14.8l-3.6 3.6\"/></svg>',\n  hilo:'<svg viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M12 3l7 8h-4.2L12 21l-2.8-10H5l7-8z\"/></svg>',\n  plinko:'<svg viewBox=\"0 0 24 24\" fill=\"currentColor\"><circle cx=\"12\" cy=\"4.5\" r=\"1.5\"/><circle cx=\"8\" cy=\"9\" r=\"1.5\"/><circle cx=\"16\" cy=\"9\" r=\"1.5\"/><circle cx=\"5\" cy=\"13.5\" r=\"1.5\"/><circle cx=\"12\" cy=\"13.5\" r=\"1.5\"/><circle cx=\"19\" cy=\"13.5\" r=\"1.5\"/><circle cx=\"3\" cy=\"18\" r=\"1.5\"/><circle cx=\"8.5\" cy=\"18\" r=\"1.5\"/><circle cx=\"15.5\" cy=\"18\" r=\"1.5\"/><circle cx=\"21\" cy=\"18\" r=\"1.5\"/></svg>',\n  keno:'<svg viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.7\" stroke-linejoin=\"round\"><path d=\"M12 2.6l2.6 6 6.4.5-4.9 4.2 1.5 6.3L12 16.1l-5.6 3.5 1.5-6.3-4.9-4.2 6.4-.5 2.6-6z\" fill=\"rgba(59,130,246,.16)\"/></svg>',\n  wheel:'<svg viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.7\"><circle cx=\"12\" cy=\"12\" r=\"9\"/><circle cx=\"12\" cy=\"12\" r=\"2\" fill=\"currentColor\" stroke=\"none\"/><path d=\"M12 3v4M12 17v4M3 12h4M17 12h4M6.8 6.8l2.8 2.8M14.4 14.4l2.8 2.8M17.2 6.8l-2.8 2.8M9.6 14.4l-2.8 2.8\"/></svg>',\n  limbo:'<svg viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\" stroke-linecap=\"round\"><path d=\"M6 12c0-3.3 2.7-6 6-6s6 2.7 6 6-2.7 6-6 6-6-2.7-6-6z\"/><path d=\"M18 12c0-3.3 2.7-6 6-6M6 18c-3.3 0-6-2.7-6-6\"/></svg>',\n  coinflip:'<svg viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.7\"><circle cx=\"12\" cy=\"12\" r=\"9\"/><circle cx=\"12\" cy=\"12\" r=\"6\" fill=\"rgba(59,130,246,.14)\"/><path d=\"M12 9.5v5M9.8 12h4.4\"/></svg>',\n  slots:'<svg viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.7\"><rect x=\"3\" y=\"4\" width=\"18\" height=\"16\" rx=\"3.4\"/><rect x=\"6.2\" y=\"7\" width=\"3.2\" height=\"10\" rx=\"1.4\"/><rect x=\"10.4\" y=\"7\" width=\"3.2\" height=\"10\" rx=\"1.4\"/><rect x=\"14.6\" y=\"7\" width=\"3.2\" height=\"10\" rx=\"1.4\"/></svg>',\n  muteOn:'<svg viewBox=\"0 0 24 24\" width=\"20\" height=\"20\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.8\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M11 5L6 9H3v6h3l5 4V5z\" fill=\"rgba(37,99,235,.2)\"/><path d=\"M15.5 8.5a5 5 0 010 7M18.5 6a9 9 0 010 12\"/></svg>',\n  muteOff:'<svg viewBox=\"0 0 24 24\" width=\"20\" height=\"20\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.8\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M11 5L6 9H3v6h3l5 4V5z\" fill=\"rgba(37,99,235,.2)\"/><path d=\"M22 9l-6 6M16 9l6 6\"/></svg>'\n};\n\n/* ============================== CORE STATE ============================== */\nconst S={demo:true,user:null,balance:0,cfg:null,game:null,session:null,history:[],board:[],\n  stats:{games:0,wins:0,losses:0,wagered:0,paid:0},busy:false,bet:0};\nconst $=id=>document.getElementById(id);\nconst em=html=>String(html==null?'':html).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));\nconst fmt=n=>{n=Math.round(n*100)/100;let s=n.toFixed(2).replace(/\\.?0+$/,'');return s||'0'};\n\nlet balTimer=null,balShown=0;\nfunction setBal(target){\n  const el=$('bal');if(!el)return;\n  target=Math.round((+target||0)*100)/100;\n  if(balTimer){clearInterval(balTimer);balTimer=null;}\n  const from=balShown,delta=target-from;\n  if(Math.abs(delta)<0.005){balShown=target;el.textContent=fmt(target);el.classList.remove('pulse');void el.offsetWidth;el.classList.add('pulse');return;}\n  const t0=Date.now(),dur=420;\n  balTimer=setInterval(()=>{\n    const t=Math.min(1,(Date.now()-t0)/dur);\n    const v=from+delta*(1-Math.pow(1-t,3));\n    balShown=v;el.textContent=fmt(v);\n    if(t>=1){clearInterval(balTimer);balTimer=null;balShown=target;el.textContent=fmt(target);\n      el.classList.remove('pulse');void el.offsetWidth;el.classList.add('pulse');}\n  },16);\n}\n\nfunction toast(msg){\n  const t=$('toast');if(!t)return;\n  t.textContent=msg;t.classList.add('show');\n  clearTimeout(t._h);t._h=setTimeout(()=>t.classList.remove('show'),2600);\n}\nfunction notify(msg){toast(msg);}\n\nfunction initData(){\n  if(window.Telegram&&Telegram.WebApp&&Telegram.WebApp.initData)return Telegram.WebApp.initData;\n  return 'user=%7B%22id%22%3A777000%2C%22first_name%22%3A%22Preview%20Player%22%7D';\n}\nasync function api(path,body){\n  try{\n    const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},\n      body:JSON.stringify(Object.assign({initData:initData()},body||{}))});\n    const j=await r.json();\n    if(!r.ok&&r.status!==401){return {ok:false,error:j.error||'Request failed',code:j.code};}\n    return j;\n  }catch(e){return {offline:true};}\n}\n\n/* ============================== DEMO ENGINE ============================== */\nconst DEMO={\n  deck(){let d=[];for(let i=0;i<52;i++){let v=(i%13)+2;d.push(v>14?14:v);}for(let i=d.length-1;i>0;i--){let j=Math.floor(Math.random()*(i+1));[d[i],d[j]]=[d[j],d[i]];}return d;},\n  bjVal(h){let t=0,a=0;h.forEach(c=>{if(c===14){a++;t+=1}else t+=Math.min(c,10);});return a>0&&t+10<=21?t+10:t;}\n};\nfunction demoFair(){return {seed_hash:[...Array(24)].map(()=>Math.floor(Math.random()*16).toString(16)).join(''),nonce:'0'};}\nfunction demoResult(game,action,data){\n  data=data||{};\n  let bet=parseFloat(data.bet)||0;\n  if(!bet&&S.session&&S.session.game===game)bet=S.session.bet||0;\n  const rnd=()=>Math.random();\n  const fair=demoFair();\n  let won,payout=0,extra={};\n  switch(game){\n    case 'dice':{\n      const dir=data.direction==='under'?'under':'over',t=parseInt(data.target)||50;\n      const roll=1+Math.floor(rnd()*100);\n      won=dir==='over'?roll>t:roll<t;\n      const wins=dir==='over'?(100-t):(t-1);\n      const mult=wins>0?0.97*100/wins:0;\n      payout=won?bet*mult:0;\n      extra={roll,target:t,direction:dir,multiplier:mult};break;}\n    case 'crash':{\n      if(action==='play'){\n        const r=rnd();const cp=r>=0.97?1:Math.max(1.01,Math.round((0.97/r)*100)/100);\n        S.session={game:'crash',bet,cp,started:Date.now(),cashed:false};\n        return {ok:true,session_id:1,crash_point:cp,bet,fair};}\n      const mult=Math.min(parseFloat(data.multiplier)||1,S.session.cp-0.01);\n      payout=bet*mult;won=true;extra={multiplier:mult,crash_point:S.session.cp};break;}\n    case 'mines':{\n      const mines=[3,5,10].includes(parseInt(data.mines))?parseInt(data.mines):3;\n      if(action==='new'){\n        let bombs=new Set();while(bombs.size<mines)bombs.add(Math.floor(rnd()*25));\n        S.session={game:'mines',bet,mines,bombs:[...bombs],revealed:[]};\n        return {ok:true,session_id:1,grid:[...Array(25)].map((_,i)=>({i,revealed:false})),fair};}\n      const s=S.session;\n      if(action==='cashout'){\n        const m=minesMult(s.mines,s.revealed.length);payout=bet*m;won=true;\n        extra={multiplier:m,revealed:[...s.revealed]};break;}\n      const cell=parseInt(data.cell);\n      if(s.revealed.includes(cell))return {ok:false,error:'Already revealed.'};\n      s.revealed.push(cell);\n      if(s.bombs.includes(cell)){won=false;payout=0;extra={bomb_at:cell,revealed:[...s.revealed]};break;}\n      if(s.revealed.length>=25-s.mines){const m=minesMult(s.mines,s.revealed.length);payout=bet*m;won=true;extra={cleared:true,multiplier:m,revealed:[...s.revealed]};break;}\n      return {ok:true,won:null,cell,revealed:[...s.revealed],multiplier:minesMult(s.mines,s.revealed.length),potential_payout:bet*minesMult(s.mines,s.revealed.length),bet,fair};}\n    case 'towers':{\n      const diff=data.difficulty||'easy';const bad={easy:1,medium:2,hard:3}[diff];\n      if(action==='new'){\n        S.session={game:'towers',bet,bad,row:0,layout:[...Array(8)].map(function(){var b=new Set();while(b.size<bad)b.add(Math.floor(rnd()*3));return[...b];})};\n        return {ok:true,session_id:1,difficulty:diff,fair};}\n      const s=S.session;\n      if(action==='cashout'){const m=towMult(s.row,bad);payout=bet*m;won=true;extra={multiplier:m,row:s.row};break;}\n      const col=parseInt(data.col);\n      if(s.layout[s.row].includes(col)){won=false;payout=0;extra={row:s.row,col};break;}\n      s.row++;\n      const m=towMult(s.row,bad);\n      if(s.row>=8){payout=bet*m;won=true;extra={cleared:true,multiplier:m};break;}\n      return {ok:true,won:null,row:s.row,col,multiplier:m,potential_payout:bet*m,bet,fair};}\n    case 'blackjack':{\n      if(action==='new'){\n        let d=DEMO.deck(),p=[d.pop(),d.pop()],dl=[d.pop(),d.pop()];\n        S.session={game:'blackjack',bet,deck:d,player:p,dealer:dl,doubled:false};\n        return {ok:true,session_id:1,player:p.map(cl),dealer:[cl(dl[0]),'?'],player_value:DEMO.bjVal(p),fair};}\n      const s=S.session;\n      if(action==='hit'){s.player.push(s.deck.pop());\n        if(DEMO.bjVal(s.player)>21)return bjDemoSettle(s);\n        return {ok:true,player:s.player.map(cl),player_value:DEMO.bjVal(s.player),dealer:[cl(s.dealer[0]),'?'],fair};}\n      if(action==='double'){s.bet=s.bet*2;s.player.push(s.deck.pop());return bjDemoSettle(s);}\n      return bjDemoSettle(s);}\n    case 'baccarat':{\n      const side=data.side||'player';\n      const winner=['player','banker','tie'][Math.floor(rnd()*3)];\n      won=winner===side;const mult={player:2,banker:1.95,tie:9}[side];\n      payout=won?bet*mult:0;\n      extra={winner,player_cards:['A','7'],banker_cards:['K','8'],player_value:8,banker_value:8,side};break;}\n    case 'roulette':{\n      const spin=Math.floor(rnd()*37);\n      let choice=data.choice||'red';\n      const color=spin===0?'green':([1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36].includes(spin)?'red':'black');\n      let mult=0;\n      if(choice==='red'||choice==='black')mult=color===choice?2:0;\n      else if(choice==='green')mult=spin===0?14:0;\n      else if(choice==='even'||choice==='odd')mult=spin!==0&&(spin%2===0)===(choice==='even')?2:0;\n      else if(choice==='low')mult=spin>=1&&spin<=18?2:0;\n      else if(choice==='high')mult=spin>=19?2:0;\n      else if(/^\\d+$/.test(choice)){mult=spin===parseInt(choice)?36:0;}\n      won=mult>0;payout=won?bet*mult:0;\n      extra={spin,color,choice};break;}\n    case 'hilo':{\n      if(action==='new'){let d=DEMO.deck(),cur=d.pop();\n        S.session={game:'hilo',bet,deck:d,current:cur,mult:1,step:0};\n        return {ok:true,session_id:1,card:cl(cur),higher_mult:1.2,lower_mult:1.2,cards_left:d.length,fair};}\n      const s=S.session;\n      if(action==='cashout'){payout=bet*s.mult;won=true;extra={multiplier:s.mult,steps:s.step};break;}\n      const card=s.deck.pop();\n      const ok=(action==='higher'&&card>s.current)||(action==='lower'&&card<s.current);\n      if(!ok){won=false;payout=0;extra={drawn:cl(card),had:cl(s.current),tie:card===s.current};break;}\n      s.current=card;s.step++;s.mult*=1.05;\n      if(s.deck.length===0){payout=bet*s.mult;won=true;extra={deck_cleared:true,multiplier:s.mult};break;}\n      return {ok:true,won:null,card:cl(card),higher_mult:1.2,lower_mult:1.2,multiplier:s.mult,potential_payout:bet*s.mult,cards_left:s.deck.length,fair};}\n    case 'plinko':{\n      const risk=data.risk||'low';\n      const tabs={low:[5.4,2,1.1,0.95,0.48,0.95,1.1,2,5.4],medium:[12,3.1,1.3,0.65,0.3,0.65,1.3,3.1,12],high:[20,4.5,1.6,0.35,0.18,0.35,1.6,4.5,20]}[risk];\n      const bucket=Math.floor(rnd()*9);const mult=tabs[bucket];\n      payout=bet*mult;won=payout>0;extra={bucket,risk,multiplier:mult};break;}\n    case 'keno':{\n      const picks=(data.picks||[]).slice().sort((a,b)=>a-b);\n      let drawn=new Set();while(drawn.size<10)drawn.add(1+Math.floor(rnd()*80));\n      const hits=picks.filter(p=>drawn.has(p));\n      const mult=hits.length>=2?Math.min(1000,0.97/(picks.length-1)*comb(80,10)/(comb(picks.length,hits.length)*comb(80-picks.length,10-hits.length))):0;\n      payout=bet*mult;won=payout>0;\n      extra={picks,drawn:[...drawn].sort((a,b)=>a-b),hits,multiplier:mult};break;}\n    case 'wheel':{\n      const segs=[0,0.9,1.3,1.7,2.6,4.3,8.5],weights=[30,42,14,7,4,2,1];\n      let r=rnd()*100,idx=0,acc=0;\n      for(let i=0;i<weights.length;i++){acc+=weights[i];if(r<acc){idx=i;break;}}\n      const mult=segs[idx];payout=bet*mult;won=payout>0;extra={segment:idx,multiplier:mult};break;}\n    case 'limbo':{\n      const t=Math.max(1.01,Math.min(100000,parseFloat(data.target)||2));\n      const p=(1e8-t*1e6)/1e8,mult=0.97/p;\n      const roll=rnd();won=roll>=p;payout=won?bet*mult:0;\n      extra={target:t,multiplier:mult};break;}\n    case 'coinflip':{\n      const side=data.side||'heads';const landed=rnd()<0.5?'heads':'tails';\n      won=landed===side;payout=won?bet*1.94:0;extra={landed,side};break;}\n    case 'slots':{\n      const sym=['C','R','7','A','K','Q','J'];\n      const reel=[0,1,2].map(()=>sym[Math.floor(rnd()*sym.length)]);\n      const mult=reel.every(x=>x===reel[0])?{C:2,R:3,7:4,A:5,K:10,Q:20,J:50}[reel[0]]:0;\n      payout=bet*mult;won=payout>0;extra={reel,multiplier:mult};break;}\n  }\n  S.balance+=payout;S.session=null;\n  return {ok:true,won:won!==null?won:undefined,payout,bet,...extra,fair};\n}\nfunction bjDemoSettle(s){\n  let dl=s.dealer;\n  while(DEMO.bjVal(dl)<17&&s.deck.length)dl.push(s.deck.pop());\n  const pv=DEMO.bjVal(s.player),dv=DEMO.bjVal(dl);\n  let payout=0,won=false,push=false;\n  const bet=s.bet;\n  const natural=s.player.length===2&&pv===21;\n  if(pv<=21&&(dv>21||pv>dv)){payout=bet*(natural?2.5:2);won=true;}\n  else if(pv<=21&&pv===dv){payout=bet;push=true;won=true;}\n  S.balance+=payout;S.session=null;\n  return {ok:true,won,push,payout,bet,player_cards:s.player.map(cl),dealer_cards:dl.map(cl),player_value:pv,dealer_value:dv,natural,fair:demoFair()};\n}\nfunction minesMult(mines,rev){if(!rev)return 1;return Math.round(0.97*comb(25,rev)/comb(25-mines,rev)*100)/100;}\nfunction towMult(row,bad){return Math.round(0.97*Math.pow(3/(3-bad),row)*100)/100;}\nfunction comb(n,k){let r=1;for(let i=0;i<k;i++)r=r*(n-i)/(i+1);return Math.round(r);}\nfunction cl(c){return c===14?'A':c===13?'K':c===12?'Q':c===11?'J':c===1?'A':String(c);}\n\n/* ============================== INTRO ============================== */\nlet introSkipped=false,introDone=false;\nfunction buildIntroTitle(){\n  const words='CASINO ROYALS';\n  const el=$('introTitle');\n  el.innerHTML=words.split('').map((ch,i)=>\n    `<span class=\"${ch===' '?'':(i>=words.indexOf('ROYALS')?'gold':'')}\" style=\"animation-delay:${0.15+i*0.05}s\">${ch===' '?'&nbsp;':ch}</span>`\n  ).join('');\n}\nfunction skipIntro(){\n  if(introDone)return;\n  introSkipped=true;\n  const it=$('intro');\n  if(it){it.classList.add('gone');}\n  setTimeout(()=>{if(it&&it.parentNode)it.parentNode.removeChild(it);introDone=true;},650);\n}\nfunction startIntro(){\n  buildIntroTitle();\n  sfx.unlock();\n  const it=$('intro');\n  it.addEventListener('click',skipIntro);\n  setTimeout(()=>{if(!introSkipped)sfx.fanfare();},300);\n  setTimeout(skipIntro,2900);\n  setTimeout(()=>{if(!introDone){introDone=true;if(it.parentNode)it.parentNode.removeChild(it);}},3600);\n}\n\n/* ============================== BOOTSTRAP ============================== */\nasync function boot(){\n  startIntro();\n  try{\n    const w=window.Telegram&&Telegram.WebApp;\n    if(w){try{w.ready();w.expand();}catch(e){}}\n    const cfg=await api('/api/config');\n    if(!cfg.offline){S.cfg=cfg;S.demo=!!cfg.demoMode;$('bannerDemo').style.display=S.demo?'block':'none';}\n    else{S.cfg={appName:'Casino Royals',currency:'Coins',minBet:1,maxBet:100,games:GAMES_META,botUsername:null};S.demo=true;}\n    if(S.demo){S.balance=1000;setBal(S.balance);renderGrid();renderStats();}\n    else{\n      const init=await api('/api/init');\n      if(init&&init.ok&&init.user){\n        S.user=init.user;setBal(init.balance||0);\n        S.history=init.history||[];S.board=init.leaderboard||[];\n        S.stats=init.stats||S.stats;\n      }\n      renderGrid();renderStats();\n    }\n    $('depBtn').href='https://t.me/'+(S.cfg.botUsername||'');\n  }catch(err){\n    S.cfg={appName:'Casino Royals',currency:'Coins',minBet:1,maxBet:100,games:GAMES_META,botUsername:null};\n    S.demo=true;setBal(1000);renderGrid();renderStats();\n    const b=$('bannerErr');\n    if(b){b.style.display='block';b.textContent='Connection issue - running in local mode. '+(err&&err.message?err.message:'');}\n  }\n  document.getElementById('muteBtn').innerHTML=sfx.muted?ICON.muteOff:ICON.muteOn;\n}\n\n/* ============================== VIEWS ============================== */\ndocument.querySelectorAll('#tabs button').forEach(b=>b.onclick=()=>{\n  sfx.click();hap();\n  document.querySelectorAll('#tabs button').forEach(x=>x.classList.remove('on'));\n  b.classList.add('on');\n  document.querySelectorAll('.view').forEach(v=>v.classList.remove('on'));\n  $('view-'+b.dataset.view).classList.add('on');\n  if(b.dataset.view==='wallet')renderWallet();\n  if(b.dataset.view==='board')renderBoard();\n});\n\nfunction renderGrid(){\n  const games=(S.cfg&&S.cfg.games&&S.cfg.games.length)?S.cfg.games:GAMES_META;\n  $('grid').innerHTML=games.map(g=>{\n    const icon=ICON[g&&g.id]||ICON.dice;\n    const name=(g&&g.name)||'Game';\n    const tag=(g&&g.tag)?String(g.tag).toUpperCase():'';\n    return `\n    <div class=\"tile\" onclick=\"sfx.click();hap();openGame('${(g&&g.id)||''}')\">\n      <span class=\"tg\">${em(tag)}</span>\n      <div class=\"icon-ring\">${icon}</div>\n      <div class=\"nm\">${em(name)}</div>\n    </div>`;\n  }).join('');\n}\n\nfunction openGame(id){\n  S.game=id;S.session=null;\n  const g=(S.cfg.games||GAMES_META).find(x=>x.id===id)||{id:id,name:id,mono:id[0].toUpperCase()};\n  document.querySelectorAll('.view').forEach(v=>v.classList.remove('on'));\n  $('view-game').classList.add('on');\n  renderPanel(g);\n}\nfunction backGames(){sfx.click();document.querySelectorAll('.view').forEach(v=>v.classList.remove('on'));$('view-games').classList.add('on');}\n\n/* ============================== PANEL SHELL ============================== */\nfunction panelShell(g,inner,betCtrl=true){\n  const min=S.cfg.minBet||1,max=S.cfg.maxBet||100;\n  const icon=ICON[g.id]||ICON.dice;\n  return `\n  <div class=\"panel-head\">\n    <button class=\"back-btn\" onclick=\"backGames()\">&larr;</button>\n    <div class=\"icon-ring\">${icon}</div>\n    <div><h2>${em(g.name)}</h2><small>PROVABLY FAIR</small></div>\n  </div>\n  ${betCtrl?`\n  <div class=\"bet-row\"><label>BET</label><div class=\"bet-input\">\n    <input type=\"number\" id=\"betIn\" min=\"${min}\" max=\"${max}\" step=\"1\" value=\"${Math.max(min,Math.min(max,S.bet||min))}\"></div></div>\n  <div class=\"chips\">\n    <button onclick=\"sfx.click();setBet('min')\">MIN</button>\n    <button onclick=\"sfx.click();setBet('x2')\">2x</button>\n    <button onclick=\"sfx.click();setBet('x5')\">5x</button>\n    <button onclick=\"sfx.click();setBet('max')\">MAX</button>\n  </div>`:''}\n  ${inner}\n  <div class=\"hint-msg\" id=\"panelMsg\"></div>\n  <div id=\"resultBox\"></div>\n  <div class=\"fair\" id=\"fairBox\"></div>`;\n}\nfunction setBet(kind){\n  const min=S.cfg.minBet||1,max=S.cfg.maxBet||100;\n  const cur=parseFloat($('betIn').value)||min;\n  $('betIn').value=fmt(kind==='min'?min:kind==='x2'?Math.min(max,cur*2):kind==='x5'?Math.min(max,cur*5):max);\n}\nfunction getBet(){const v=parseFloat($('betIn')&&$('betIn').value);return isNaN(v)?0:v;}\n\nfunction renderPanel(g){\n  const m={dice:pnlDice,crash:pnlCrash,mines:pnlMines,towers:pnlTowers,blackjack:pnlBJ,baccarat:pnlBaccarat,\n    roulette:pnlRoulette,hilo:pnlHilo,plinko:pnlPlinko,keno:pnlKeno,wheel:pnlWheel,limbo:pnlLimbo,\n    coinflip:pnlCoin,slots:pnlSlots};\n  $('panel').innerHTML=panelShell(g,(m[g.id]||pnlDice)());\n  $('betIn')&&($('betIn').oninput=()=>{S.bet=parseFloat($('betIn').value)||0;});\n}\n\nfunction showResult(res){\n  const box=$('resultBox');\n  if(!box)return;\n  if(res&&res.ok===false){box.innerHTML=`<div class=\"result lose\"><div class=\"lbl\">ERROR</div><div class=\"sub\">${em(res.error||'Request failed')}</div></div>`;return;}\n  if(res&&res.won===null)return;\n  if(res&&res.payout!==undefined){\n    S.balance=res.balance!==undefined?res.balance:S.balance;\n    setBal(S.balance);\n    const win=res.won&&res.payout>0;\n    const push=res.push;\n    if(win)sfx.win();else if(push)sfx.coin();else sfx.lose();\n    box.innerHTML=`<div class=\"result ${win?'win':'lose'}\">\n      <div class=\"lbl\">${push?'PUSH':win?'YOU WIN':'ROUND LOST'}</div>\n      <div class=\"big\">${push?'RETURNED':(win?'+'+fmt(res.payout):'-'+fmt((res.bet||0)-(res.payout||0)||0))}</div>\n      <div class=\"sub\">Balance: <b>${fmt(S.balance)}</b></div></div>`;\n  }\n  if(res&&res.fair){\n    $('fairBox').innerHTML=`Seed <code>${res.fair.seed_hash}...</code> Nonce <code>${res.fair.nonce}</code>`;\n  }\n}\nasync function doPlay(game,action,data){\n  if(S.busy)return;S.busy=true;\n  let res;\n  if(S.demo){res=demoResult(game,action,data);if(res.offline)res={ok:false,error:'Offline'};}\n  else res=await api('/api/play',{game,action,data});\n  S.busy=false;\n  if(res&&res.balance!==undefined){S.balance=res.balance;setBal(res.balance);}\n  if(res&&res.ok&&res.result)res=Object.assign({balance:res.balance},res.result);\n  return res;\n}\n\n/* ============================== DICE ============================== */\nlet diceDir='over',diceTarget=50;\nfunction pnlDice(){\n  return `\n  <div class=\"ctrl-row\">\n    <button class=\"ctrl on\" id=\"dOver\" onclick=\"sfx.click();diceDir='over';$('dOver').classList.add('on');$('dUnder').classList.remove('on');updDice()\">Over</button>\n    <button class=\"ctrl\" id=\"dUnder\" onclick=\"sfx.click();diceDir='under';$('dUnder').classList.add('on');$('dOver').classList.remove('on');updDice()\">Under</button>\n  </div>\n  <div class=\"range-row\"><input type=\"range\" id=\"dTarget\" min=\"1\" max=\"100\" value=\"50\" oninput=\"diceTarget=+this.value;updDice()\"><div class=\"val\" id=\"dTargetVal\">50</div></div>\n  <div class=\"payout-hint\" id=\"dHint\"></div>\n  <div class=\"dice-stage\"><div class=\"dice-num\" id=\"diceNum\">--</div></div>\n  <button class=\"primary\" onclick=\"playDice()\">Roll The Dice</button>`;\n}\nfunction updDice(){\n  $('dTargetVal').textContent=diceTarget;\n  const wins=diceDir==='over'?(100-diceTarget):(diceTarget-1);\n  const m=wins>0?0.97*100/wins:0;\n  $('dHint').innerHTML=`Payout <b>${fmt(m)}x</b> - win <b>${fmt(getBet()*m)}</b>`;\n}\nasync function playDice(){\n  const bet=getBet();if(!bet)return notify('Enter a bet amount.');\n  sfx.roll();\n  const el=$('diceNum');el.classList.add('rolling');\n  const rollAnim=setInterval(()=>{el.textContent=1+Math.floor(Math.random()*100);},80);\n  const res=await doPlay('dice','play',{bet,direction:diceDir,target:diceTarget});\n  setTimeout(()=>{\n    clearInterval(rollAnim);\n    el.classList.remove('rolling');el.classList.add('land');\n    if(res&&res.roll!==undefined)el.textContent=res.roll;\n    setTimeout(()=>el.classList.remove('land'),550);\n    if(res&&res.roll!==undefined){\n      $('resultBox').insertAdjacentHTML('afterbegin',\n        `<div class=\"result ${res.won?'win':'lose'}\"><div class=\"lbl\">DICE</div><div class=\"big\">${res.roll}</div></div>`);\n    }\n    showResult(res);\n  },900);\n}\n\n/* ============================== CRASH (Aviator style) ============================== */\nconst PLANE_PATH='M0 8 L18 1 L30 5 L26 11 L30 15 L18 17 L8 13 L0 8 Z';\nfunction pnlCrash(){\n  return `\n  <div class=\"crash-stage\" id=\"crashStage\">\n    <div class=\"cloud\" style=\"top:52px;width:120px;height:26px\"></div>\n    <div class=\"cloud\" style=\"top:140px;width:90px;height:22px;animation-duration:18s\"></div>\n    <div class=\"cloud\" style=\"top:210px;width:140px;height:28px;animation-duration:26s\"></div>\n    <canvas id=\"crashCv\"></canvas>\n    <div class=\"crash-mult\" id=\"crashMult\">1.00x</div>\n    <div class=\"crash-bet\" id=\"crashBet\">BET 0</div>\n  </div>\n  <div class=\"payout-hint\">Cash out before the plane flies away. The higher it climbs, the bigger the payout.</div>\n  <button class=\"primary\" id=\"crashStart\" onclick=\"playCrash()\">Take Off</button>`;\n}\nfunction crashCanvasFit(){\n  const cv=$('crashCv');if(!cv)return null;\n  const stage=$('crashStage');\n  const dpr=window.devicePixelRatio||1;\n  const w=stage.clientWidth,h=stage.clientHeight;\n  cv.width=w*dpr;cv.height=h*dpr;\n  const ctx=cv.getContext('2d');\n  if(!ctx)return null;\n  ctx.setTransform(dpr,0,0,dpr,0,0);\n  return {ctx,w,h};\n}\nfunction drawPlane(ctx,x,y,rot,scale){\n  ctx.save();\n  ctx.translate(x,y);ctx.rotate(rot);ctx.scale(scale||1.4,scale||1.4);\n  ctx.fillStyle='#1d4ed8';ctx.strokeStyle='#fff';ctx.lineWidth=1.2;\n  const p=new Path2D(PLANE_PATH);\n  ctx.fill(p);ctx.stroke(p);\n  ctx.restore();\n}\nasync function playCrash(){\n  const bet=getBet();if(!bet)return notify('Enter a bet amount.');\n  sfx.unlock();\n  const res=await doPlay('crash','play',{bet});\n  if(!res||!res.ok){showResult(res);return;}\n  const cp=res.crash_point;\n  $('crashStart')&&$('crashStart').remove();\n  $('crashBet').textContent='BET '+fmt(bet)+' | WIN '+fmt(bet);\n  const fit=crashCanvasFit();\n  let cashMultiplier=null;\n  let particles=[];\n  let raf=null;\n  const stage=$('crashStage');\n  const DUR=6500,t0=Date.now();\n  const trail=[];\n  const curveX=t=>0.06+0.84*Math.pow(t,1.25);\n  const curveY=t=>0.9-0.82*Math.pow(t,1.35);\n  const multAt=t=>cp>1?Math.exp(Math.log(cp)*t):1;\n  sfx.tick();\n  function frame(){\n    const t=Math.min(1,(Date.now()-t0)/DUR);\n    const mult=cashMultiplier!==null?cashMultiplier:multAt(t);\n    $('crashMult').textContent=fmt(mult)+'x';\n    $('crashBet').textContent='BET '+fmt(bet)+' | WIN '+fmt(bet*mult);\n    if(fit){\n      const {ctx,w,h}=fit;\n      ctx.clearRect(0,0,w,h);\n      if(!cashMultiplier){\n        const px=curveX(t)*w,py=curveY(t)*h;\n        trail.push({x:px,y:py});\n        if(trail.length>1){\n          for(let i=1;i<trail.length;i++){\n            const a=trail[i-1],b=trail[i];\n            const alpha=i/trail.length;\n            ctx.strokeStyle='rgba(37,99,235,'+(0.15+0.6*alpha)+')';\n            ctx.lineWidth=2.5+3*alpha;\n            ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.stroke();\n          }\n        }\n        const dx=curveX(Math.min(1,t+0.01))*w-px;\n        const dy=curveY(Math.min(1,t+0.01))*h-py;\n        const rot=Math.atan2(dy,dx)+0.35;\n        drawPlane(ctx,px,py,rot,1.35);\n      }else{\n        for(let i=1;i<trail.length;i++){\n          ctx.strokeStyle='rgba(245,158,11,'+(0.2+0.5*i/trail.length)+')';\n          ctx.lineWidth=2.5+2.5*i/trail.length;\n          ctx.beginPath();ctx.moveTo(trail[i-1].x,trail[i-1].y);ctx.lineTo(trail[i].x,trail[i].y);ctx.stroke();\n        }\n        if(trail.length){\n          const last=trail[trail.length-1];\n          drawPlane(ctx,last.x-16,last.y-14,-0.9,1.0);\n        }\n      }\n      particles=particles.filter(p=>p.life>0);\n      particles.forEach(p=>{\n        p.x+=p.vx;p.y+=p.vy;p.vy+=0.15;p.life--;\n        ctx.globalAlpha=Math.max(0,p.life/28);\n        ctx.fillStyle=p.color;\n        ctx.beginPath();ctx.arc(p.x,p.y,p.r,0,7);ctx.fill();\n      });\n      ctx.globalAlpha=1;\n    }\n    if(cashMultiplier===null&&(t>=1||mult>=cp)){\n      cancelAnimationFrame(raf);\n      stage.classList.add('boom');\n      sfx.boom();\n      if(fit&&trail.length){\n        const last=trail[trail.length-1];\n        for(let i=0;i<42;i++){\n          particles.push({x:last.x,y:last.y,vx:(Math.random()-0.5)*7,vy:(Math.random()-0.6)*6,\n            life:26+Math.floor(Math.random()*16),r:1.6+Math.random()*3.4,\n            color:['#f59e0b','#ef4444','#fbbf24','#ffffff'][i%4]});\n        }\n        let pr=raf;const boomFrames=()=>{\n          if(!fit)return;\n          const c2=fit;\n          c2.ctx.clearRect(0,0,c2.w,c2.h);\n          for(let i=1;i<trail.length;i++){\n            c2.ctx.strokeStyle='rgba(37,99,235,.35)';\n            c2.ctx.lineWidth=2.5;\n            c2.ctx.beginPath();c2.ctx.moveTo(trail[i-1].x,trail[i-1].y);c2.ctx.lineTo(trail[i].x,trail[i].y);c2.ctx.stroke();\n          }\n          particles=particles.filter(p=>p.life>0);\n          particles.forEach(p=>{p.x+=p.vx;p.y+=p.vy;p.vy+=0.16;p.life--;\n            c2.ctx.globalAlpha=Math.max(0,p.life/26);c2.ctx.fillStyle=p.color;\n            c2.ctx.beginPath();c2.ctx.arc(p.x,p.y,p.r,0,7);c2.ctx.fill();});\n          c2.ctx.globalAlpha=1;\n          if(particles.length)pr=requestAnimationFrame(boomFrames);\n        };\n        boomFrames();\n      }\n      setTimeout(()=>{stage.classList.remove('boom');},550);\n      if(!S.session||!S.session.cashed){\n        S.session=null;\n        showResult({ok:true,won:false,payout:0,bet,balance:S.balance,fair:res.fair});\n      }\n      return;\n    }\n    raf=requestAnimationFrame(frame);\n  }\n  raf=requestAnimationFrame(frame);\n  $('panel').insertAdjacentHTML('beforeend',\n    `<button class=\"primary alt\" id=\"cashBtn\" style=\"margin-top:14px\" onclick=\"cashCrash()\">Cash Out</button>`);\n}\nasync function cashCrash(){\n  const btn=$('cashBtn');if(!btn||btn.disabled)return;btn.disabled=true;\n  const cur=parseFloat($('crashMult').textContent)||1;\n  sfx.cash();hap('medium');\n  const res=await doPlay('crash','cashout',{session_id:S.session&&S.session.id||1,multiplier:cur});\n  S.session=null;\n  $('cashBtn').remove();\n  showResult(res);\n}\nfunction curGame(){return (S.cfg.games||GAMES_META).find(x=>x.id===S.game);}\n\n/* ============================== MINES ============================== */\nlet minesCount=3;\nfunction pnlMines(){\n  return `\n  <div class=\"ctrl-row\">\n    ${[3,5,10].map(m=>`<button class=\"ctrl ${m===minesCount?'on':''}\" onclick=\"sfx.click();minesCount=${m};renderPanel(curGame())\">${m} Bombs</button>`).join('')}\n  </div>\n  <div class=\"board\"><div class=\"mines-grid\" id=\"mGrid\"></div></div>\n  <button class=\"primary\" id=\"mStart\" onclick=\"startMines()\">Start Round</button>`;\n}\nasync function startMines(){\n  const bet=getBet();if(!bet)return notify('Enter a bet amount.');\n  sfx.click();\n  const res=await doPlay('mines','new',{bet,mines:minesCount});\n  if(!res||!res.ok){showResult(res);return;}\n  S.session={id:res.session_id,game:'mines',bet};\n  drawMines(res.fair);\n}\nfunction drawMines(fair){\n  const g=$('mGrid');g.innerHTML='';\n  for(let i=0;i<25;i++){\n    const c=document.createElement('div');c.className='mcell';c.id='mc'+i;\n    c.onclick=()=>revealMine(i);\n    g.appendChild(c);\n  }\n  if(fair)$('fairBox').innerHTML=`Seed <code>${fair.seed_hash}...</code>`;\n  $('mStart').remove();\n  $('panel').insertAdjacentHTML('beforeend',\n    `<button class=\"primary alt\" id=\"mCash\" style=\"margin-top:14px\" onclick=\"cashMines()\">Cash Out</button>`);\n}\nasync function revealMine(cell){\n  if(!S.session)return;\n  sfx.click();hap();\n  const res=await doPlay('mines','reveal',{session_id:S.session.id,cell});\n  if(res&&res.ok===false){showResult(res);return;}\n  const el=$('mc'+cell);\n  if(res.won===false){\n    el.innerHTML='<div class=\"boom\"></div>';el.classList.add('dead');\n    sfx.boom();\n    (res.revealed||[]).forEach(r=>{const e=$('mc'+r);if(e&&e.children.length===0){e.innerHTML='<div class=\"gem\"></div>';e.classList.add('rev');}});\n    S.session=null;const c=$('mCash');c&&c.remove();\n    showResult(res);\n  }else if(res.won===true){\n    el.innerHTML='<div class=\"gem\"></div>';el.classList.add('rev');\n    sfx.coin();\n    S.session=null;const c=$('mCash');c&&c.remove();\n    showResult(res);\n  }else{\n    el.innerHTML='<div class=\"gem\"></div>';el.classList.add('rev');\n    sfx.tick();\n    $('resultBox').innerHTML=`<div class=\"result lose\"><div class=\"lbl\">MULTIPLIER</div><div class=\"big\">${fmt(res.multiplier)}x</div><div class=\"sub\">Cash out <b>${fmt(res.potential_payout)}</b></div></div>`;\n  }\n}\nasync function cashMines(){\n  if(!S.session)return;\n  sfx.cash();hap('medium');\n  const res=await doPlay('mines','cashout',{session_id:S.session.id});\n  S.session=null;const c=$('mCash');c&&c.remove();\n  showResult(res);\n}\n\n/* ============================== TOWERS ============================== */\nlet towDiff='easy';\nfunction pnlTowers(){\n  return `\n  <div class=\"ctrl-row\">\n    ${['easy','medium','hard'].map(d=>`<button class=\"ctrl ${d===towDiff?'on':''}\" onclick=\"sfx.click();towDiff='${d}';renderPanel(curGame())\">${d[0].toUpperCase()+d.slice(1)}</button>`).join('')}\n  </div>\n  <div class=\"board\"><div id=\"towBoard\" style=\"display:flex;flex-direction:column;align-items:center\"></div></div>\n  <button class=\"primary\" id=\"towStart\" onclick=\"startTowers()\">Start Round</button>`;\n}\nfunction towRowsHTML(cleared,deadRow,deadCol){\n  let h='';\n  for(let r=7;r>=0;r--){\n    h+=`<div style=\"display:flex;gap:7px;margin-bottom:7px\">`;\n    for(let c=0;c<3;c++){\n      const state=r<cleared?'clr':(r===cleared?'cur':(r===deadRow&&c===deadCol?'dead':'fut'));\n      const styles={\n        clr:'border-color:rgba(59,130,246,.6);background:#fff;box-shadow:0 0 14px rgba(59,130,246,.4)',\n        cur:'border-color:rgba(59,130,246,.35);background:linear-gradient(160deg,#fff,#dce9ff)',\n        dead:'border-color:rgba(239,68,68,.7);background:linear-gradient(160deg,#fee2e2,#fecaca)',\n        fut:'border-color:rgba(59,130,246,.16);background:rgba(255,255,255,.65)'}[state];\n      const inner=state==='clr'?'<div class=\"gem\"></div>':state==='dead'?'<div class=\"boom\"></div>':'';\n      const on=state==='cur'?`onclick=\"pickTower(${c})\"`:'';\n      h+=`<div class=\"mcell\" style=\"width:54px;${styles};${state==='cur'?'cursor:pointer':''}\" ${on}>${inner}</div>`;\n    }\n    h+='</div>';\n  }\n  return h;\n}\nasync function startTowers(){\n  const bet=getBet();if(!bet)return notify('Enter a bet amount.');\n  sfx.click();\n  const res=await doPlay('towers','new',{bet,difficulty:towDiff});\n  if(!res||!res.ok){showResult(res);return;}\n  S.session={id:res.session_id,game:'towers',bet,cleared:0};\n  $('towStart').remove();\n  $('towBoard').innerHTML=towRowsHTML(0,-1,-1);\n  $('fairBox').innerHTML=`Seed <code>${res.fair.seed_hash}...</code>`;\n  $('panel').insertAdjacentHTML('beforeend',\n    `<button class=\"primary alt\" id=\"towCash\" style=\"margin-top:14px\" onclick=\"cashTowers()\">Cash Out</button>`);\n}\nasync function pickTower(col){\n  if(!S.session)return;\n  sfx.click();hap();\n  const res=await doPlay('towers','pick',{session_id:S.session.id,col});\n  if(res&&res.ok===false){showResult(res);return;}\n  if(res.won===false){\n    sfx.boom();\n    $('towBoard').innerHTML=towRowsHTML(S.session.cleared,res.row,col);\n    S.session=null;const c=$('towCash');c&&c.remove();showResult(res);\n  }else if(res.won===true){\n    sfx.coin();\n    $('towBoard').innerHTML=towRowsHTML(8,-1,-1);\n    S.session=null;const c=$('towCash');c&&c.remove();showResult(res);\n  }else{\n    sfx.tick();\n    S.session.cleared=res.row;\n    $('towBoard').innerHTML=towRowsHTML(res.row,-1,-1);\n    $('resultBox').innerHTML=`<div class=\"result lose\"><div class=\"lbl\">MULTIPLIER</div><div class=\"big\">${fmt(res.multiplier)}x</div><div class=\"sub\">Cash out <b>${fmt(res.potential_payout)}</b></div></div>`;\n  }\n}\nasync function cashTowers(){\n  if(!S.session)return;\n  sfx.cash();hap('medium');\n  const res=await doPlay('towers','cashout',{session_id:S.session.id});\n  S.session=null;const c=$('towCash');c&&c.remove();showResult(res);\n}\n\n/* ============================== BLACKJACK ============================== */\nfunction pnlBJ(){\n  return `\n  <div class=\"hand-label\">DEALER</div>\n  <div class=\"cardzone\" id=\"bjDealer\"></div>\n  <div class=\"hand-label\">YOUR HAND</div>\n  <div class=\"cardzone\" id=\"bjPlayer\"></div>\n  <div class=\"payout-hint\" id=\"bjHint\"></div>\n  <button class=\"primary\" id=\"bjStart\" onclick=\"startBJ()\">Deal</button>`;\n}\nasync function startBJ(){\n  const bet=getBet();if(!bet)return notify('Enter a bet amount.');\n  sfx.deal();\n  const res=await doPlay('blackjack','new',{bet});\n  if(!res||!res.ok){showResult(res);return;}\n  S.session={id:res.session_id,game:'blackjack',bet};\n  $('bjDealer').innerHTML=res.dealer.map(c=>c==='?'?'<div class=\"pcard back\"></div>':`<div class=\"pcard flip-in\">${c}</div>`).join('');\n  $('bjPlayer').innerHTML=res.player.map(c=>`<div class=\"pcard flip-in\">${c}</div>`).join('');\n  $('bjHint').innerHTML=`Your hand: <b>${res.player_value}</b>`;\n  $('fairBox').innerHTML=`Seed <code>${res.fair.seed_hash}...</code>`;\n  $('bjStart').remove();\n  $('panel').insertAdjacentHTML('beforeend',`\n    <div class=\"ctrl-row\" style=\"margin-top:14px\">\n      <button class=\"ctrl on\" onclick=\"bjAct('hit')\">Hit</button>\n      <button class=\"ctrl\" onclick=\"bjAct('stand')\">Stand</button>\n      <button class=\"ctrl\" onclick=\"bjAct('double')\">Double</button>\n    </div>`);\n}\nasync function bjAct(act){\n  if(!S.session)return;\n  sfx.deal();\n  const res=await doPlay('blackjack',act,{session_id:S.session.id});\n  if(res&&res.ok===false){showResult(res);return;}\n  if(res.player!==undefined&&res.player_value!==undefined&&res.won===undefined){\n    $('bjPlayer').innerHTML=res.player.map(c=>`<div class=\"pcard flip-in\">${c}</div>`).join('');\n    $('bjHint').innerHTML=`Your hand: <b>${res.player_value}</b>`;\n    return;\n  }\n  if(res.player_cards){\n    $('bjDealer').innerHTML=res.dealer_cards.map(c=>`<div class=\"pcard flip-in\">${c}</div>`).join('');\n    $('bjPlayer').innerHTML=res.player_cards.map(c=>`<div class=\"pcard flip-in\">${c}</div>`).join('');\n    $('bjHint').innerHTML=`You <b>${res.player_value}</b> - Dealer <b>${res.dealer_value}</b>`;\n    S.session=null;\n    showResult(res);\n  }\n}\n\n/* ============================== BACCARAT ============================== */\nlet bacSide='player';\nfunction pnlBaccarat(){\n  return `\n  <div class=\"ctrl-row\">\n    <button class=\"ctrl on\" onclick=\"sfx.click();bacSide='player';updBac()\">Player 2x</button>\n    <button class=\"ctrl\" onclick=\"sfx.click();bacSide='banker';updBac()\">Banker 1.95x</button>\n    <button class=\"ctrl\" onclick=\"sfx.click();bacSide='tie';updBac()\">Tie 9x</button>\n  </div>\n  <div class=\"hand-label\">BANKER</div><div class=\"cardzone\" id=\"bacB\"></div>\n  <div class=\"hand-label\">PLAYER</div><div class=\"cardzone\" id=\"bacP\"></div>\n  <div class=\"payout-hint\" id=\"bacHint\"></div>\n  <button class=\"primary\" onclick=\"playBac()\">Deal</button>`;\n}\nfunction updBac(){$('bacHint').innerHTML=`Betting on <b>${bacSide}</b> at ${bacSide==='player'?'2x':bacSide==='banker'?'1.95x':'9x'}`;}\nasync function playBac(){\n  const bet=getBet();if(!bet)return notify('Enter a bet amount.');\n  sfx.deal();\n  const res=await doPlay('baccarat','play',{bet,side:bacSide});\n  if(res&&res.player_cards){\n    $('bacB').innerHTML=res.banker_cards.map(c=>`<div class=\"pcard flip-in\">${c}</div>`).join('');\n    $('bacP').innerHTML=res.player_cards.map(c=>`<div class=\"pcard flip-in\">${c}</div>`).join('');\n    $('bacHint').innerHTML=`Player <b>${res.player_value}</b> - Banker <b>${res.banker_value}</b> - Winner: <b>${res.winner.toUpperCase()}</b>`;\n  }\n  showResult(res);\n}\n\n/* ============================== ROULETTE ============================== */\nlet roulChoice='red';\nfunction pnlRoulette(){\n  return `\n  <div class=\"roul-wheel\"><div class=\"ball\" id=\"roulBall\"></div><div class=\"hub\"><span>CR</span></div></div>\n  <div class=\"ctrl-row\">\n    <button class=\"ctrl on\" onclick=\"sfx.click();roulChoice='red';markRoul()\">Red</button>\n    <button class=\"ctrl\" onclick=\"sfx.click();roulChoice='black';markRoul()\">Black</button>\n    <button class=\"ctrl\" onclick=\"sfx.click();roulChoice='green';markRoul()\">Zero</button>\n    <button class=\"ctrl\" onclick=\"sfx.click();roulChoice='even';markRoul()\">Even</button>\n    <button class=\"ctrl\" onclick=\"sfx.click();roulChoice='odd';markRoul()\">Odd</button>\n    <button class=\"ctrl\" onclick=\"sfx.click();roulChoice='low';markRoul()\">1-18</button>\n    <button class=\"ctrl\" onclick=\"sfx.click();roulChoice='high';markRoul()\">19-36</button>\n  </div>\n  <div class=\"num-pad\" id=\"roulPad\"></div>\n  <button class=\"primary\" onclick=\"playRoul()\">Spin</button>`;\n}\nfunction markRoul(){\n  document.querySelectorAll('#view-game .ctrl').forEach(b=>{\n    const t=b.textContent.trim();\n    const map={'Red':'red','Black':'black','Zero':'green','Even':'even','Odd':'odd','1-18':'low','19-36':'high'};\n    b.classList.toggle('on',map[t]===roulChoice);\n  });\n  document.querySelectorAll('#roulPad button').forEach(b=>b.classList.toggle('on',b.textContent===roulChoice));\n}\nasync function playRoul(){\n  const bet=getBet();if(!bet)return notify('Enter a bet amount.');\n  const res=await doPlay('roulette','play',{bet,choice:roulChoice});\n  $('roulBall').style.transition='none';\n  $('roulBall').style.transform='rotate(0deg)';\n  void $('roulBall').offsetWidth;\n  $('roulBall').style.transition='';\n  requestAnimationFrame(()=>{\n    $('roulBall').style.transform='rotate('+(1800+Math.random()*720)+'deg)';\n  });\n  const tickI=setInterval(()=>sfx.tick(),170);\n  if(res&&res.spin!==undefined){\n    const deg=res.spin*(360/37);\n    setTimeout(()=>{$('roulBall').style.transform='rotate('+(1800+deg)+'deg)';},250);\n    setTimeout(()=>{\n      clearInterval(tickI);\n      $('resultBox').insertAdjacentHTML('afterbegin',\n        `<div class=\"result ${res.won?'win':'lose'}\"><div class=\"lbl\">NUMBER</div><div class=\"big\">${res.spin} ${res.color.toUpperCase()}</div></div>`);\n    },1600);\n  }\n  setTimeout(()=>{clearInterval(tickI);showResult(res);},4400);\n}\n\n/* ============================== HI-LO ============================== */\nfunction pnlHilo(){\n  return `\n  <div class=\"cardzone\" id=\"hiloCard\"></div>\n  <div class=\"payout-hint\" id=\"hiloHint\"></div>\n  <button class=\"primary\" id=\"hiloStart\" onclick=\"startHilo()\">Deal Card</button>`;\n}\nasync function startHilo(){\n  const bet=getBet();if(!bet)return notify('Enter a bet amount.');\n  sfx.deal();\n  const res=await doPlay('hilo','new',{bet});\n  if(!res||!res.ok){showResult(res);return;}\n  S.session={id:res.session_id,game:'hilo',bet};\n  $('hiloCard').innerHTML=`<div class=\"pcard flip-in\">${res.card}</div>`;\n  $('hiloHint').innerHTML=`Higher <b>${fmt(res.higher_mult)}x</b> - Lower <b>${fmt(res.lower_mult)}x</b> - chain <b>1x</b>`;\n  $('fairBox').innerHTML=`Seed <code>${res.fair.seed_hash}...</code>`;\n  $('hiloStart').remove();\n  $('panel').insertAdjacentHTML('beforeend',`\n    <div class=\"ctrl-row\" style=\"margin-top:14px\">\n      <button class=\"ctrl on\" onclick=\"hiloAct('higher')\">Higher</button>\n      <button class=\"ctrl\" onclick=\"hiloAct('lower')\">Lower</button>\n    </div>\n    <button class=\"primary alt\" onclick=\"hiloAct('cashout')\">Cash Out</button>`);\n}\nasync function hiloAct(act){\n  if(!S.session)return;\n  sfx.deal();\n  const res=await doPlay('hilo',act,{session_id:S.session.id});\n  if(res&&res.ok===false){showResult(res);return;}\n  if(res.card!==undefined&&res.won===undefined){\n    $('hiloCard').innerHTML=`<div class=\"pcard flip-in\">${res.card}</div>`;\n    $('hiloHint').innerHTML=`Higher <b>${fmt(res.higher_mult)}x</b> - Lower <b>${fmt(res.lower_mult)}x</b> - chain <b>${fmt(res.multiplier)}x</b> - cash out <b>${fmt(res.potential_payout)}</b>`;\n    return;\n  }\n  if(res.drawn!==undefined&&res.won===false){\n    $('hiloCard').innerHTML=`<div class=\"pcard flip-in\">${res.drawn}</div>`;\n    if(res.tie)$('hiloHint').innerHTML='Tie - round lost.';\n    S.session=null;showResult(res);return;\n  }\n  S.session=null;showResult(res);\n}\n\n/* ============================== PLINKO ============================== */\nlet plinkoRisk='low';\nfunction pnlPlinko(){\n  return `\n  <div class=\"ctrl-row\">\n    ${['low','medium','high'].map(r=>`<button class=\"ctrl ${r===plinkoRisk?'on':''}\" onclick=\"sfx.click();plinkoRisk='${r}';renderPanel(curGame())\">${r[0].toUpperCase()+r.slice(1)}</button>`).join('')}\n  </div>\n  <div class=\"plinko-board\" id=\"plinkoBoard\"></div>\n  <button class=\"primary\" onclick=\"playPlinko()\">Drop Ball</button>`;\n}\nfunction drawPlinko(){\n  const b=$('plinkoBoard');b.innerHTML='';\n  const tabs={low:[5.4,2,1.1,0.95,0.48,0.95,1.1,2,5.4],medium:[12,3.1,1.3,0.65,0.3,0.65,1.3,3.1,12],high:[20,4.5,1.6,0.35,0.18,0.35,1.6,4.5,20]}[plinkoRisk];\n  tabs.forEach((m,i)=>{\n    const d=document.createElement('div');d.className='pbucket';d.id='pb'+i;\n    d.textContent=fmt(m)+'x';d.style.left=(i*11.11)+'%';d.style.width='11.11%';\n    b.appendChild(d);\n  });\n  const cols=[1,2,3,4,5,6,7,8];\n  cols.forEach((c,ri)=>{\n    const pegs=ri+1;\n    for(let pi=0;pi<pegs;pi++){\n      const peg=document.createElement('div');peg.className='ppeg';\n      const x=(50+(pi-(pegs-1)/2)*(90/(pegs+1)))>0?50+(pi-(pegs-1)/2)*(82/(pegs+1)):50;\n      peg.style.left=x+'%';\n      peg.style.top=(30+ri*28)+'px';\n      b.appendChild(peg);\n    }\n  });\n}\nasync function playPlinko(){\n  const bet=getBet();if(!bet)return notify('Enter a bet amount.');\n  drawPlinko();\n  const board=$('plinkoBoard');\n  const ball=document.createElement('div');ball.className='pball';ball.id='pball';\n  board.appendChild(ball);\n  const res=await doPlay('plinko','play',{bet,risk:plinkoRisk});\n  const bucket=(res&&res.bucket!==undefined)?res.bucket:4;\n  let x=50,row=0;\n  const step=()=>{\n    if(row>=8){\n      setTimeout(()=>{\n        document.querySelectorAll('.pbucket').forEach((b2,i)=>b2.classList.toggle('hit',i===bucket));\n        showResult(res);\n      },240);\n      return;\n    }\n    const dir=Math.random()<0.5?-1:1;\n    const half=row+1;\n    x=50+((Math.floor((x/100)*(half))+(dir>0?0.5:-0.5))/(half))*0; // recompute below\n    // simple visual: drift left/right by a cell\n    const cellWidth=82/(half+1);\n    const curCells=Math.round((x-50)/(cellWidth/2));\n    const nxt=curCells+(dir>0?1:-1);\n    x=50+nxt*cellWidth/2;\n    row++;\n    ball.style.left=x+'%';\n    ball.style.top=(22+row*27)+'px';\n    sfx.tick();\n    setTimeout(step,130);\n  };\n  setTimeout(step,80);\n}\n\n/* ============================== KENO ============================== */\nlet kenoPicks=new Set();\nfunction pnlKeno(){\n  kenoPicks=new Set();\n  let cells='';\n  for(let i=1;i<=80;i++)cells+=`<div class=\"kcell\" id=\"k${i}\" onclick=\"toggleKeno(${i})\">${i}</div>`;\n  return `\n  <div class=\"keno-status\" id=\"kenoStatus\">Pick 1 to 10 numbers</div>\n  <div class=\"board\"><div class=\"keno-grid\">${cells}</div></div>\n  <button class=\"primary\" onclick=\"playKeno()\">Play Keno</button>`;\n}\nfunction toggleKeno(n){\n  sfx.click();\n  const el=$('k'+n);\n  if(kenoPicks.has(n)){kenoPicks.delete(n);el.classList.remove('sel');}\n  else if(kenoPicks.size<10){kenoPicks.add(n);el.classList.add('sel');}\n  $('kenoStatus').textContent=`Pick 1 to 10 numbers - selected ${kenoPicks.size}`;\n}\nasync function playKeno(){\n  if(!kenoPicks.size)return notify('Pick at least one number.');\n  const bet=getBet();if(!bet)return notify('Enter a bet amount.');\n  const res=await doPlay('keno','play',{bet,picks:[...kenoPicks]});\n  if(res&&res.drawn){\n    res.drawn.forEach((n,i)=>{\n      setTimeout(()=>{\n        const el=$('k'+n);\n        el.classList.add(kenoPicks.has(n)?'both':'hit');\n        if(kenoPicks.has(n))sfx.coin();else sfx.tick();\n      },i*260);\n    });\n    setTimeout(()=>{\n      $('kenoStatus').textContent=`Hits: ${res.hits.length} - payout ${fmt(res.multiplier)}x`;\n      showResult(res);\n    },res.drawn.length*260+300);\n  }\n}\n\n/* ============================== WHEEL ============================== */\nconst WHEEL_SEGS=[{m:0,w:30,c:'#dbeafe'},{m:0.9,w:42,c:'#bfdbfe'},{m:1.3,w:14,c:'#93c5fd'},\n  {m:1.7,w:7,c:'#60a5fa'},{m:2.6,w:4,c:'#3b82f6'},{m:4.3,w:2,c:'#2563eb'},{m:8.5,w:1,c:'#f59e0b'}];\nfunction pnlWheel(){\n  let total=WHEEL_SEGS.reduce((a,s)=>a+s.w,0);\n  let segs='',acc=0;\n  WHEEL_SEGS.forEach(s=>{\n    const a0=acc/total*360,a1=(acc+s.w)/total*360;\n    segs+=`<path d=\"${arc(115,115,110,a0,a1)}\" fill=\"${s.c}\" stroke=\"#fff\" stroke-width=\"2.5\"/>`;\n    const mid=(a0+a1)/2*Math.PI/180;\n    segs+=`<text x=\"${115+92*Math.sin(mid)}\" y=\"${115-92*Math.cos(mid)+5}\" text-anchor=\"middle\" font-family=\"Georgia,serif\" font-size=\"15\" font-weight=\"800\" fill=\"${s.c==='#f59e0b'?'#fff':'#1e3a8a'}\">${s.m}x</text>`;\n    acc+=s.w;\n  });\n  return `\n  <div class=\"wheel-wrap\">\n    <div class=\"wheel-pointer\"></div>\n    <svg class=\"wheel-svg\" id=\"wheelSvg\" viewBox=\"0 0 230 230\">${segs}</svg>\n  </div>\n  <button class=\"primary\" onclick=\"playWheel()\">Spin The Wheel</button>`;\n}\nfunction arc(cx,cy,r,a0,a1){\n  const p=(a)=>[cx+r*Math.sin(a*Math.PI/180),cy-r*Math.cos(a*Math.PI/180)];\n  const [x0,y0]=p(a0),[x1,y1]=p(a1);\n  const large=a1-a0>180?1:0;\n  return `M ${cx} ${cy} L ${x0} ${y0} A ${r} ${r} 0 ${large} 1 ${x1} ${y1} Z`;\n}\nasync function playWheel(){\n  const bet=getBet();if(!bet)return notify('Enter a bet amount.');\n  const res=await doPlay('wheel','play',{bet});\n  const idx=(res&&res.segment!==undefined)?res.segment:0;\n  let total=WHEEL_SEGS.reduce((a,s)=>a+s.w,0),acc=0;\n  for(let i=0;i<idx;i++)acc+=WHEEL_SEGS[i].w;\n  const target=(acc+WHEEL_SEGS[idx].w/2)/total*360;\n  const rot=1800+(360-target)+90;\n  const svg=$('wheelSvg');\n  svg.style.transition='none';svg.style.transform='rotate(0deg)';\n  void svg.offsetWidth;svg.style.transition='';\n  requestAnimationFrame(()=>{svg.style.transform='rotate('+rot+'deg)';});\n  const tickI=setInterval(()=>sfx.tick(),140);\n  setTimeout(()=>{clearInterval(tickI);showResult(res);},4500);\n}\n\n/* ============================== LIMBO ============================== */\nlet limboTarget=2;\nfunction pnlLimbo(){\n  const t=limboTarget,p=(1e8-t*1e6)/1e8,m=0.97/p;\n  return `\n  <div class=\"limbo-target\">\n    <label>TARGET</label>\n    <input type=\"number\" id=\"limboIn\" value=\"${limboTarget}\" step=\"0.01\" min=\"1.01\" oninput=\"limboTarget=parseFloat(this.value)||2;updLimbo()\">\n    <div class=\"val\" id=\"limboMult\">${fmt(m)}x</div>\n  </div>\n  <div class=\"payout-hint\">Win chance <b>${fmt(p*100)}%</b> - payout <b>${fmt(m)}x</b></div>\n  <div class=\"limbo-beam\">\n    <div class=\"limbo-num\" id=\"limboNum\">1.00x</div>\n    <div class=\"limbo-dot\" id=\"limboDot\" style=\"bottom:12px\"></div>\n  </div>\n  <button class=\"primary\" onclick=\"playLimbo()\">Launch</button>`;\n}\nfunction updLimbo(){\n  const t=Math.max(1.01,Math.min(100000,limboTarget));\n  const p=(1e8-t*1e6)/1e8,m=0.97/p;\n  $('limboMult').textContent=fmt(m)+'x';\n}\nasync function playLimbo(){\n  const bet=getBet();if(!bet)return notify('Enter a bet amount.');\n  const res=await doPlay('limbo','play',{bet,target:limboTarget});\n  if(res&&res.multiplier!==undefined){\n    const dot=$('limboDot'),num=$('limboNum');\n    const m=res.multiplier;\n    const target=res.target;\n    const climb=Math.min(1,(m/target));\n    dot.style.bottom=(12+climb*210)+'px';\n    const t0=Date.now();\n    const iv=setInterval(()=>{\n      const t=Math.min(1,(Date.now()-t0)/1400);\n      num.textContent=fmt(1+(m-1)*t)+'x';\n      if(t>=1){clearInterval(iv);num.textContent=fmt(m)+'x';\n        if(res.won)sfx.win();else sfx.lose();}\n    },40);\n    if(res.won)sfx.tick();\n    $('resultBox').insertAdjacentHTML('afterbegin',\n      `<div class=\"result ${res.won?'win':'lose'}\"><div class=\"lbl\">TARGET ${fmt(target)}x</div><div class=\"big\">${fmt(m)}x</div></div>`);\n  }\n  showResult(res);\n}\n\n/* ============================== COIN FLIP ============================== */\nlet coinSide='heads';\nfunction pnlCoin(){\n  return `\n  <div class=\"coin-stage\"><div class=\"coin\" id=\"coinEl\">CR</div></div>\n  <div class=\"ctrl-row\">\n    <button class=\"ctrl on\" onclick=\"sfx.click();coinSide='heads'\">Heads</button>\n    <button class=\"ctrl\" onclick=\"sfx.click();coinSide='tails'\">Tails</button>\n  </div>\n  <div class=\"payout-hint\">Payout <b>1.94x</b></div>\n  <button class=\"primary\" onclick=\"playCoin()\">Flip</button>`;\n}\nasync function playCoin(){\n  const bet=getBet();if(!bet)return notify('Enter a bet amount.');\n  sfx.coin();\n  $('coinEl').classList.remove('flip');void $('coinEl').offsetWidth;\n  $('coinEl').classList.add('flip');\n  const res=await doPlay('coinflip','play',{bet,side:coinSide});\n  if(res&&res.landed){\n    setTimeout(()=>{\n      $('coinEl').textContent=res.landed==='heads'?'H':'T';\n      $('resultBox').insertAdjacentHTML('afterbegin',\n        `<div class=\"result ${res.won?'win':'lose'}\"><div class=\"lbl\">LANDED</div><div class=\"big\">${res.landed.toUpperCase()}</div></div>`);\n    },760);\n  }\n  setTimeout(()=>showResult(res),1600);\n}\n\n/* ============================== SLOTS ============================== */\nfunction pnlSlots(){\n  return `\n  <div class=\"slots-row\">\n    <div class=\"sreel\" id=\"sr0\"><div class=\"strip\"></div></div>\n    <div class=\"sreel\" id=\"sr1\"><div class=\"strip\"></div></div>\n    <div class=\"sreel\" id=\"sr2\"><div class=\"strip\"></div></div>\n  </div>\n  <button class=\"primary\" onclick=\"playSlots()\">Spin</button>`;\n}\nconst SLOT_SYM=['C','R','7','A','K','Q','J'];\nfunction fillReel(el,stopAt){\n  const strip=el.querySelector('.strip');\n  let syms=[];\n  for(let i=0;i<12;i++)syms.push(SLOT_SYM[Math.floor(Math.random()*SLOT_SYM.length)]);\n  syms[10]=stopAt;\n  strip.innerHTML=syms.map(s=>`<span>${s}</span>`).join('');\n}\nasync function playSlots(){\n  const bet=getBet();if(!bet)return notify('Enter a bet amount.');\n  const res=await doPlay('slots','play',{bet});\n  const reel=(res&&res.reel)?res.reel:[SLOT_SYM[0],SLOT_SYM[0],SLOT_SYM[0]];\n  [0,1,2].forEach(i=>{const el=$('sr'+i);el.classList.remove('win');el.classList.add('spinning');fillReel(el,reel[i]);});\n  sfx.roll();\n  setTimeout(()=>{\n    [0,1,2].forEach(i=>{\n      const el=$('sr'+i);el.classList.remove('spinning');\n      el.querySelector('.strip').style.transform='translateY(-'+(10*104)+'px)';\n    });\n    if(res&&res.won&&res.reel&&res.reel.every(x=>x===res.reel[0])){\n      [0,1,2].forEach(i=>$('sr'+i).classList.add('win'));\n      sfx.bigwin();\n    }\n    showResult(res);\n  },1700);\n}\n\n/* ============================== WALLET / BOARD ============================== */\nfunction renderStats(){\n  const st=S.stats||{};\n  $('stGames').textContent=st.games||0;\n  $('stWins').textContent=(st.wins||0)+' / '+(st.losses||0);\n  $('stWagered').textContent=fmt(st.wagered||0);\n  $('stPaid').textContent=fmt(st.paid||0);\n}\nfunction renderWallet(){\n  renderStats();\n  const hist=S.history||[];\n  $('history').innerHTML=hist.length?hist.map(h=>{\n    const win=(h.payout||0)>0;\n    return `<div class=\"row\"><div class=\"icon-ring\">${ICON[h.game]||ICON.dice}</div>\n      <div class=\"grow\"><div class=\"t1\">${em(gameName(h.game))}</div><div class=\"t2\">${h.status}${h.created_at?' - '+h.created_at.slice(0,16).replace('T',' '):''}</div></div>\n      <div class=\"amt ${win?'pos':'neg'}\">${win?'+':'-'}${fmt(h.payout||0)}</div></div>`;\n  }).join(''):`<div class=\"empty\">No rounds yet.<br>Take a seat at one of the tables.</div>`;\n}\nfunction renderBoard(){\n  const b=S.board||[];\n  $('board').innerHTML=b.length?b.map((u,i)=>`\n    <div class=\"row\"><div class=\"rank ${i<3?'gold':''}\">${i+1}</div>\n    <div class=\"grow\"><div class=\"t1\">${em(u.first_name||u.username||'Player')}</div><div class=\"t2\">@${em(u.username||'anonymous')}</div></div>\n    <div class=\"amt\">${fmt(u.balance)}</div></div>`).join(''):`<div class=\"empty\">The leaderboard populates once players connect through the bot.</div>`;\n}\nfunction walletGo(kind){\n  if(S.demo)return notify('Deposits and withdrawals are handled by the bot after deployment.');\n  const u=S.cfg.botUsername;\n  if(!u)return notify('Bot username not configured. Set TELEGRAM_BOT_TOKEN.');\n  window.open('https://t.me/'+u+(kind==='deposit'?'?start=deposit':''),'_blank');\n  return false;\n}\nfunction gameName(g){const m={dice:'Dice',crash:'Crash',mines:'Mines',towers:'Towers',blackjack:'Blackjack',baccarat:'Baccarat',roulette:'Roulette',hilo:'Hi-Lo',plinko:'Plinko',keno:'Keno',wheel:'Wheel of Fortune',limbo:'Limbo',coinflip:'Coin Flip',slots:'Slots'};return m[g]||g;}\n\n/* ============================== GAME REGISTRY ============================== */\nconst GAMES_META=[\n  {id:'dice',name:'Dice',tag:'Instant'},\n  {id:'crash',name:'Crash',tag:'Live'},\n  {id:'mines',name:'Mines',tag:'Skill'},\n  {id:'towers',name:'Towers',tag:'Skill'},\n  {id:'blackjack',name:'Blackjack',tag:'Cards'},\n  {id:'baccarat',name:'Baccarat',tag:'Cards'},\n  {id:'roulette',name:'Roulette',tag:'Classic'},\n  {id:'hilo',name:'Hi-Lo',tag:'Cards'},\n  {id:'plinko',name:'Plinko',tag:'Instant'},\n  {id:'keno',name:'Keno',tag:'Instant'},\n  {id:'wheel',name:'Wheel of Fortune',tag:'Instant'},\n  {id:'limbo',name:'Limbo',tag:'Instant'},\n  {id:'coinflip',name:'Coin Flip',tag:'Instant'},\n  {id:'slots',name:'Slots',tag:'Classic'},\n];\n\n/* roulette number pad injection after render */\nconst _origRenderPanel=renderPanel;\nrenderPanel=function(g){\n  _origRenderPanel(g);\n  if(g.id==='roulette'){\n    let h='';\n    for(let n=0;n<=36;n++)h+=`<button onclick=\"sfx.click();roulChoice='${n}';markRoul()\">${n}</button>`;\n    $('roulPad').innerHTML=h;\n  }\n};\n\nwindow.skipIntro=skipIntro;\nboot();\n</script>\n</body>\n</html>\n"
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


async def _api_config_payload() -> JSONResponse:
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


@app.get("/api/config")
async def api_config_get(request: Request):
    accept = (request.headers.get("accept") or "").lower()
    if "text/html" in accept:
        # A human/browser opened the data endpoint - send them to the casino UI.
        return RedirectResponse(url="/", status_code=302)
    return await _api_config_payload()


@app.post("/api/config")
async def api_config_post() -> JSONResponse:
    return await _api_config_payload()


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
