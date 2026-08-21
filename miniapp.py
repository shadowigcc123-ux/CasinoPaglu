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
EMBEDDED_INDEX_HTML = "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n<meta charset=\"UTF-8\">\n<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no\">\n<title>Casino Royals</title>\n<style>\n:root{\n  --bg:#0A0E1A; --bg2:#0D1424; --panel:#111A30; --panel2:#182547; --field:#0B1322;\n  --line:rgba(201,168,76,.22);\n  --blue:#2563eb; --blue2:#3b82f6; --cyan:#22d3ee; --gold:#C9A84C; --gold2:#FFD700;\n  --ruby:#DC143C; --ink:#FFFFFF; --muted:#93A0C0;\n  --glow:0 0 22px rgba(59,130,246,.5); --glowS:0 0 12px rgba(59,130,246,.32);\n  --grad:linear-gradient(135deg,#2563eb,#1d4ed8);\n  --serif:Georgia,'Times New Roman',serif;\n  --sans:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;\n  --r:16px;\n}\n*{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent}\nhtml,body{height:100%}\nhtml{overflow-x:hidden}\nimg,svg,canvas{max-width:100%}\nbody{\n  font-family:var(--sans);\n  background:linear-gradient(180deg,#0a1122 0%,#0d1730 55%,#0a1122 100%) fixed;\n  color:var(--ink); overflow-x:hidden; max-width:100vw;\n}\nbody::before{content:\"\";position:fixed;inset:0;pointer-events:none;opacity:.05;z-index:0;\n  background-image:\n    radial-gradient(circle at 12% 18%,#3b82f6 0 9px,transparent 10px),\n    radial-gradient(circle at 34% 72%,#22d3ee 0 7px,transparent 8px),\n    radial-gradient(circle at 62% 14%,#f5b942 0 8px,transparent 9px),\n    radial-gradient(circle at 84% 58%,#3b82f6 0 10px,transparent 11px),\n    radial-gradient(circle at 22% 92%,#22d3ee 0 6px,transparent 7px),\n    radial-gradient(circle at 74% 92%,#f5b942 0 7px,transparent 8px);\n  background-size:340px 340px;\n  animation:backDrift 60s linear infinite}\n@keyframes backDrift{from{background-position:0 0}to{background-position:340px 340px}}\n.orb{position:fixed;border-radius:50%;filter:blur(70px);opacity:.16;pointer-events:none;z-index:0;animation:float 13s ease-in-out infinite}\n.orb1{width:380px;height:380px;background:radial-gradient(circle,#3b82f6,transparent 70%);top:-110px;left:-100px}\n.orb2{width:340px;height:340px;background:radial-gradient(circle,#22d3ee,transparent 70%);bottom:-90px;right:-90px;animation-delay:-6s}\n.orb3{width:280px;height:280px;background:radial-gradient(circle,#f5b942,transparent 70%);top:38%;left:58%;animation-delay:-3s;opacity:.07}\n@keyframes float{0%,100%{transform:translateY(0) scale(1)}50%{transform:translateY(26px) scale(1.06)}}\n#app{position:relative;z-index:1;max-width:560px;margin:0 auto;padding:14px 16px 110px}\n\n/* ============================ ENV LANDING ============================ */\n#envLanding{position:fixed;inset:0;z-index:98;display:flex;align-items:center;justify-content:center;padding:24px;\n  background:radial-gradient(900px 600px at 50% 30%,#12224a 0%,#0A0E1A 55%,#050a14 100%);text-align:center}\n#envLanding .env-card{max-width:360px;background:rgba(17,26,48,.92);border:1px solid rgba(201,168,76,.35);border-radius:24px;\n  padding:34px 26px;box-shadow:0 20px 60px rgba(0,0,0,.6),0 0 40px rgba(201,168,76,.15);animation:panelIn .4s ease}\n#envLanding .env-crown{width:74px;height:74px;filter:drop-shadow(0 0 18px rgba(201,168,76,.8));margin-bottom:14px;animation:crownGlow 2.8s ease-in-out infinite}\n#envLanding h2{font-family:var(--serif);font-size:24px;font-weight:800;letter-spacing:2px;color:var(--gold2);margin-bottom:10px}\n#envLanding .env-sub{font-size:13px;color:var(--muted);line-height:1.65;margin-bottom:22px}\n#envLanding .env-btn{display:block;padding:16px;border-radius:14px;background:linear-gradient(180deg,#FFD700,#C9A84C);color:#1a1206;\n  font-weight:900;letter-spacing:1.6px;font-size:14px;text-decoration:none;box-shadow:0 8px 24px rgba(201,168,76,.45);transition:.2s}\n#envLanding .env-btn:active{transform:scale(.97)}\n#envLanding .env-demo{display:block;width:100%;margin-top:12px;padding:11px;background:none;border:none;color:var(--muted);\n  font-weight:700;font-size:12px;cursor:pointer;text-decoration:underline}\n/* ============================ INTRO ============================ */\n#intro{position:fixed;inset:0;z-index:99;display:flex;align-items:center;justify-content:center;flex-direction:column;\n  background:radial-gradient(900px 600px at 50% 38%,#12224a 0%,#0a1122 55%,#050a18 100%);\n  transition:opacity .6s ease,transform .6s ease;overflow:hidden}\n#intro.gone{opacity:0;transform:translateY(-100%);pointer-events:none}\n#intro .beam{position:absolute;top:0;bottom:0;width:130px;left:-140px;transform:skewX(-18deg);\n  background:linear-gradient(90deg,transparent,rgba(96,165,250,.3),transparent);animation:beamMove 1.6s ease-in-out infinite}\n@keyframes beamMove{0%{left:-140px}100%{left:110%}}\n#intro .intro-crown{width:clamp(84px,24vw,118px);height:clamp(84px,24vw,118px);filter:drop-shadow(0 0 26px rgba(245,185,66,.75));animation:crownIn 1s cubic-bezier(.2,1.4,.4,1) backwards}\n@keyframes crownIn{from{transform:scale(.2) rotate(-14deg);opacity:0}to{transform:scale(1) rotate(0);opacity:1}}\n#intro .intro-title{margin-top:24px;font-family:var(--serif);font-size:clamp(20px,6.4vw,34px);font-weight:700;letter-spacing:2.5px;color:#fff;display:flex;white-space:nowrap;padding:0 8px;max-width:100%;overflow:hidden}\n#intro .intro-title span{display:inline-block;animation:letterIn .7s cubic-bezier(.2,1.3,.4,1) backwards;text-shadow:0 0 18px rgba(125,170,255,.8)}\n#intro .intro-title span.gold{background:linear-gradient(180deg,#ffe9a8,#f5b942 60%,#b45309);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}\n@keyframes letterIn{from{transform:translateY(30px) scale(.6);opacity:0}to{transform:none;opacity:1}}\n#intro .intro-sub{margin-top:14px;font-size:10px;letter-spacing:3px;color:#9db9ef;font-weight:700;animation:fadeUp .8s .9s backwards;padding:0 12px;text-align:center}\n#intro .intro-ring{margin-top:30px;width:150px;height:3px;border-radius:3px;overflow:hidden;background:rgba(255,255,255,.12)}\n#intro .intro-ring i{display:block;height:100%;width:40%;border-radius:3px;background:linear-gradient(90deg,#3b82f6,#22d3ee);animation:ringLoad 1.4s ease forwards}\n@keyframes ringLoad{from{width:4%}to{width:100%}}\n#intro .intro-hint{position:absolute;bottom:28px;font-size:10px;letter-spacing:1.5px;color:rgba(157,185,239,.65);font-weight:700;animation:fadeUp 1s 1.2s backwards;text-align:center;width:100%}\n@keyframes fadeUp{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}\n\n/* ============================ HEADER ============================ */\nheader{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:6px 2px 16px}\n.brand{display:flex;align-items:center;gap:12px}\n.brand svg{width:44px;height:44px;filter:drop-shadow(0 2px 8px rgba(245,185,66,.5));animation:crownGlow 2.8s ease-in-out infinite}\n@keyframes crownGlow{0%,100%{filter:drop-shadow(0 0 2px rgba(245,185,66,.35))}50%{filter:drop-shadow(0 0 12px rgba(245,185,66,.9))}}\n.brand h1{font-family:var(--serif);font-size:24px;font-weight:800;letter-spacing:1.2px;\n  background:linear-gradient(135deg,#93c5fd,#3b82f6 50%,#22d3ee);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}\n.brand small{display:block;font-size:8.5px;color:var(--muted);font-weight:800;letter-spacing:3px;-webkit-text-fill-color:var(--muted)}\n.head-right{display:flex;align-items:center;gap:8px}\n.chip{background:rgba(18,28,56,.85);backdrop-filter:blur(14px);border:1px solid var(--line);border-radius:13px;padding:8px 14px;\n  box-shadow:var(--glowS);text-align:right}\n.chip span{display:block;font-size:8px;letter-spacing:2.2px;color:var(--muted);font-weight:800}\n.chip b{font-size:18px;color:var(--gold2);font-weight:800;text-shadow:0 0 14px rgba(245,185,66,.5)}\n.chip b.pulse{animation:balPulse .45s ease}\n.chip .mode-tag{display:inline-block;margin-left:6px;padding:2px 7px;border-radius:6px;font-size:7.5px;font-weight:900;letter-spacing:1px;\n  background:rgba(245,185,66,.16);color:var(--gold2);border:1px solid rgba(245,185,66,.4);vertical-align:2px}\n.chip .mode-tag.live{background:rgba(74,222,128,.14);color:#4ade80;border-color:rgba(74,222,128,.45)}\n@keyframes balPulse{0%{transform:scale(1)}35%{transform:scale(1.16);color:#fff}100%{transform:scale(1)}}\n.icon-btn{width:40px;height:40px;border-radius:12px;border:1px solid #1d4ed8;background:#2563eb;color:#fff;\n  display:flex;align-items:center;justify-content:center;cursor:pointer;box-shadow:0 4px 14px rgba(37,99,235,.45);transition:.2s}\n.refresh-btn{width:40px;height:40px;border-radius:12px;border:1px solid #1d4ed8;background:#2563eb;color:#fff;\n  font-size:17px;cursor:pointer;transition:.25s;box-shadow:0 4px 14px rgba(37,99,235,.45);display:flex;align-items:center;justify-content:center}\n.refresh-btn:active{transform:rotate(220deg);transition:.45s}\n.refresh-btn.spin{animation:refreshSpin .7s linear}\n@keyframes refreshSpin{from{transform:rotate(0)}to{transform:rotate(360deg)}}\n\n/* ============================ BANNER ============================ */\n.banner{display:none;margin:0 0 12px;padding:11px 14px;border-radius:12px;font-size:12px;font-weight:600;line-height:1.5;border:1px solid}\n.banner.demo{display:block;border-color:rgba(245,185,66,.4);background:rgba(245,185,66,.08);color:var(--gold2)}\n.banner.err{display:block;border-color:rgba(239,68,68,.5);background:rgba(239,68,68,.1);color:#fca5a5;position:relative;padding-right:34px}\n.banner .bx{position:absolute;top:8px;right:10px;width:20px;height:20px;border-radius:50%;border:1px solid rgba(255,255,255,.25);\n  color:#fff;font-size:11px;font-weight:900;line-height:18px;text-align:center;cursor:pointer}\n.banner.warn{display:block;border-color:rgba(245,185,66,.5);background:rgba(245,185,66,.1);color:var(--gold2);position:relative;padding-right:34px}\n\n/* ============================ BOTTOM NAV ============================ */\n#tabs{position:fixed;left:50%;transform:translateX(-50%);bottom:0;z-index:40;width:100%;max-width:560px;\n  display:flex;gap:2px;background:rgba(8,14,32,.94);backdrop-filter:blur(18px);border-top:1px solid var(--line);\n  padding:8px 6px calc(10px + env(safe-area-inset-bottom, 0px))}\n#tabs button{flex:1;border:none;background:transparent;padding:7px 2px;border-radius:12px;\n  display:flex;flex-direction:column;align-items:center;gap:3px;cursor:pointer;transition:.22s}\n#tabs button svg{width:21px;height:21px;color:var(--muted);transition:.22s}\n#tabs button .nl{font-size:9.5px;font-weight:800;letter-spacing:.6px;color:var(--muted);transition:.22s}\n#tabs button.on svg{color:var(--cyan);filter:drop-shadow(0 0 8px rgba(34,211,238,.7))}\n#tabs button.on .nl{color:var(--cyan)}\n#tabs button.on{background:rgba(37,99,235,.12)}\n\n/* ============================ SECTIONS / TILES ============================ */\n.sec-title{display:flex;align-items:center;gap:10px;font-size:13px;font-weight:800;letter-spacing:1.6px;margin:6px 2px 12px;color:#93c5fd;text-transform:uppercase}\n.sec-title .bar{width:4px;height:16px;border-radius:4px;background:var(--grad);box-shadow:0 0 12px rgba(59,130,246,.7)}\n.sec-title .rule{flex:1;height:1px;background:linear-gradient(90deg,var(--line),transparent)}\n.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}\n.grid.sub{margin-bottom:8px}\n.tile{position:relative;background:rgba(18,28,56,.85);backdrop-filter:blur(12px);border:1px solid var(--line);border-radius:var(--r);\n  padding:18px 13px 15px;cursor:pointer;overflow:hidden;transition:.28s;animation:tileIn .45s ease backwards;box-shadow:0 6px 18px rgba(0,0,0,.35)}\n.tile:nth-child(1){animation-delay:.03s}.tile:nth-child(2){animation-delay:.06s}.tile:nth-child(3){animation-delay:.09s}\n.tile:nth-child(4){animation-delay:.12s}.tile:nth-child(5){animation-delay:.15s}.tile:nth-child(6){animation-delay:.18s}\n.tile:nth-child(7){animation-delay:.21s}.tile:nth-child(8){animation-delay:.24s}.tile:nth-child(9){animation-delay:.27s}\n@keyframes tileIn{from{transform:translateY(18px) scale(.95)}to{transform:none}}\n.tile:hover{transform:translateY(-4px);border-color:rgba(59,130,246,.55);box-shadow:0 12px 30px rgba(0,0,0,.5),var(--glow)}\n.tile:active{transform:scale(.97)}\n.tile .icon-ring{width:66px;height:66px;border-radius:50%;margin:0 auto 11px;display:flex;align-items:center;justify-content:center;\n  background:radial-gradient(circle at 35% 30%,#22355f,#0f1a36);border:1px solid var(--line);box-shadow:0 0 22px rgba(59,130,246,.4),inset 0 0 18px rgba(59,130,246,.12);\n  transition:.28s;animation:bob 3s ease-in-out infinite}\n.tile:nth-child(2n) .icon-ring{animation-delay:-1.5s}\n.tile:nth-child(3n) .icon-ring{animation-delay:-2.2s}\n@keyframes bob{0%,100%{transform:translateY(0)}50%{transform:translateY(-5px)}}\n.tile:hover .icon-ring{box-shadow:0 0 28px rgba(59,130,246,.7);transform:scale(1.08) rotate(-4deg)}\n.tile .icon-ring svg{width:40px;height:40px;color:#7ab3ff}\n.tile .nm{font-size:14px;font-weight:800;text-align:center;letter-spacing:.2px;color:var(--ink)}\n.tile .tg{position:absolute;top:10px;right:10px;font-size:7.5px;font-weight:800;letter-spacing:1.6px;padding:4px 9px;border-radius:99px;\n  background:rgba(37,99,235,.16);color:#93c5fd}\n.tile::after{content:\"\";position:absolute;top:0;left:-80%;width:55%;height:100%;transform:skewX(-22deg);\n  background:linear-gradient(90deg,transparent,rgba(125,170,255,.18),transparent);transition:left .7s ease;pointer-events:none}\n.tile:hover::after{left:130%}\n\n/* ============================ FEATURED HERO ============================ */\n.featured{position:relative;border-radius:24px;overflow:hidden;margin-bottom:16px;padding:28px 22px 74px;cursor:pointer;\n  background:radial-gradient(130% 120% at 82% -10%,#7c2534 0%,#4a1524 48%,#250a13 100%);\n  border:1px solid rgba(248,113,113,.4);box-shadow:0 14px 40px rgba(120,20,35,.45),inset 0 0 60px rgba(0,0,0,.35);animation:panelIn .4s ease}\n.featured .f-stars{position:absolute;inset:0;pointer-events:none;animation:twinkle 3s ease-in-out infinite;\n  background-image:radial-gradient(1.4px 1.4px at 18% 28%,rgba(255,255,255,.5) 50%,transparent 51%),\n  radial-gradient(1px 1px at 62% 18%,rgba(255,255,255,.35) 50%,transparent 51%),\n  radial-gradient(1.4px 1.4px at 78% 52%,rgba(255,255,255,.3) 50%,transparent 51%),\n  radial-gradient(1px 1px at 38% 66%,rgba(255,255,255,.4) 50%,transparent 51%)}\n.featured .f-plane{position:absolute;top:14px;left:104%;color:#fff;animation:flyAcross 7s linear infinite}\n.featured .f-plane svg{width:56px;height:56px;filter:drop-shadow(0 0 14px rgba(248,113,113,.95))}\n@keyframes flyAcross{0%{left:104%}100%{left:-64px}}\n.featured .f-tag{display:inline-block;font-size:8.5px;letter-spacing:2.4px;font-weight:900;color:#fff;\n  background:linear-gradient(135deg,#ef4444,#b91c1c);padding:5px 12px;border-radius:99px;margin-bottom:12px;box-shadow:0 0 16px rgba(239,68,68,.6)}\n.featured h2{font-family:var(--serif);font-size:32px;font-weight:800;color:#fff;letter-spacing:1.8px;text-shadow:0 0 26px rgba(248,113,113,.7)}\n.featured .f-sub{font-size:11.5px;color:rgba(255,255,255,.78);font-weight:600;margin-top:6px;max-width:72%}\n.featured .f-play{position:absolute;left:20px;bottom:16px;padding:11px 28px;border-radius:12px;background:#fff;color:#b91c1c;\n  font-weight:900;letter-spacing:2px;font-size:12.5px;box-shadow:0 6px 18px rgba(0,0,0,.45)}\n.featured .f-live{position:absolute;right:16px;bottom:18px;display:flex;align-items:center;gap:6px;color:#fca5a5;font-size:9.5px;font-weight:900;letter-spacing:1.6px}\n.featured .f-live i{width:7px;height:7px;border-radius:50%;background:#ef4444;box-shadow:0 0 8px #ef4444;animation:livePulse 1.2s infinite}\n@keyframes livePulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.5;transform:scale(1.4)}}\n\n/* ============================ CATEGORY CHIPS ============================ */\n.cat-row{display:flex;gap:8px;overflow-x:auto;padding:2px 2px 8px;margin-bottom:12px;scrollbar-width:none;-webkit-overflow-scrolling:touch}\n.cat-row::-webkit-scrollbar{display:none}\n.cat{flex-shrink:0;padding:9px 17px;border-radius:99px;border:1.5px solid rgba(59,130,246,.4);background:rgba(18,28,56,.7);color:#93c5fd;\n  font-weight:800;font-size:11.5px;letter-spacing:.4px;cursor:pointer;transition:.18s}\n.cat.on{background:#2563eb;color:#fff;border-color:#2563eb;box-shadow:0 0 16px rgba(37,99,235,.55)}\n.pos-row{display:flex;gap:5px;overflow-x:auto;padding:2px 2px 8px;margin-bottom:8px;scrollbar-width:none}\n.pos-row::-webkit-scrollbar{display:none}\n.pos{flex-shrink:0;width:34px;height:34px;border-radius:9px;border:1.5px solid rgba(59,130,246,.35);background:#1b2a4e;color:#93c5fd;\n  font-weight:800;font-size:12px;cursor:pointer;transition:.15s}\n.pos.on{background:#2563eb;color:#fff;border-color:#2563eb;box-shadow:0 0 12px rgba(37,99,235,.55)}\n\n/* ============================ PANEL ============================ */\n.panel{background:rgba(18,28,56,.88);backdrop-filter:blur(16px);border:1px solid var(--line);border-radius:22px;padding:20px;\n  box-shadow:0 18px 50px rgba(0,0,0,.5);animation:panelIn .3s ease}\n@keyframes panelIn{from{transform:translateY(20px) scale(.97);opacity:0}to{transform:none;opacity:1}}\n.panel>*{animation:panelItemIn .4s ease backwards}\n.panel>*:nth-child(1){animation-delay:.02s}.panel>*:nth-child(2){animation-delay:.07s}.panel>*:nth-child(3){animation-delay:.12s}\n.panel>*:nth-child(4){animation-delay:.17s}.panel>*:nth-child(5){animation-delay:.22s}.panel>*:nth-child(6){animation-delay:.27s}\n@keyframes panelItemIn{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:none}}\n.panel-head{display:flex;align-items:center;gap:12px;margin-bottom:16px}\n.back-btn{width:42px;height:42px;border-radius:13px;border:none;background:#2563eb;color:#fff;\n  font-size:18px;cursor:pointer;transition:.2s;font-family:var(--serif);box-shadow:0 4px 14px rgba(37,99,235,.45)}\n.panel-head .icon-ring{width:48px;height:48px;border-radius:50%;display:flex;align-items:center;justify-content:center;flex-shrink:0;\n  background:radial-gradient(circle at 35% 30%,#1e3058,#101b38);border:1px solid var(--line);box-shadow:0 0 16px rgba(59,130,246,.4)}\n.panel-head .icon-ring svg{width:25px;height:25px;color:#7ab3ff}\n.panel-head h2{font-size:19px;font-weight:800;letter-spacing:.4px;color:var(--ink)}\n.panel-head small{display:block;font-size:8.5px;color:var(--muted);font-weight:800;letter-spacing:2px;margin-top:3px}\n\n.bet-row{display:flex;align-items:center;gap:10px;margin-bottom:12px}\n.bet-row label{font-size:9.5px;letter-spacing:2px;color:var(--muted);font-weight:800}\n.bet-input{flex:1}\n.bet-input input{width:100%;padding:14px 15px;border-radius:13px;border:1.5px solid var(--line);background:var(--field);\n  font-size:17px;font-weight:800;color:var(--gold2);outline:none;transition:.2s;font-family:var(--serif)}\n.bet-input input:focus{border-color:var(--blue2);box-shadow:0 0 0 4px rgba(59,130,246,.15),var(--glow)}\n.chips{display:flex;gap:7px;margin-bottom:14px}\n.chips button{flex:1;padding:10px 0;border-radius:11px;border:1px solid #1d4ed8;background:#2563eb;color:#fff;\n  font-weight:800;font-size:12px;letter-spacing:.4px;cursor:pointer;transition:.18s;box-shadow:0 4px 12px rgba(37,99,235,.35)}\n.chips button:active{background:#1d4ed8;box-shadow:0 0 18px rgba(37,99,235,.6)}\n\n.ctrl-row{display:flex;gap:7px;flex-wrap:wrap;margin-bottom:14px}\n.ctrl{flex:1;min-width:80px;padding:12px 8px;border-radius:12px;border:1.5px solid rgba(59,130,246,.35);background:#1b2a4e;\n  font-weight:800;font-size:12.5px;color:#93c5fd;cursor:pointer;transition:.18s;text-align:center;letter-spacing:.3px}\n.ctrl.on{background:#2563eb;color:#fff;border-color:#2563eb;box-shadow:0 0 18px rgba(37,99,235,.55)}\n.payout-hint{font-size:12.5px;color:var(--muted);text-align:center;margin:2px 0 12px;font-weight:700}\n.payout-hint b{color:var(--gold2)}\n\n.primary{width:100%;padding:18px;border:1px solid #3b82f6;border-radius:15px;background:linear-gradient(180deg,#3b82f6,#2563eb 60%,#1d4ed8);color:#fff;\n  font-size:16.5px;font-weight:800;letter-spacing:1.6px;cursor:pointer;box-shadow:0 8px 26px rgba(37,99,235,.55),0 0 22px rgba(59,130,246,.3);\n  transition:.22s;position:relative;overflow:hidden;text-transform:uppercase}\n.primary:hover{box-shadow:0 10px 34px rgba(37,99,235,.7),0 0 36px rgba(59,130,246,.5);transform:translateY(-2px) scale(1.01)}\n.primary:active{transform:scale(.97)}\n.primary:disabled{opacity:.5;cursor:not-allowed;box-shadow:none}\n.primary::after{content:\"\";position:absolute;top:0;left:-80%;width:50%;height:100%;transform:skewX(-20deg);\n  background:linear-gradient(90deg,transparent,rgba(255,255,255,.35),transparent);transition:left .6s ease}\n.primary:hover::after{left:130%}\n.primary.alt{background:#1b2a4e;color:#93c5fd;border:1.5px solid #2563eb;box-shadow:0 4px 14px rgba(37,99,235,.25)}\n.replay-btn{margin-top:14px;background:linear-gradient(180deg,#3b82f6,#2563eb)!important;color:#fff!important;border:1px solid #3b82f6!important}\n.primary.heartbeat{animation:btnPulse 1.6s infinite}\n@keyframes btnPulse{0%{box-shadow:0 0 0 0 rgba(37,99,235,.55)}70%{box-shadow:0 0 0 14px rgba(37,99,235,0)}100%{box-shadow:0 0 0 0 rgba(37,99,235,0)}}\n.hint-msg{display:none;margin-top:12px;padding:11px 13px;border-radius:11px;font-size:12.5px;font-weight:700;line-height:1.5;\n  border:1px solid rgba(239,68,68,.5);background:rgba(239,68,68,.1);color:#fca5a5}\n.hint-msg.show{display:block}\n\n/* ============================ RESULT / FAIR ============================ */\n.result{margin-top:14px;padding:17px;border-radius:15px;text-align:center;animation:pop .45s cubic-bezier(.2,1.4,.4,1)}\n@keyframes pop{from{transform:scale(.85);opacity:0}to{transform:none;opacity:1}}\n.result .lbl{font-size:9.5px;letter-spacing:3px;font-weight:800;color:var(--muted)}\n.result .big{font-size:30px;font-weight:900;margin:6px 0;letter-spacing:.5px}\n.result.win{border:1px solid rgba(59,130,246,.45);background:rgba(37,99,235,.12);box-shadow:0 0 26px rgba(59,130,246,.3)}\n.result.win .big{color:#7ab3ff;text-shadow:0 0 18px rgba(59,130,246,.6)}\n.result.win .lbl{color:var(--cyan)}\n.result.lose{border:1px solid var(--line);background:rgba(10,17,34,.55)}\n.result.lose .big{color:var(--muted)}\n.result .sub{font-size:12.5px;color:var(--muted);font-weight:700}\n.result .sub b{color:var(--ink)}\n.fair{margin-top:13px;font-size:10px;color:var(--muted);text-align:center;word-break:break-all;line-height:1.6}\n.fair code{background:rgba(37,99,235,.12);border:1px solid var(--line);padding:2px 7px;border-radius:6px;color:#93c5fd;font-weight:800}\n\n/* ============================ GAME BOARDS ============================ */\n.board{background:rgba(6,12,32,.6);border:1px solid var(--line);border-radius:15px;padding:13px;margin-bottom:14px;box-shadow:inset 0 2px 12px rgba(0,0,0,.4)}\n.mines-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:7px;margin-bottom:14px}\n.mcell{aspect-ratio:1;border-radius:10px;border:1px solid rgba(59,130,246,.25);cursor:pointer;transition:.16s;\n  background:linear-gradient(160deg,#16233f,#0e1a33);display:flex;align-items:center;justify-content:center;box-shadow:0 2px 8px rgba(0,0,0,.4);\n  transform-style:preserve-3d}\n.mcell:active{transform:scale(.88)}\n.mcell.rev{animation:flipReveal .45s cubic-bezier(.3,1.3,.4,1)}\n@keyframes flipReveal{0%{transform:rotateY(90deg) scale(.85)}100%{transform:rotateY(0) scale(1)}}\n.mcell.rev{border-color:rgba(59,130,246,.6);background:#12244a;box-shadow:0 0 16px rgba(59,130,246,.45)}\n.mcell .gem{width:46%;aspect-ratio:1;transform:rotate(45deg);border-radius:3px;\n  background:linear-gradient(135deg,#93c5fd,#3b82f6 55%,#1d4ed8);box-shadow:0 0 14px rgba(59,130,246,.8);animation:gemIn .35s cubic-bezier(.2,1.5,.4,1)}\n@keyframes gemIn{from{transform:rotate(45deg) scale(0)}to{transform:rotate(45deg) scale(1)}}\n.mcell .burst{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;pointer-events:none}\n.mcell .burst i{position:absolute;width:3px;height:3px;border-radius:50%;background:#FFD700;box-shadow:0 0 8px #FFD700;\n  animation:burstFly .55s ease-out forwards}\n@keyframes burstFly{from{transform:translate(0,0) scale(1);opacity:1}to{transform:translate(var(--dx),var(--dy)) scale(.4);opacity:0}}\n.mcell .boom{width:54%;aspect-ratio:1;border-radius:50%;border:2px solid #334155;\n  background:radial-gradient(circle at 35% 30%,#64748b,#0f172a 70%)}\n.mcell.dead{border-color:rgba(239,68,68,.7);background:linear-gradient(160deg,#3a1616,#251010);box-shadow:0 0 20px rgba(239,68,68,.6);animation:shake .45s}\n@keyframes shake{0%,100%{transform:translateX(0)}20%{transform:translateX(-5px)}40%{transform:translateX(5px)}60%{transform:translateX(-4px)}80%{transform:translateX(4px)}}\n\n/* ============================ CRASH (Aviator) ============================ */\n.feed-strip{display:flex;gap:6px;overflow-x:auto;padding:2px 2px 8px;scrollbar-width:none;-webkit-overflow-scrolling:touch;max-height:26px}\n.feed-strip::-webkit-scrollbar{display:none}\n.fpill{flex-shrink:0;padding:4px 10px;border-radius:7px;font-size:10px;font-weight:800;letter-spacing:.3px;\n  background:rgba(17,26,48,.9);border:1px solid rgba(201,168,76,.3);color:#93c5fd;animation:pop .3s ease}\n.fpill b{color:var(--gold2)}\n.history-strip{display:flex;gap:6px;overflow-x:auto;padding:4px 2px 12px;margin-bottom:2px;scrollbar-width:none;-webkit-overflow-scrolling:touch}\n.history-strip::-webkit-scrollbar{display:none}\n.hpill{flex-shrink:0;padding:6px 12px;border-radius:9px;font-size:12px;font-weight:900;letter-spacing:.4px;\n  border:1px solid rgba(255,255,255,.12);background:rgba(10,17,34,.8);animation:pop .35s ease}\n.hpill.h-low{color:#f87171}.hpill.h-mid{color:#fbbf24}.hpill.h-high{color:#4ade80}\n.crash-stage{position:relative;height:330px;border-radius:18px;border:1px solid rgba(239,68,68,.4);overflow:hidden;margin-bottom:14px;\n  background:radial-gradient(130% 100% at 50% 0%,#5c1a24 0%,#38101a 55%,#1d090e 100%);box-shadow:inset 0 0 60px rgba(0,0,0,.55),0 8px 30px rgba(120,20,35,.35)}\n.crash-stage .stars{position:absolute;inset:0;pointer-events:none;animation:twinkle 3s ease-in-out infinite;\n  background-image:radial-gradient(1.5px 1.5px at 20% 30%,rgba(255,255,255,.4) 50%,transparent 51%),\n  radial-gradient(1px 1px at 65% 20%,rgba(255,255,255,.3) 50%,transparent 51%),\n  radial-gradient(1.5px 1.5px at 80% 55%,rgba(255,255,255,.25) 50%,transparent 51%),\n  radial-gradient(1px 1px at 40% 70%,rgba(255,255,255,.35) 50%,transparent 51%),\n  radial-gradient(1px 1px at 90% 85%,rgba(255,255,255,.3) 50%,transparent 51%)}\n@keyframes twinkle{0%,100%{opacity:.45}50%{opacity:1}}\n.crash-stage .gridlines{position:absolute;inset:0;opacity:.13;pointer-events:none;\n  background:repeating-linear-gradient(0deg,transparent 0 42px,rgba(248,113,113,.8) 42px 43px),\n  repeating-linear-gradient(90deg,transparent 0 42px,rgba(248,113,113,.8) 42px 43px)}\n.crash-stage canvas{position:absolute;inset:0;width:100%;height:100%}\n.crash-mult{position:absolute;top:14px;left:0;right:0;text-align:center;font-size:clamp(30px,11vw,46px);font-weight:900;color:#fff;\n  text-shadow:0 0 26px rgba(248,113,113,.95),0 0 8px rgba(255,255,255,.5),0 2px 6px rgba(0,0,0,.5);z-index:3;letter-spacing:.5px;\n  transition:color .3s,text-shadow .3s}\n.crash-mult.m-green{color:#4ade80;text-shadow:0 0 26px rgba(74,222,128,.9)}\n.crash-mult.m-yellow{color:#fbbf24;text-shadow:0 0 26px rgba(251,191,36,.9)}\n.crash-mult.m-red{color:#f87171;text-shadow:0 0 26px rgba(248,113,113,.95)}\n.crash-bet{position:absolute;bottom:12px;left:14px;z-index:3;font-size:11.5px;font-weight:800;color:#fff;\n  background:rgba(0,0,0,.55);border:1px solid rgba(248,113,113,.45);border-radius:9px;padding:6px 12px;backdrop-filter:blur(4px)}\n.opt-row{display:flex;gap:8px;align-items:center;margin-bottom:10px;flex-wrap:wrap}\n.opt-row label{font-size:9.5px;letter-spacing:1.4px;color:var(--muted);font-weight:800;white-space:nowrap}\n.opt-row input[type=number]{width:74px;padding:9px 10px;border-radius:9px;border:1.5px solid var(--line);background:var(--field);\n  font-size:13px;font-weight:800;color:var(--gold2);outline:none;font-family:var(--serif)}\n.opt-row .toggle{display:flex;align-items:center;gap:6px;cursor:pointer;user-select:none}\n.opt-row .toggle input{display:none}\n.opt-row .toggle .tknob{width:38px;height:22px;border-radius:99px;background:#1b2a4e;border:1px solid var(--line);position:relative;transition:.2s}\n.opt-row .toggle .tknob::after{content:\"\";position:absolute;top:2px;left:2px;width:16px;height:16px;border-radius:50%;background:#93a0c0;transition:.2s}\n.opt-row .toggle input:checked + .tknob{background:#2563eb;border-color:#3b82f6}\n.opt-row .toggle input:checked + .tknob::after{left:18px;background:#fff;box-shadow:0 0 8px rgba(255,255,255,.7)}\n.crash-stage.boom{animation:stageShake .5s}\n.crash-stage .countdown{position:absolute;inset:0;z-index:5;display:flex;align-items:center;justify-content:center;\n  background:rgba(10,14,26,.42)}\n.crash-stage .countdown b{font-size:clamp(64px,18vw,96px);font-weight:900;color:#FFD700;text-shadow:0 0 40px rgba(255,215,0,.9);\n  animation:cdPop .6s cubic-bezier(.2,1.4,.4,1)}\n.crash-stage .countdown.go b{color:#00FF88;text-shadow:0 0 40px rgba(0,255,136,.9)}\n@keyframes cdPop{from{transform:scale(1.6);opacity:0}to{transform:scale(1);opacity:1}}\n.crash-idle{position:absolute;left:50%;bottom:14px;transform:translateX(-50%);width:74px;height:74px;z-index:3;\n  filter:drop-shadow(0 0 16px rgba(248,113,113,.7));animation:idleBob 1.6s ease-in-out infinite}\n.crash-idle svg{width:100%;height:100%}\n@keyframes idleBob{0%,100%{transform:translateX(-50%) translateY(0)}50%{transform:translateX(-50%) translateY(-9px)}}\n@keyframes stageShake{0%,100%{transform:translate(0)}15%{transform:translate(-7px,3px)}35%{transform:translate(6px,-4px)}55%{transform:translate(-5px,2px)}75%{transform:translate(4px,-2px)}}\n\n/* ============================ CARDS ============================ */\n.cardzone{display:flex;justify-content:center;gap:10px;flex-wrap:wrap;margin:8px 0 14px;min-height:84px}\n.pcard{width:60px;height:84px;border-radius:10px;background:linear-gradient(160deg,#ffffff,#f1f6ff);border:1.5px solid rgba(59,130,246,.35);\n  display:flex;align-items:center;justify-content:center;font-family:var(--serif);font-size:26px;font-weight:700;color:#0f172a;\n  box-shadow:0 6px 16px rgba(0,0,0,.5);animation:dealIn .35s ease}\n@keyframes dealIn{from{transform:translateY(-18px) rotate(-7deg) scale(.8);opacity:0}to{transform:none;opacity:1}}\n.pcard.back{background:repeating-linear-gradient(45deg,#3b82f6 0 7px,#2563eb 7px 14px);border:1.5px solid #1d4ed8}\n.pcard.flip-in{animation:flipIn .45s ease}\n@keyframes flipIn{0%{transform:rotateY(90deg)}100%{transform:rotateY(0)}}\n.hand-label{font-size:9px;font-weight:800;letter-spacing:2.4px;color:var(--muted);text-align:center;margin:6px 0 3px}\n\n/* ============================ KENO ============================ */\n.keno-grid{display:grid;grid-template-columns:repeat(10,1fr);gap:4px;margin-bottom:14px}\n.kcell{aspect-ratio:1;border-radius:7px;border:1px solid rgba(59,130,246,.22);background:#16233f;font-family:var(--serif);\n  font-size:11px;font-weight:700;color:var(--muted);cursor:pointer;transition:.14s;display:flex;align-items:center;justify-content:center}\n.kcell.sel{background:#2563eb;color:#fff;border-color:transparent;box-shadow:0 0 12px rgba(37,99,235,.6);animation:kpop .2s}\n.kcell.hit{border-color:rgba(245,185,66,.6);color:var(--gold2);background:#1b2a4e}\n.kcell.both{background:linear-gradient(135deg,#fbbf24,#f59e0b);color:#1a1206;animation:kpop .4s}\n@keyframes kpop{0%{transform:scale(.4)}70%{transform:scale(1.15)}100%{transform:scale(1)}}\n\n/* ============================ PLINKO ============================ */\n.plinko-board{position:relative;height:300px;border-radius:15px;border:1px solid var(--line);background:linear-gradient(180deg,#0e1a33,#0a1226);\n  overflow:hidden;margin-bottom:14px;box-shadow:inset 0 2px 12px rgba(0,0,0,.5)}\n.ppeg{position:absolute;width:9px;height:9px;border-radius:50%;background:var(--grad);box-shadow:0 0 7px rgba(59,130,246,.7);transform:translate(-50%,-50%)}\n.pball{position:absolute;top:22px;left:50%;width:14px;height:14px;border-radius:50%;margin-left:-7px;\n  background:radial-gradient(circle at 35% 30%,#fde68a,#f59e0b 60%,#b45309);box-shadow:0 0 14px rgba(245,158,11,.95);z-index:2;transition:left .5s cubic-bezier(.4,.2,.5,1),top .5s cubic-bezier(.4,.2,.5,1)}\n.pbucket{position:absolute;bottom:0;height:34px;display:flex;align-items:center;justify-content:center;\n  font-size:9px;font-weight:800;color:var(--muted);border-top:1px solid var(--line);background:rgba(18,28,56,.85);letter-spacing:.4px}\n.pbucket.hit{background:linear-gradient(135deg,#fbbf24,#f59e0b);color:#1a1206;box-shadow:0 0 18px rgba(245,158,11,.6)}\n.heat-row{display:flex;gap:4px;margin-bottom:10px}\n.heat-cell{flex:1;height:14px;border-radius:4px;background:#1b2a4e;border:1px solid var(--line);position:relative}\n.heat-cell .hfill{position:absolute;left:0;bottom:0;right:0;background:linear-gradient(180deg,#fbbf24,#f59e0b);border-radius:3px;transition:height .3s}\n.heat-cell span{position:absolute;top:-14px;left:50%;transform:translateX(-50%);font-size:8px;color:var(--muted);font-weight:800}\n\n/* ============================ WHEEL ============================ */\n.wheel-wrap{position:relative;width:225px;height:225px;margin:4px auto 16px}\n.wheel-pointer{position:absolute;top:-10px;left:50%;transform:translateX(-50%);z-index:3;width:0;height:0;\n  border-left:10px solid transparent;border-right:10px solid transparent;border-top:16px solid var(--cyan);filter:drop-shadow(0 2px 4px rgba(34,211,238,.6))}\n.wheel-svg{width:100%;height:100%;transition:transform 4.4s cubic-bezier(.15,.85,.25,1);filter:drop-shadow(0 10px 22px rgba(0,0,0,.6))}\n\n/* ============================ ROULETTE ============================ */\n.roul-wheel{width:205px;height:205px;border-radius:50%;margin:6px auto 16px;position:relative;\n  box-shadow:0 0 0 6px #0d1830,0 0 0 8px rgba(59,130,246,.5),0 12px 30px rgba(0,0,0,.6)}\n.roul-wheel:before{content:\"\";position:absolute;inset:0;border-radius:50%;\n  background:conic-gradient(#dc2626 0 18deg,#111827 18deg 36deg,#dc2626 36deg 54deg,#111827 54deg 72deg,\n  #dc2626 72deg 90deg,#111827 90deg 108deg,#dc2626 108deg 126deg,#111827 126deg 144deg,\n  #dc2626 144deg 162deg,#111827 162deg 180deg,#dc2626 180deg 198deg,#111827 198deg 216deg,\n  #dc2626 216deg 234deg,#111827 234deg 252deg,#dc2626 252deg 270deg,#111827 270deg 288deg,\n  #dc2626 288deg 306deg,#111827 306deg 324deg,#16a34a 324deg 342deg,#111827 342deg 360deg)}\n.roul-wheel .ball{position:absolute;inset:0;transition:transform 4.2s cubic-bezier(.12,.8,.25,1);z-index:2}\n.roul-wheel .ball:before{content:\"\";position:absolute;top:7px;left:50%;transform:translateX(-50%);width:14px;height:14px;\n  border-radius:50%;background:radial-gradient(circle at 35% 30%,#fff,#93c5fd 45%,#2563eb);box-shadow:0 0 10px rgba(59,130,246,.9)}\n.roul-wheel .hub{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;z-index:3}\n.roul-wheel .hub span{width:54px;height:54px;border-radius:50%;border:1px solid rgba(59,130,246,.5);background:var(--grad);\n  display:flex;align-items:center;justify-content:center;font-weight:800;font-size:12px;color:#fff;letter-spacing:1px;box-shadow:var(--glow)}\n.num-pad{display:grid;grid-template-columns:repeat(6,1fr);gap:5px;margin-bottom:12px}\n.num-pad button{padding:9px 0;border-radius:8px;border:1px solid rgba(59,130,246,.3);background:#1b2a4e;font-weight:800;font-size:11.5px;color:#93c5fd;cursor:pointer;transition:.15s}\n.num-pad button.on{background:#2563eb;color:#fff;border-color:#2563eb;box-shadow:0 0 14px rgba(37,99,235,.55)}\n\n/* ============================ COIN ============================ */\n.coin-stage{display:flex;justify-content:center;margin:10px 0 16px;perspective:600px}\n.coin{width:106px;height:106px;border-radius:50%;border:3px solid #b45309;display:flex;align-items:center;justify-content:center;\n  font-family:var(--serif);font-weight:800;font-size:25px;color:#7c4a03;background:radial-gradient(circle at 35% 30%,#fef3c7,#f59e0b 60%,#b45309);\n  box-shadow:0 14px 30px rgba(0,0,0,.5),0 0 22px rgba(245,158,11,.5);transform-style:preserve-3d}\n.coin.flip{animation:coinFlip 1.5s ease-in-out}\n@keyframes coinFlip{0%{transform:rotateY(0)}50%{transform:rotateY(1080deg)}100%{transform:rotateY(2160deg)}}\n\n/* ============================ SLOTS ============================ */\n.slots-row{display:flex;justify-content:center;gap:12px;margin-bottom:16px;padding:14px;\n  background:rgba(6,12,32,.65);border:1px solid var(--line);border-radius:15px;box-shadow:inset 0 2px 12px rgba(0,0,0,.5)}\n.sreel{width:84px;height:102px;border-radius:12px;border:2px solid rgba(59,130,246,.5);background:#0e1a33;overflow:hidden;position:relative;\n  box-shadow:0 0 18px rgba(59,130,246,.35)}\n.sreel .strip{position:absolute;left:0;right:0;display:flex;flex-direction:column;align-items:center;transition:transform .7s cubic-bezier(.2,.8,.3,1)}\n.sreel .strip span{height:102px;display:flex;align-items:center;justify-content:center;font-family:var(--serif);font-size:42px;font-weight:800;color:#7ab3ff;text-shadow:0 0 16px rgba(59,130,246,.5)}\n.sreel.spinning .strip{animation:sroll .3s linear infinite}\n@keyframes sroll{from{transform:translateY(0)}to{transform:translateY(-408px)}}\n.sreel.win{animation:winGlow .6s ease 3}\n@keyframes winGlow{0%,100%{box-shadow:0 0 18px rgba(59,130,246,.35)}50%{box-shadow:0 0 40px rgba(245,158,11,.9);border-color:#f59e0b}}\n\n/* ============================ DICE ============================ */\n.dice-stage{display:flex;justify-content:center;align-items:center;margin:6px 0 16px}\n.dice-num{width:116px;height:116px;border-radius:24px;border:2px solid rgba(59,130,246,.5);background:#0e1a33;\n  display:flex;align-items:center;justify-content:center;font-size:50px;font-weight:900;color:#7ab3ff;\n  box-shadow:0 10px 26px rgba(0,0,0,.5),0 0 28px rgba(59,130,246,.35);text-shadow:0 0 18px rgba(59,130,246,.7);transition:transform .2s}\n.dice-num.rolling{animation:diceShake .5s linear infinite}\n@keyframes diceShake{0%{transform:rotate(0) scale(1)}25%{transform:rotate(9deg) scale(1.06)}50%{transform:rotate(-9deg) scale(1.06)}75%{transform:rotate(6deg) scale(1.02)}100%{transform:rotate(0) scale(1)}}\n.dice-num.land{animation:landPop .5s cubic-bezier(.2,1.6,.4,1)}\n@keyframes landPop{0%{transform:scale(1.25)}100%{transform:scale(1)}}\n\n/* ============================ LIMBO ============================ */\n.limbo-beam{position:relative;height:260px;border-radius:15px;border:1px solid var(--line);overflow:hidden;margin-bottom:14px;\n  background:linear-gradient(180deg,#0b1e4b 0%,#1e3a8a 55%,#2563eb 100%);box-shadow:inset 0 0 40px rgba(0,0,0,.4)}\n.limbo-dot{position:absolute;left:50%;width:16px;height:16px;margin-left:-8px;border-radius:50%;\n  background:radial-gradient(circle at 35% 30%,#fff,#7ab3ff 50%,#2563eb);box-shadow:0 0 16px rgba(125,170,255,1);transition:bottom 1s cubic-bezier(.3,.5,.4,1)}\n.limbo-num{position:absolute;top:12px;left:0;right:0;text-align:center;font-size:36px;font-weight:900;color:#fff;text-shadow:0 0 20px rgba(125,170,255,.9)}\n.limbo-target{display:flex;gap:8px;align-items:center;margin-bottom:12px}\n.limbo-target label{font-size:9.5px;letter-spacing:1.6px;color:var(--muted);font-weight:800}\n.limbo-target input{flex:1;padding:13px 14px;border-radius:12px;border:1.5px solid var(--line);background:var(--field);font-size:16px;font-weight:800;color:var(--gold2);outline:none}\n.limbo-target input:focus{border-color:var(--blue2);box-shadow:0 0 0 4px rgba(59,130,246,.14)}\n.limbo-target .val{min-width:58px;text-align:center;font-weight:800;color:#7ab3ff;border:1.5px solid var(--line);border-radius:12px;padding:13px 0;font-size:15px;background:var(--field)}\n.keno-status{font-size:11.5px;color:var(--muted);font-weight:800;letter-spacing:.5px;text-align:center;margin-bottom:9px}\n.range-row{display:flex;align-items:center;gap:10px;margin-bottom:12px}\n.range-row input[type=range]{flex:1;accent-color:var(--blue)}\n.range-row .val{min-width:54px;text-align:center;font-weight:800;color:#7ab3ff;border:1.5px solid var(--line);border-radius:10px;padding:8px 0;font-size:14px;background:var(--field)}\n\n/* ============================ LISTS ============================ */\n.list{display:flex;flex-direction:column;gap:10px}\n.row{display:flex;align-items:center;gap:12px;background:rgba(18,28,56,.85);backdrop-filter:blur(12px);border:1px solid var(--line);\n  border-radius:14px;padding:13px 15px;box-shadow:0 4px 14px rgba(0,0,0,.35)}\n.row .icon-ring{width:40px;height:40px;border-radius:50%;display:flex;align-items:center;justify-content:center;flex-shrink:0;\n  background:radial-gradient(circle at 35% 30%,#1e3058,#101b38);border:1px solid var(--line);box-shadow:0 0 12px rgba(59,130,246,.3)}\n.row .icon-ring svg{width:21px;height:21px;color:#7ab3ff}\n.row .grow{flex:1;min-width:0}\n.row .t1{font-weight:800;font-size:13.5px;color:var(--ink)}\n.row .t2{font-size:10.5px;color:var(--muted);font-weight:700;margin-top:2px}\n.row .amt{font-weight:900;font-size:14px}\n.row .amt.pos{color:#4ade80}.row .amt.neg{color:var(--muted)}\n.rank{width:30px;height:30px;border-radius:9px;display:flex;align-items:center;justify-content:center;\n  font-weight:900;font-size:13px;border:1px solid var(--line);color:#93c5fd;background:#0e1a33;flex-shrink:0}\n.rank.gold{background:linear-gradient(135deg,#fbbf24,#f59e0b);color:#1a1206;border-color:transparent;box-shadow:0 0 14px rgba(245,158,11,.5)}\n.empty{padding:38px 10px;text-align:center;color:var(--muted);font-weight:700;font-size:13px;line-height:1.7}\n.fair-card{background:rgba(18,28,56,.85);backdrop-filter:blur(12px);border:1px solid var(--line);border-radius:16px;padding:18px;margin-bottom:13px;box-shadow:0 4px 14px rgba(0,0,0,.35)}\n.fair-card h3{font-size:15px;font-weight:800;color:#93c5fd;margin-bottom:8px;letter-spacing:.4px}\n.fair-card p{font-size:12.5px;color:var(--muted);line-height:1.7}\n.fair-card code{background:rgba(37,99,235,.12);border:1px solid var(--line);padding:1px 6px;border-radius:5px;color:#93c5fd;font-weight:800}\n.wallet-actions{display:flex;gap:11px;margin-bottom:16px}\n.wallet-actions a,.wallet-actions button{flex:1;text-decoration:none;text-align:center;padding:15px;border-radius:13px;\n  font-weight:800;font-size:12.5px;letter-spacing:1.2px;border:none;cursor:pointer;text-transform:uppercase}\n.wa-dep{background:linear-gradient(180deg,#3b82f6,#2563eb);color:#fff;box-shadow:0 6px 18px rgba(37,99,235,.5)}\n.wa-wd{background:#1b2a4e;color:#93c5fd;border:1.5px solid #2563eb!important;box-shadow:0 4px 14px rgba(37,99,235,.25)}\n.stats-row{display:grid;grid-template-columns:1fr 1fr;gap:11px;margin-bottom:16px}\n.stat{background:rgba(18,28,56,.85);backdrop-filter:blur(12px);border:1px solid var(--line);border-radius:14px;padding:14px;text-align:center;box-shadow:0 4px 14px rgba(0,0,0,.35)}\n.stat b{display:block;font-size:19px;color:var(--gold2);margin-bottom:4px;font-weight:900;text-shadow:0 0 12px rgba(245,185,66,.4)}\n.stat span{font-size:8.5px;color:var(--muted);font-weight:800;letter-spacing:1.8px}\n.stat.small b{font-size:15px}\n.chart-box{background:rgba(18,28,56,.85);border:1px solid var(--line);border-radius:14px;padding:14px;margin-bottom:16px}\n.chart-box h4{font-size:11px;font-weight:800;letter-spacing:1.6px;color:#93c5fd;margin-bottom:10px}\n.chart{display:flex;align-items:flex-end;gap:6px;height:96px}\n.chart .bar{flex:1;border-radius:5px 5px 0 0;background:linear-gradient(180deg,#3b82f6,#1d4ed8);position:relative;min-height:3px;\n  animation:barGrow .6s cubic-bezier(.2,1.2,.4,1) backwards}\n.chart .bar.win{background:linear-gradient(180deg,#FFD700,#C9A84C)}\n@keyframes barGrow{from{height:0!important}}\n.chart .bar span{position:absolute;top:-15px;left:50%;transform:translateX(-50%);font-size:7.5px;color:var(--muted);font-weight:800}\n.pergame .row .amt.pos{color:#4ade80}\n\n/* ============================ PROFILE ============================ */\n.profile-card{display:flex;align-items:center;gap:13px;background:rgba(18,28,56,.85);backdrop-filter:blur(14px);\n  border:1px solid var(--line);border-radius:17px;padding:15px;margin-bottom:16px;box-shadow:0 6px 22px rgba(0,0,0,.4);position:relative;overflow:hidden}\n.profile-card::after{content:\"\";position:absolute;top:0;left:-90%;width:60%;height:100%;transform:skewX(-22deg);\n  background:linear-gradient(90deg,transparent,rgba(125,170,255,.18),transparent);animation:profileShine 4.5s ease infinite;pointer-events:none}\n@keyframes profileShine{0%,60%{left:-90%}100%{left:150%}}\n.profile-avatar{width:56px;height:56px;border-radius:50%;border:2.5px solid #2563eb;box-shadow:0 0 18px rgba(37,99,235,.5);\n  display:flex;align-items:center;justify-content:center;font-weight:900;font-size:21px;color:#fff;flex-shrink:0;\n  background:var(--grad);overflow:hidden;position:relative}\n.profile-avatar img{width:100%;height:100%;object-fit:cover}\n.profile-name{font-size:15.5px;font-weight:800;color:var(--ink)}\n.profile-name .prem{margin-left:6px;font-size:10px;padding:2px 7px;border-radius:99px;background:linear-gradient(135deg,#fbbf24,#f59e0b);color:#1a1206;font-weight:800}\n.profile-sub{font-size:11px;color:var(--muted);font-weight:700;margin-top:3px}\n\n/* ============================ MISC ============================ */\n.ripple{position:absolute;border-radius:50%;background:rgba(255,255,255,.5);transform:scale(0);animation:rippleA .6s ease-out;pointer-events:none}\n@keyframes rippleA{to{transform:scale(3);opacity:0}}\n.confetti{position:fixed;top:-16px;z-index:60;width:9px;height:14px;border-radius:2px;pointer-events:none;animation:confFall linear forwards}\n@keyframes confFall{to{transform:translateY(110vh) rotate(720deg);opacity:.9}}\n#toast{position:fixed;left:50%;bottom:96px;transform:translateX(-50%) translateY(80px);z-index:50;\n  background:#0f172a;color:#fff;padding:13px 22px;border-radius:14px;font-size:13px;font-weight:700;\n  box-shadow:0 10px 30px rgba(0,0,0,.5),0 0 20px rgba(59,130,246,.45);transition:transform .35s cubic-bezier(.2,1.2,.4,1);max-width:86%;text-align:center}\n#toast.show{transform:translateX(-50%) translateY(0)}\n.view{display:none}\n.view.on{display:block;animation:viewIn .3s ease}\n@keyframes viewIn{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}\n</style>\n</head>\n<body>\n<div class=\"orb orb1\"></div><div class=\"orb orb2\"></div><div class=\"orb orb3\"></div>\n\n<!-- INTRO -->\n<div id=\"envLanding\" style=\"display:none\">\n  <div class=\"env-card\">\n    <svg class=\"env-crown\" viewBox=\"0 0 24 24\" fill=\"none\"><path d=\"M2.5 7.5L6 11l6-7 6 7 3.5-3.5L20 20H4L2.5 7.5z\" fill=\"#C9A84C\"/><rect x=\"3.4\" y=\"16.6\" width=\"17.2\" height=\"2.6\" rx=\"1.3\" fill=\"#FFD700\"/></svg>\n    <h2>CASINO ROYALS</h2>\n    <p class=\"env-sub\">This is a Telegram Mini App. Open it inside Telegram to play with your real wallet.</p>\n    <a class=\"env-btn\" id=\"envBtn\" href=\"https://t.me/CasinoRoyalsBot\" target=\"_blank\">Open in Telegram</a>\n    <button class=\"env-demo\" id=\"envDemo\">Continue with demo mode</button>\n  </div>\n</div>\n\n<div id=\"intro\">\n  <div class=\"beam\"></div>\n  <svg class=\"intro-crown\" viewBox=\"0 0 24 24\" width=\"118\" height=\"118\" fill=\"none\" stroke=\"#fbbf24\" stroke-width=\"1.4\" stroke-linejoin=\"round\">\n    <path d=\"M2.5 7.5L6 11l6-7 6 7 3.5-3.5L20 20H4L2.5 7.5z\" fill=\"url(#g1)\"/>\n    <rect x=\"3.4\" y=\"16.6\" width=\"17.2\" height=\"2.6\" rx=\"1.3\" fill=\"#f59e0b\"/>\n    <circle cx=\"12\" cy=\"8.4\" r=\"1.1\" fill=\"#fff\"/>\n    <defs><linearGradient id=\"g1\" x1=\"2\" y1=\"4\" x2=\"22\" y2=\"20\"><stop offset=\"0\" stop-color=\"#ffe9a8\"/><stop offset=\".55\" stop-color=\"#f59e0b\"/><stop offset=\"1\" stop-color=\"#b45309\"/></linearGradient></defs>\n  </svg>\n  <div class=\"intro-title\" id=\"introTitle\"></div>\n  <div class=\"intro-sub\">ROYAL TABLE GAMES</div>\n  <div class=\"intro-ring\"><i></i></div>\n  <div class=\"intro-hint\">TAP TO SKIP</div>\n</div>\n\n<div id=\"app\">\n  <header>\n    <div class=\"brand\">\n      <svg viewBox=\"0 0 24 24\" width=\"34\" height=\"34\" fill=\"none\" stroke=\"#f59e0b\" stroke-width=\"1.5\" stroke-linejoin=\"round\">\n        <path d=\"M2.5 7.5L6 11l6-7 6 7 3.5-3.5L20 20H4L2.5 7.5z\" fill=\"#fbbf24\"/>\n        <rect x=\"3.4\" y=\"16.6\" width=\"17.2\" height=\"2.6\" rx=\"1.3\" fill=\"#f59e0b\"/>\n      </svg>\n      <div>\n        <h1>CASINO ROYALS</h1>\n        <small>TABLE GAMES - V2</small>\n      </div>\n    </div>\n    <div class=\"head-right\">\n      <div class=\"chip\"><span>BALANCE</span><b id=\"bal\">0</b><span class=\"mode-tag\" id=\"modeTag\">DEMO</span></div>\n      <button class=\"refresh-btn\" id=\"refreshBtn\" onclick=\"refreshBalance()\" aria-label=\"refresh\"></button>\n      <button class=\"icon-btn\" id=\"muteBtn\" onclick=\"toggleMute()\" aria-label=\"sound\"></button>\n    </div>\n  </header>\n\n  <div class=\"banner demo\" id=\"bannerDemo\">DEMO MODE - local balance. Open the casino from your bot's menu button inside Telegram to load your real wallet.</div>\n  <div class=\"banner err\" id=\"bannerErr\" style=\"display:none\"></div>\n  <div class=\"banner warn\" id=\"bannerWarn\" style=\"display:none\"></div>\n\n\n  <div class=\"view on\" id=\"view-games\">\n    <div id=\"grid\"></div>\n    <div class=\"cat-row\" id=\"catRow\">\n      <button class=\"cat on\" data-cat=\"all\" onclick=\"setCat('all')\">All</button>\n    </div>\n  </div>\n\n  <div class=\"view\" id=\"view-game\"><div class=\"panel\" id=\"panel\"></div></div>\n\n  <div class=\"view\" id=\"view-spin\">\n    <div class=\"sec-title\"><span class=\"bar\"></span>Crash Arena<span class=\"rule\"></span></div>\n    <div id=\"spinPanel\"></div>\n  </div>\n\n  <div class=\"view\" id=\"view-wallet\">\n    <div class=\"sec-title\"><span class=\"bar\"></span>Wallet<span class=\"rule\"></span></div>\n    <div class=\"profile-card\" id=\"profileCard\">\n      <div class=\"profile-avatar\" id=\"profileAvatar\">G</div>\n      <div style=\"flex:1;min-width:0\">\n        <div class=\"profile-name\" id=\"profileName\">Guest</div>\n        <div class=\"profile-sub\" id=\"profileSub\">Connect from Telegram to load your profile</div>\n      </div>\n    </div>\n    <div class=\"wallet-actions\">\n      <a class=\"wa-dep\" id=\"depBtn\" href=\"#\" onclick=\"return walletGo('deposit')\">Deposit</a>\n      <button class=\"wa-wd\" id=\"wdBtn\" onclick=\"walletGo('withdraw')\">Withdraw</button>\n    </div>\n    <div class=\"stats-row\">\n      <div class=\"stat\"><b id=\"stWagered\">0</b><span>WAGERED</span></div>\n      <div class=\"stat\"><b id=\"stNet\">0</b><span>NET P/L</span></div>\n      <div class=\"stat\"><b id=\"stGames\">0</b><span>GAMES</span></div>\n      <div class=\"stat\"><b id=\"stStreak\">0</b><span>STREAK</span></div>\n    </div>\n    <div class=\"chart-box\">\n      <h4>LAST 7 DAYS - WAGERED vs PAID</h4>\n      <div class=\"chart\" id=\"walletChart\"></div>\n    </div>\n    <div class=\"sec-title\"><span class=\"bar\"></span>Per-Game Stats<span class=\"rule\"></span></div>\n    <div class=\"list\" id=\"perGame\"></div>\n    <div class=\"sec-title\" style=\"margin-top:16px\"><span class=\"bar\"></span>Recent Rounds<span class=\"rule\"></span></div>\n    <div class=\"list\" id=\"history\"></div>\n  </div>\n\n  <div class=\"view\" id=\"view-board\">\n    <div class=\"sec-title\"><span class=\"bar\"></span>Leaderboard<span class=\"rule\"></span></div>\n    <div class=\"cat-row\" id=\"lbPeriod\">\n      <button class=\"cat\" data-p=\"daily\" onclick=\"lbSet('period','daily')\">Daily</button>\n      <button class=\"cat\" data-p=\"weekly\" onclick=\"lbSet('period','weekly')\">Weekly</button>\n      <button class=\"cat\" data-p=\"monthly\" onclick=\"lbSet('period','monthly')\">Monthly</button>\n      <button class=\"cat on\" data-p=\"all\" onclick=\"lbSet('period','all')\">All Time</button>\n    </div>\n    <div class=\"cat-row\" id=\"lbMetric\">\n      <button class=\"cat on\" data-m=\"profit\" onclick=\"lbSet('metric','profit')\">Profit</button>\n      <button class=\"cat\" data-m=\"games\" onclick=\"lbSet('metric','games')\">Games</button>\n      <button class=\"cat\" data-m=\"multiplier\" onclick=\"lbSet('metric','multiplier')\">Multiplier</button>\n    </div>\n    <div class=\"list\" id=\"board\"></div>\n  </div>\n\n  <div class=\"view\" id=\"view-admin\">\n    <div class=\"sec-title\"><span class=\"bar\"></span>Admin Dashboard<span class=\"rule\"></span></div>\n    <div class=\"stats-row\">\n      <div class=\"stat\"><b id=\"adUsers\">0</b><span>USERS</span></div>\n      <div class=\"stat\"><b id=\"adBalance\">0</b><span>BALANCE</span></div>\n      <div class=\"stat\"><b id=\"adGames\">0</b><span>GAMES</span></div>\n      <div class=\"stat\"><b id=\"adEdge\">0</b><span>HOUSE EDGE</span></div>\n    </div>\n    <div class=\"sec-title\"><span class=\"bar\"></span>Per-Game Totals<span class=\"rule\"></span></div>\n    <div class=\"list\" id=\"adPerGame\"></div>\n    <div class=\"sec-title\" style=\"margin-top:16px\"><span class=\"bar\"></span>Recent Rounds<span class=\"rule\"></span></div>\n    <div class=\"list\" id=\"adRecent\"></div>\n  </div>\n\n  <div class=\"view\" id=\"view-fair\">\n    <div class=\"sec-title\"><span class=\"bar\"></span>Provably Fair<span class=\"rule\"></span></div>\n    <div class=\"fair-card\">\n      <h3>Verifiable results</h3>\n      <p>Before each round the server commits to a random seed and reveals its SHA-256 hash. Every outcome is derived from <code>hash(seed + nonce + salt)</code>, so a result can never be changed after you have played - not even by the house. Table games carry a 3% house edge (return to player of 97%).</p>\n    </div>\n    <div class=\"fair-card\">\n      <h3>House rules</h3>\n      <p>Minimum and maximum bets are set by the operator. Balances are shared with the Casino Royals Telegram bot - one wallet, everywhere. Payouts credit instantly; deposits and withdrawals are handled through the bot. Play only with funds you can afford to lose.</p>\n    </div>\n  </div>\n</div>\n\n<nav id=\"tabs\">\n  <button data-view=\"games\" class=\"on\">\n    <svg viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.8\" stroke-linejoin=\"round\"><path d=\"M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z\"/></svg>\n    <span class=\"nl\">MAIN</span>\n  </button>\n  <button data-view=\"spin\">\n    <svg viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.8\" stroke-linejoin=\"round\"><path d=\"M12 2c2.5 3.5 6 5 7.5 11-1.6 1.6-4 1.6-5.5.4.7 4-.7 7.5-2 10-1.3-2.5-2.7-6-2-10-1.5 1.2-3.9 1.2-5.5-.4C6 7 9.5 5.5 12 2z\"/></svg>\n    <span class=\"nl\">SPIN</span>\n  </button>\n  <button data-view=\"wallet\">\n    <svg viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.8\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><rect x=\"2.5\" y=\"5.5\" width=\"19\" height=\"14\" rx=\"3\"/><path d=\"M16 12h5M16 9.5h5\"/></svg>\n    <span class=\"nl\">WALLET</span>\n  </button>\n  <button data-view=\"board\">\n    <svg viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.8\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M8 21V11M12 21V4M16 21v-7M4 21h16\"/></svg>\n    <span class=\"nl\">TOP</span>\n  </button>\n  <button data-view=\"fair\">\n    <svg viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.8\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M12 3l7 3v5c0 4.5-3 8.5-7 10-4-1.5-7-5.5-7-10V6l7-3z\"/><path d=\"M9.5 12l2 2 3.5-4\"/></svg>\n    <span class=\"nl\">FAIR</span>\n  </button>\n  <button data-view=\"admin\" id=\"adminTab\" style=\"display:none\">\n    <svg viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.8\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><circle cx=\"12\" cy=\"8\" r=\"4\"/><path d=\"M4 20c1.5-3.5 4.5-5 8-5s6.5 1.5 8 5\"/></svg>\n    <span class=\"nl\">ADMIN</span>\n  </button>\n</nav>\n\n<div id=\"toast\"></div>\n<script>\n/* ============================== SOUND ENGINE ============================== */\nconst sfx=(function(){\n  let ctx=null,muted=localStorage.getItem('cr_muted')==='1';\n  function ensure(){\n    if(!ctx){try{ctx=new (window.AudioContext||window.webkitAudioContext)();}catch(e){ctx=null;}}\n    if(ctx&&ctx.state==='suspended'){try{ctx.resume();}catch(e){}}\n  }\n  function tone(freq,dur,type,vol,delay,slideTo){\n    if(muted)return;ensure();if(!ctx)return;\n    const t0=ctx.currentTime+(delay||0);\n    const o=ctx.createOscillator(),g=ctx.createGain();\n    o.type=type||'sine';o.frequency.setValueAtTime(freq,t0);\n    if(slideTo)o.frequency.exponentialRampToValueAtTime(slideTo,t0+dur);\n    g.gain.setValueAtTime(0.0001,t0);\n    g.gain.exponentialRampToValueAtTime(vol||0.15,t0+0.012);\n    g.gain.exponentialRampToValueAtTime(0.0001,t0+dur);\n    o.connect(g);g.connect(ctx.destination);\n    o.start(t0);o.stop(t0+dur+0.05);\n  }\n  function noise(dur,vol,fc,delay){\n    if(muted)return;ensure();if(!ctx)return;\n    const t0=ctx.currentTime+(delay||0);\n    const len=Math.max(1,Math.floor(ctx.sampleRate*dur));\n    const buf=ctx.createBuffer(1,len,ctx.sampleRate);\n    const d=buf.getChannelData(0);\n    for(let i=0;i<len;i++)d[i]=(Math.random()*2-1)*(1-i/len);\n    const src=ctx.createBufferSource();src.buffer=buf;\n    const f=ctx.createBiquadFilter();f.type='lowpass';f.frequency.value=fc||900;\n    const g=ctx.createGain();g.gain.setValueAtTime(vol||0.2,t0);\n    g.gain.exponentialRampToValueAtTime(0.0001,t0+dur);\n    src.connect(f);f.connect(g);g.connect(ctx.destination);\n    src.start(t0);\n  }\n  return {\n    get muted(){return muted;},\n    toggle(){muted=!muted;localStorage.setItem('cr_muted',muted?'1':'0');return muted;},\n    unlock(){ensure();},\n    click(){tone(700,0.06,'square',0.06);tone(1050,0.05,'sine',0.08,0.02);},\n    tick(){tone(2200,0.03,'square',0.05);},\n    coin(){tone(1250,0.12,'sine',0.14);tone(1875,0.22,'sine',0.12,0.09);},\n    deal(){noise(0.12,0.12,2400);tone(520,0.06,'triangle',0.06,0.03);},\n    roll(){tone(320,0.5,'sawtooth',0.05,0,420);noise(0.25,0.06,1200,0.05);},\n    win(){tone(523,0.14,'triangle',0.16);tone(659,0.14,'triangle',0.16,0.11);tone(784,0.14,'triangle',0.16,0.22);tone(1046,0.4,'triangle',0.2,0.33);tone(1568,0.5,'sine',0.12,0.45);},\n    bigwin(){[523,659,784,1046,1318,1568].forEach((f,i)=>tone(f,0.22,'triangle',0.18,i*0.09));noise(0.5,0.05,3000,0.5);},\n    lose(){tone(300,0.25,'sawtooth',0.1,0,150);tone(150,0.45,'sawtooth',0.12,0.18,70);},\n    boom(){noise(0.5,0.4,700);tone(90,0.5,'sawtooth',0.25,0,40);},\n    cash(){tone(880,0.08,'square',0.1);tone(1320,0.08,'square',0.1,0.07);tone(1760,0.16,'square',0.12,0.14);},\n    fanfare(){[392,523,659,784].forEach((f,i)=>tone(f,0.3,'triangle',0.14,i*0.16));[1046,1318].forEach((f,i)=>tone(f,0.5,'triangle',0.16,0.7+i*0.12));}\n  };\n})();\nfunction toggleMute(){\n  const m=sfx.toggle();\n  document.getElementById('muteBtn').innerHTML=m?ICON.muteOn:ICON.muteOff;\n  if(!m)sfx.unlock();\n}\nconst REFRESH_ICON='<svg viewBox=\"0 0 24 24\" width=\"18\" height=\"18\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M21 12a9 9 0 11-2.64-6.36\"/><path d=\"M21 3v6h-6\"/></svg>';\ndocument.getElementById('refreshBtn').innerHTML=REFRESH_ICON;\n\n/* Ripple effect on every primary/ctrl/chip button */\ndocument.addEventListener('click',function(e){\n  const btn=e.target.closest('.primary,.ctrl,.chips button,.wa-dep,.wa-wd,.cat');\n  if(!btn)return;\n  const rect=btn.getBoundingClientRect();\n  const d=Math.max(rect.width,rect.height);\n  const r=document.createElement('span');\n  r.className='ripple';\n  r.style.width=r.style.height=d+'px';\n  r.style.left=(e.clientX-rect.left-d/2)+'px';\n  r.style.top=(e.clientY-rect.top-d/2)+'px';\n  btn.appendChild(r);\n  setTimeout(()=>r.remove(),650);\n});\n\n/* Confetti for big wins */\nfunction confettiBurst(){\n  const colors=['#2563eb','#3b82f6','#06b6d4','#f59e0b','#fbbf24','#93c5fd'];\n  for(let i=0;i<36;i++){\n    const c=document.createElement('div');\n    c.className='confetti';\n    c.style.left=(Math.random()*100)+'vw';\n    c.style.background=colors[i%colors.length];\n    c.style.animationDuration=(1.4+Math.random()*1.4)+'s';\n    c.style.animationDelay=(Math.random()*0.5)+'s';\n    c.style.transform='rotate('+(Math.random()*360)+'deg)';\n    document.body.appendChild(c);\n    setTimeout(()=>c.remove(),3200);\n  }\n}\n\n/* Profile card */\nfunction renderProfile(){\n  const u=S.user;\n  if(!u){return;}\n  const av=$('profileAvatar');\n  const name=em(u.name||'Player')+(u.last_name?' '+em(u.last_name):'');\n  if(u.photo_url){\n    av.innerHTML='<img src=\"'+em(u.photo_url)+'\" alt=\"avatar\" onerror=\"this.remove();this.parentNode.textContent=\\''+((u.name||'G')[0]||'G').toUpperCase()+'\\';\">';\n  }else{\n    av.textContent=(u.name||'G')[0].toUpperCase();\n  }\n  $('profileName').innerHTML=em(name)+(u.is_premium?'<span class=\"prem\">PREMIUM</span>':'');\n  $('profileSub').textContent=(u.username?'@'+em(u.username):'Player')+' - ID '+u.id;\n}\n\n/* Balance + profile refresh (also used after deposits) */\nlet refreshing=false;\nasync function refreshBalance(){\n  if(refreshing)return;refreshing=true;\n  const btn=$('refreshBtn');\n  btn&&btn.classList.add('spin');\n  sfx.click();\n  try{\n    if(!S.realMode){setBal(S.balance);toast('Preview mode - balance is local');return;}\n    const res=await api('/api/balance');\n    if(res&&res.ok){\n      setBal(res.balance||0);\n      if(res.stats){S.stats=res.stats;renderStats();}\n      if(res.user){S.user=res.user;renderProfile();}\n      toast('Balance updated');\n    }else{\n      toast(res&&res.error?res.error:'Refresh failed');\n    }\n  }catch(e){toast('Refresh failed');}\n  finally{refreshing=false;btn&&btn.classList.remove('spin');}\n}\ndocument.addEventListener('visibilitychange',function(){\n  if(!document.hidden)refreshBalance();\n});\n\n/* Auto-reconnect: if login failed (e.g. bot token changed on Railway),\n   keep retrying until the real wallet loads. No user action needed. */\nlet reconnectTimer=null;\nfunction startReconnect(){\n  if(reconnectTimer)return;\n  reconnectTimer=setInterval(async function(){\n    if(S.realMode){clearInterval(reconnectTimer);reconnectTimer=null;return;}\n    if(!isMiniApp())return;\n    const init=await api('/api/init');\n    if(init&&init.ok&&init.user){\n      S.user=init.user;setBal(init.balance||0);\n      S.history=init.history||[];S.board=init.leaderboard||[];\n      S.stats=init.stats||S.stats;\n      S.demo=false;S.realMode=true;\n      renderProfile();renderModeTag();\n      const be=$('bannerErr');if(be)be.style.display='none';\n      const bw=$('bannerWarn');if(bw)bw.style.display='none';\n      toast('Connected - wallet loaded');\n      clearInterval(reconnectTimer);reconnectTimer=null;\n    }\n  },8000);\n}\nfunction hap(kind){try{const w=window.Telegram&&Telegram.WebApp;if(w&&w.HapticFeedback){w.HapticFeedback.impactOccurred(kind||'light');}}catch(e){}}\n\n/* ============================== ICONS / LOGOS ============================== */\nconst ICON={\n  crown:'<svg viewBox=\"0 0 48 48\" fill=\"none\"><defs><linearGradient id=\"gcrn\" x1=\"4\" y1=\"6\" x2=\"44\" y2=\"42\"><stop offset=\"0\" stop-color=\"#ffe9a8\"/><stop offset=\".55\" stop-color=\"#f5b942\"/><stop offset=\"1\" stop-color=\"#b45309\"/></linearGradient></defs><path d=\"M5 15L12 22l12-14 12 14 7-7-3 25H8L5 15z\" fill=\"url(#gcrn)\" stroke=\"#8a5a10\" stroke-width=\"1.4\" stroke-linejoin=\"round\"/><rect x=\"6.8\" y=\"33.2\" width=\"34.4\" height=\"5.2\" rx=\"2.6\" fill=\"url(#gcrn)\" stroke=\"#8a5a10\" stroke-width=\"1.2\"/><circle cx=\"24\" cy=\"16.8\" r=\"2.2\" fill=\"#fff\"/><circle cx=\"13.6\" cy=\"25.4\" r=\"1.7\" fill=\"#e11d48\"/><circle cx=\"34.4\" cy=\"25.4\" r=\"1.7\" fill=\"#2563eb\"/><circle cx=\"24\" cy=\"29\" r=\"1.7\" fill=\"#16a34a\"/></svg>',\n  dice:'<svg viewBox=\"0 0 48 48\" fill=\"none\"><defs><linearGradient id=\"gdi\" x1=\"6\" y1=\"6\" x2=\"42\" y2=\"42\"><stop offset=\"0\" stop-color=\"#93c5fd\"/><stop offset=\"1\" stop-color=\"#1d4ed8\"/></linearGradient><linearGradient id=\"gdi2\" x1=\"10\" y1=\"10\" x2=\"38\" y2=\"38\"><stop offset=\"0\" stop-color=\"#ffffff\"/><stop offset=\"1\" stop-color=\"#dbeafe\"/></linearGradient></defs><rect x=\"7\" y=\"7\" width=\"34\" height=\"34\" rx=\"9\" fill=\"url(#gdi)\" stroke=\"#0f2a6b\" stroke-width=\"1.6\"/><rect x=\"12\" y=\"12\" width=\"24\" height=\"24\" rx=\"6\" fill=\"url(#gdi2)\"/><circle cx=\"19\" cy=\"19\" r=\"2.6\" fill=\"#1d4ed8\"/><circle cx=\"29\" cy=\"19\" r=\"2.6\" fill=\"#1d4ed8\"/><circle cx=\"24\" cy=\"24\" r=\"2.6\" fill=\"#1d4ed8\"/><circle cx=\"19\" cy=\"29\" r=\"2.6\" fill=\"#1d4ed8\"/><circle cx=\"29\" cy=\"29\" r=\"2.6\" fill=\"#1d4ed8\"/></svg>',\n  crash:'<svg viewBox=\"0 0 48 48\" fill=\"none\"><defs><linearGradient id=\"gcr\" x1=\"14\" y1=\"2\" x2=\"34\" y2=\"40\"><stop offset=\"0\" stop-color=\"#ffffff\"/><stop offset=\"1\" stop-color=\"#dbe3ee\"/></linearGradient><linearGradient id=\"gcrf\" x1=\"20\" y1=\"34\" x2=\"28\" y2=\"46\"><stop offset=\"0\" stop-color=\"#fde68a\"/><stop offset=\".5\" stop-color=\"#f97316\"/><stop offset=\"1\" stop-color=\"#ef4444\"/></linearGradient></defs><path d=\"M20 34c-2.8 0-5.2-.6-6.4-2.4-1.6 1-2.6 2.6-2.6 4.4 0 3.2 3 4.6 7.6 4.6h10.8c4.6 0 7.6-1.4 7.6-4.6 0-1.8-1-3.4-2.6-4.4-1.2 1.8-3.6 2.4-6.4 2.4\" fill=\"url(#gcrf)\"/><path d=\"M24 3c3.2 4.6 7.8 6.6 9.2 14.6-2 2-5 1.8-6.6.5.8 5-.8 9.4-2.6 12-1.8-2.6-3.4-6.6-2.6-12-1.6 1.3-4.6 1.5-6.6-.5C16.2 9.6 20.8 7.6 24 3z\" fill=\"url(#gcr)\" stroke=\"#ef4444\" stroke-width=\"1.5\" stroke-linejoin=\"round\"/><circle cx=\"24\" cy=\"17.5\" r=\"4.4\" fill=\"#7dd3fc\" stroke=\"#1d4ed8\" stroke-width=\"1.3\"/><circle cx=\"24\" cy=\"17.5\" r=\"1.6\" fill=\"#0f2a6b\"/><path d=\"M17.5 4.5c.6 2.4 2.4 3.6 4.8 4.2M30.5 4.5c-.6 2.4-2.4 3.6-4.8 4.2\" stroke=\"#ef4444\" stroke-width=\"1.4\" stroke-linecap=\"round\"/><path d=\"M12.6 24.5l-2.8 2.8M35.4 24.5l2.8 2.8\" stroke=\"#ef4444\" stroke-width=\"1.6\" stroke-linecap=\"round\"/></svg>',\n  mines:'<svg viewBox=\"0 0 48 48\" fill=\"none\"><defs><radialGradient id=\"gm\" cx=\"38%\" cy=\"30%\" r=\"75%\"><stop offset=\"0\" stop-color=\"#3b3f4a\"/><stop offset=\"1\" stop-color=\"#0b0e16\"/></radialGradient></defs><circle cx=\"24\" cy=\"26\" r=\"15\" fill=\"url(#gm)\" stroke=\"#525b6d\" stroke-width=\"1.4\"/><path d=\"M24 11c-3 0-5-3-5-6.5 3 .6 5 3 5 6.5z\" fill=\"#3b3f4a\" stroke=\"#525b6d\" stroke-width=\"1.2\"/><path d=\"M24 10.5c2.4-3.4 5.6-4.6 8.6-4.2-2.4 1.6-3.4 3.4-4 5.4\" stroke=\"#525b6d\" stroke-width=\"1.2\" fill=\"none\"/><path d=\"M20.6 14.4c-2-1.2-4.2-1.4-6.2-.6 2 .6 3.6 2 4.8 3.6\" stroke=\"#525b6d\" stroke-width=\"1.2\" fill=\"none\"/><path d=\"M30 19.4c2.4-1.2 4.6-1.6 6.6-.8-2.2.6-3.8 2-5 4.4\" stroke=\"#525b6d\" stroke-width=\"1.2\" fill=\"none\"/><circle cx=\"24\" cy=\"26\" r=\"3\" fill=\"#fde047\"/><circle cx=\"24\" cy=\"26\" r=\"3\" fill=\"#fde047\" stroke=\"#f97316\" stroke-width=\"1.2\"/></svg>',\n  towers:'<svg viewBox=\"0 0 48 48\" fill=\"none\"><defs><linearGradient id=\"gt\" x1=\"8\" y1=\"4\" x2=\"40\" y2=\"44\"><stop offset=\"0\" stop-color=\"#60a5fa\"/><stop offset=\"1\" stop-color=\"#1d4ed8\"/></linearGradient></defs><rect x=\"12\" y=\"28\" width=\"24\" height=\"7\" rx=\"2\" fill=\"url(#gt)\" stroke=\"#0f2a6b\" stroke-width=\"1.2\"/><rect x=\"16\" y=\"19\" width=\"16\" height=\"7\" rx=\"2\" fill=\"url(#gt)\" stroke=\"#0f2a6b\" stroke-width=\"1.2\"/><rect x=\"20\" y=\"10\" width=\"8\" height=\"7\" rx=\"2\" fill=\"url(#gt)\" stroke=\"#0f2a6b\" stroke-width=\"1.2\"/><rect x=\"22\" y=\"2.6\" width=\"4\" height=\"5\" rx=\"2\" fill=\"#f5b942\" stroke=\"#8a5a10\" stroke-width=\"1\"/><path d=\"M6 39h36\" stroke=\"#0f2a6b\" stroke-width=\"2.4\" stroke-linecap=\"round\"/></svg>',\n  blackjack:'<svg viewBox=\"0 0 48 48\" fill=\"none\"><defs><linearGradient id=\"gbj\" x1=\"6\" y1=\"8\" x2=\"42\" y2=\"40\"><stop offset=\"0\" stop-color=\"#ffffff\"/><stop offset=\"1\" stop-color=\"#dbeafe\"/></linearGradient></defs><rect x=\"9\" y=\"9\" width=\"21\" height=\"30\" rx=\"4\" fill=\"url(#gbj)\" stroke=\"#93c5fd\" stroke-width=\"1.4\"/><rect x=\"16\" y=\"15\" width=\"21\" height=\"30\" rx=\"4\" transform=\"rotate(14 26 30)\" fill=\"url(#gbj)\" stroke=\"#93c5fd\" stroke-width=\"1.4\"/><path d=\"M24 16c0 7-6 9-6 15a6 6 0 0012 0c0-6-6-8-6-15z\" fill=\"#111827\"/></svg>',\n  baccarat:'<svg viewBox=\"0 0 48 48\" fill=\"none\"><defs><linearGradient id=\"gba\" x1=\"4\" y1=\"4\" x2=\"44\" y2=\"44\"><stop offset=\"0\" stop-color=\"#ffffff\"/><stop offset=\"1\" stop-color=\"#dbeafe\"/></linearGradient></defs><rect x=\"7\" y=\"9\" width=\"17\" height=\"25\" rx=\"3.4\" transform=\"rotate(-10 15 21)\" fill=\"url(#gba)\" stroke=\"#93c5fd\" stroke-width=\"1.4\"/><rect x=\"24\" y=\"9\" width=\"17\" height=\"25\" rx=\"3.4\" transform=\"rotate(10 32 21)\" fill=\"url(#gba)\" stroke=\"#93c5fd\" stroke-width=\"1.4\"/><path d=\"M14 15l6 5-6 5M34 15l-6 5 6 5\" stroke=\"#2563eb\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/></svg>',\n  roulette:'<svg viewBox=\"0 0 48 48\" fill=\"none\"><circle cx=\"24\" cy=\"24\" r=\"20\" fill=\"#111827\"/><path d=\"M24 4a20 20 0 018.4 1.7L29 12 24 4zM42.3 16A20 20 0 0144 24l-12 2-5-12zM24 44a20 20 0 01-8.4-1.7L19 36l5 8zM5.7 16L4 24l12 2 5-12z\" fill=\"#dc2626\"/><path d=\"M4 24l12 2 5-12L5.7 16 4 24zM24 4l5 8 3-5.3A20 20 0 0124 4zM36 21l8-5a20 20 0 00-3-5L36 21z\" fill=\"#16a34a\" opacity=\".9\"/><circle cx=\"24\" cy=\"24\" r=\"6.4\" fill=\"#2563eb\" stroke=\"#93c5fd\" stroke-width=\"1.6\"/><circle cx=\"24\" cy=\"24\" r=\"2.2\" fill=\"#fff\"/><circle cx=\"41\" cy=\"13\" r=\"3.2\" fill=\"#fff\" stroke=\"#93c5fd\" stroke-width=\"1\"/></svg>',\n  hilo:'<svg viewBox=\"0 0 48 48\" fill=\"none\"><defs><linearGradient id=\"gh\" x1=\"6\" y1=\"4\" x2=\"42\" y2=\"44\"><stop offset=\"0\" stop-color=\"#ffffff\"/><stop offset=\"1\" stop-color=\"#dbeafe\"/></linearGradient></defs><rect x=\"10\" y=\"14\" width=\"28\" height=\"26\" rx=\"4\" fill=\"url(#gh)\" stroke=\"#93c5fd\" stroke-width=\"1.5\"/><path d=\"M24 20l7 7h-4l-3 6-3-6h-4l7-7z\" fill=\"#2563eb\"/><path d=\"M14 38h20M18 42h12\" stroke=\"#93c5fd\" stroke-width=\"1.6\" stroke-linecap=\"round\"/></svg>',\n  plinko:'<svg viewBox=\"0 0 48 48\" fill=\"none\"><defs><linearGradient id=\"gp\" x1=\"4\" y1=\"4\" x2=\"44\" y2=\"44\"><stop offset=\"0\" stop-color=\"#60a5fa\"/><stop offset=\"1\" stop-color=\"#1d4ed8\"/></linearGradient></defs><circle cx=\"24\" cy=\"6\" r=\"3\" fill=\"url(#gp)\"/><circle cx=\"15\" cy=\"15\" r=\"3\" fill=\"url(#gp)\"/><circle cx=\"33\" cy=\"15\" r=\"3\" fill=\"url(#gp)\"/><circle cx=\"9\" cy=\"24\" r=\"3\" fill=\"url(#gp)\"/><circle cx=\"24\" cy=\"24\" r=\"3\" fill=\"url(#gp)\"/><circle cx=\"39\" cy=\"24\" r=\"3\" fill=\"url(#gp)\"/><circle cx=\"6\" cy=\"33\" r=\"3\" fill=\"url(#gp)\"/><circle cx=\"16.5\" cy=\"33\" r=\"3\" fill=\"url(#gp)\"/><circle cx=\"31.5\" cy=\"33\" r=\"3\" fill=\"url(#gp)\"/><circle cx=\"42\" cy=\"33\" r=\"3\" fill=\"url(#gp)\"/><circle cx=\"12\" cy=\"42\" r=\"3.4\" fill=\"#f5b942\" stroke=\"#8a5a10\" stroke-width=\"1.2\"/></svg>',\n  keno:'<svg viewBox=\"0 0 48 48\" fill=\"none\"><defs><linearGradient id=\"gk\" x1=\"4\" y1=\"4\" x2=\"44\" y2=\"44\"><stop offset=\"0\" stop-color=\"#fde68a\"/><stop offset=\"1\" stop-color=\"#f59e0b\"/></linearGradient></defs><path d=\"M24 3l5.6 12.4L42 20l-9.4 8.6 2.6 12.6L24 34.6 12.8 41.2l2.6-12.6L6 20l12.4-4.6L24 3z\" fill=\"url(#gk)\" stroke=\"#8a5a10\" stroke-width=\"1.4\" stroke-linejoin=\"round\"/><circle cx=\"24\" cy=\"22\" r=\"6\" fill=\"#0f2a6b\"/><circle cx=\"24\" cy=\"22\" r=\"2\" fill=\"#fff\"/></svg>',\n  wheel:'<svg viewBox=\"0 0 48 48\" fill=\"none\"><defs><linearGradient id=\"gw\" x1=\"4\" y1=\"4\" x2=\"44\" y2=\"44\"><stop offset=\"0\" stop-color=\"#60a5fa\"/><stop offset=\"1\" stop-color=\"#1d4ed8\"/></linearGradient></defs><circle cx=\"24\" cy=\"24\" r=\"19\" fill=\"#0b1e4b\" stroke=\"#1d4ed8\" stroke-width=\"2\"/><path d=\"M24 5a19 19 0 017.4 1.5L24 24zM42.5 16.6A19 19 0 0143 24H24zM24 43a19 19 0 01-7.4-1.5L24 24zM5.5 16.6L5 24h19z\" fill=\"url(#gw)\"/><path d=\"M24 5l7.4 1.5L24 24 16.6 6.5zM43 24l-11.5.2L24 24l9.4-7.4z\" fill=\"#f5b942\"/><circle cx=\"24\" cy=\"24\" r=\"4.6\" fill=\"#fff\" stroke=\"#93c5fd\" stroke-width=\"1.4\"/></svg>',\n  limbo:'<svg viewBox=\"0 0 48 48\" fill=\"none\"><defs><linearGradient id=\"gl\" x1=\"4\" y1=\"4\" x2=\"44\" y2=\"44\"><stop offset=\"0\" stop-color=\"#7dd3fc\"/><stop offset=\"1\" stop-color=\"#2563eb\"/></linearGradient></defs><circle cx=\"24\" cy=\"24\" r=\"19\" fill=\"none\" stroke=\"url(#gl)\" stroke-width=\"2.6\" stroke-dasharray=\"8 6\"/><circle cx=\"24\" cy=\"24\" r=\"11\" fill=\"none\" stroke=\"url(#gl)\" stroke-width=\"2.4\" stroke-dasharray=\"6 5\"/><circle cx=\"24\" cy=\"24\" r=\"4.4\" fill=\"url(#gl)\"/><path d=\"M12 9.5L8 5M36 9.5L40 5M12 38.5L8 43M36 38.5L40 43\" stroke=\"#7dd3fc\" stroke-width=\"2\" stroke-linecap=\"round\"/></svg>',\n  coinflip:'<svg viewBox=\"0 0 48 48\" fill=\"none\"><defs><linearGradient id=\"gcf\" x1=\"8\" y1=\"8\" x2=\"40\" y2=\"40\"><stop offset=\"0\" stop-color=\"#fef3c7\"/><stop offset=\".6\" stop-color=\"#f5b942\"/><stop offset=\"1\" stop-color=\"#b45309\"/></linearGradient></defs><circle cx=\"24\" cy=\"24\" r=\"20\" fill=\"url(#gcf)\" stroke=\"#8a5a10\" stroke-width=\"1.6\"/><circle cx=\"24\" cy=\"24\" r=\"14.5\" fill=\"none\" stroke=\"#8a5a10\" stroke-width=\"1.4\"/><text x=\"24\" y=\"30\" text-anchor=\"middle\" font-family=\"Georgia,serif\" font-size=\"15\" font-weight=\"800\" fill=\"#7c4a03\">CR</text><path d=\"M7 14c2-2.4 4-3.6 6.4-4.2M41 14c-2-2.4-4-3.6-6.4-4.2M7 34c2 2.4 4 3.6 6.4 4.2M41 34c-2 2.4-4 3.6-6.4 4.2\" stroke=\"#fef3c7\" stroke-width=\"1.6\" stroke-linecap=\"round\"/></svg>',\n  slots:'<svg viewBox=\"0 0 48 48\" fill=\"none\"><defs><linearGradient id=\"gs\" x1=\"4\" y1=\"4\" x2=\"44\" y2=\"44\"><stop offset=\"0\" stop-color=\"#60a5fa\"/><stop offset=\"1\" stop-color=\"#1d4ed8\"/></linearGradient><linearGradient id=\"gs2\" x1=\"6\" y1=\"6\" x2=\"42\" y2=\"42\"><stop offset=\"0\" stop-color=\"#ffffff\"/><stop offset=\"1\" stop-color=\"#dbeafe\"/></linearGradient></defs><rect x=\"5\" y=\"7\" width=\"38\" height=\"34\" rx=\"7\" fill=\"url(#gs)\" stroke=\"#0f2a6b\" stroke-width=\"1.6\"/><rect x=\"9.5\" y=\"12\" width=\"8\" height=\"18\" rx=\"2.6\" fill=\"url(#gs2)\"/><rect x=\"20\" y=\"12\" width=\"8\" height=\"18\" rx=\"2.6\" fill=\"url(#gs2)\"/><rect x=\"30.5\" y=\"12\" width=\"8\" height=\"18\" rx=\"2.6\" fill=\"url(#gs2)\"/><circle cx=\"13.5\" cy=\"21\" r=\"2.4\" fill=\"#2563eb\"/><circle cx=\"24\" cy=\"21\" r=\"2.4\" fill=\"#2563eb\"/><circle cx=\"34.5\" cy=\"21\" r=\"2.4\" fill=\"#2563eb\"/><rect x=\"30.5\" y=\"31\" width=\"8\" height=\"8\" rx=\"3\" fill=\"#f5b942\" stroke=\"#8a5a10\" stroke-width=\"1.2\"/><circle cx=\"34.5\" cy=\"35\" r=\"1.8\" fill=\"#8a5a10\"/></svg>',\n  muteOn:'<svg viewBox=\"0 0 24 24\" width=\"20\" height=\"20\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.8\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M11 5L6 9H3v6h3l5 4V5z\" fill=\"rgba(255,255,255,.25)\"/><path d=\"M15.5 8.5a5 5 0 010 7M18.5 6a9 9 0 010 12\"/></svg>',\n  muteOff:'<svg viewBox=\"0 0 24 24\" width=\"20\" height=\"20\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.8\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M11 5L6 9H3v6h3l5 4V5z\" fill=\"rgba(255,255,255,.25)\"/><path d=\"M22 9l-6 6M16 9l6 6\"/></svg>'\n};\n\n/* ============================== CORE STATE ============================== */\nconst S={demo:true,realMode:false,user:null,balance:0,cfg:null,game:null,session:null,history:[],board:[],\n  stats:{games:0,wins:0,losses:0,wagered:0,paid:0},busy:false,bet:0};\nconst $=id=>document.getElementById(id);\nconst em=html=>String(html==null?'':html).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));\nconst fmt=n=>{n=Math.round(n*100)/100;let s=n.toFixed(2).replace(/\\.?0+$/,'');return s||'0'};\n\nlet balTimer=null,balShown=0;\nfunction setBal(target){\n  const el=$('bal');if(!el)return;\n  target=Math.round((+target||0)*100)/100;\n  if(balTimer){clearInterval(balTimer);balTimer=null;}\n  const from=balShown,delta=target-from;\n  if(Math.abs(delta)<0.005){balShown=target;el.textContent=fmt(target);el.classList.remove('pulse');void el.offsetWidth;el.classList.add('pulse');return;}\n  const t0=Date.now(),dur=420;\n  balTimer=setInterval(()=>{\n    const t=Math.min(1,(Date.now()-t0)/dur);\n    const v=from+delta*(1-Math.pow(1-t,3));\n    balShown=v;el.textContent=fmt(v);\n    if(t>=1){clearInterval(balTimer);balTimer=null;balShown=target;el.textContent=fmt(target);\n      el.classList.remove('pulse');void el.offsetWidth;el.classList.add('pulse');}\n  },16);\n}\n\nfunction toast(msg){\n  const t=$('toast');if(!t)return;\n  t.textContent=msg;t.classList.add('show');\n  clearTimeout(t._h);t._h=setTimeout(()=>t.classList.remove('show'),2600);\n}\nfunction notify(msg){toast(msg);}\n\n/* Robust Telegram environment detection (menu-button launches pass initData\n   through the WebApp bridge; direct-link launches pass URL params). */\nfunction isMiniApp(){\n  const bridge=!!(window.Telegram&&window.Telegram.WebApp&&window.Telegram.WebApp.initData);\n  if(bridge)return true;\n  try{\n    const q=window.location.search.substring(1);\n    const h=window.location.hash.substring(1);\n    const params=new URLSearchParams(q||h);\n    return !!(params.get('tgWebAppData')||params.get('tgWebAppStartParam'));\n  }catch(e){return false;}\n}\nfunction showLanding(){\n  const el=$('envLanding');if(!el)return;\n  const bot=(S.cfg&&S.cfg.botUsername)||'CasinoRoyalsBot';\n  $('envBtn').href='https://t.me/'+bot;\n  el.style.display='flex';\n  $('envDemo').onclick=()=>{el.style.display='none';sfx.unlock();};\n}\nfunction initData(){\n  if(isMiniApp())return Telegram.WebApp.initData;\n  return '';\n}\nfunction showBanner(html,warn){\n  const b=$(warn?'bannerWarn':'bannerErr');\n  if(!b)return;\n  b.innerHTML=html+'<span class=\"bx\" onclick=\"this.parentElement.style.display=\\'none\\'\">&times;</span>';\n  b.style.display='block';\n}\nfunction renderModeTag(){\n  const t=$('modeTag');\n  if(!t)return;\n  t.textContent=S.realMode?'LIVE':'DEMO';\n  t.classList.toggle('live',!!S.realMode);\n}\nfunction demoCrashHist(){\n  const h=[];\n  for(let i=0;i<12;i++){\n    const r=Math.random();\n    const v=r>=0.97?1:Math.max(1.01,Math.round((0.97/r)*100)/100);\n    h.push(v);\n  }\n  return h;\n}\nfunction histPill(v){\n  const cls=v<2?'h-low':(v<10?'h-mid':'h-high');\n  return '<span class=\"hpill '+cls+'\">'+fmt(v)+'x</span>';\n}\nfunction renderHist(){\n  const el=$('histStrip');\n  if(!el)return;\n  el.innerHTML=(S.crashHistory&&S.crashHistory.length?S.crashHistory:demoCrashHist()).map(histPill).join('');\n}\nfunction renderFeed(){\n  const el=$('feedStrip');if(!el)return;\n  const f=S.liveFeed||[];\n  el.innerHTML=f.length?f.map(x=>\n    `<span class=\"fpill\">${ICON[x.game]?('<svg viewBox=\"0 0 48 48\" style=\"width:12px;height:12px;vertical-align:-2px\">'+ICON[x.game].replace(/<svg[^>]*>/,'').replace(/<\\/svg>$/,'')+'</svg>'):''} <b>${em(x.user)}</b> ${fmt(x.bet)}${x.multiplier?' @'+fmt(x.multiplier)+'x':''}</span>`\n  ).join(''):'<span class=\"fpill\">Waiting for players...</span>';\n}\nlet feedTimer=null;\nfunction startFeed(){\n  if(feedTimer)return;\n  const poll=async()=>{\n    try{\n      const res=await api('/api/feed');\n      if(res&&res.ok){\n        if(res.feed)S.liveFeed=res.feed;\n        if(res.crashHistory&&res.crashHistory.length)S.crashHistory=res.crashHistory;\n        renderFeed();renderHist();\n      }\n    }catch(e){}\n  };\n  if(!S.demo)poll();\n  else{S.liveFeed=[{game:'crash',user:'Raj***',bet:25,multiplier:2.1},{game:'mines',user:'Aman***',bet:10,multiplier:0},{game:'plinko',user:'Priya***',bet:15,multiplier:3.4},{game:'blackjack',user:'Vik***',bet:40,multiplier:2}];renderFeed();}\n  feedTimer=setInterval(poll,6000);\n}\nasync function api(path,body){\n  try{\n    const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},\n      body:JSON.stringify(Object.assign({initData:initData()},body||{}))});\n    const j=await r.json();\n    if(!r.ok&&r.status!==401){return {ok:false,error:j.error||'Request failed',code:j.code};}\n    return j;\n  }catch(e){return {offline:true};}\n}\n\n/* ============================== DEMO ENGINE ============================== */\nconst DEMO={\n  deck(){let d=[];for(let i=0;i<52;i++){let v=(i%13)+2;d.push(v>14?14:v);}for(let i=d.length-1;i>0;i--){let j=Math.floor(Math.random()*(i+1));[d[i],d[j]]=[d[j],d[i]];}return d;},\n  bjVal(h){let t=0,a=0;h.forEach(c=>{if(c===14){a++;t+=1}else t+=Math.min(c,10);});return a>0&&t+10<=21?t+10:t;}\n};\nfunction demoFair(){return {seed_hash:[...Array(24)].map(()=>Math.floor(Math.random()*16).toString(16)).join(''),nonce:'0'};}\nfunction demoResult(game,action,data){\n  data=data||{};\n  let bet=parseFloat(data.bet)||0;\n  if(!bet&&S.session&&S.session.game===game)bet=S.session.bet||0;\n  const rnd=()=>Math.random();\n  const fair=demoFair();\n  let won,payout=0,extra={};\n  switch(game){\n    case 'dice':{\n      const dir=data.direction==='under'?'under':'over',t=parseInt(data.target)||50;\n      const roll=1+Math.floor(rnd()*100);\n      won=dir==='over'?roll>t:roll<t;\n      const wins=dir==='over'?(100-t):(t-1);\n      const mult=wins>0?0.97*100/wins:0;\n      payout=won?bet*mult:0;\n      extra={roll,target:t,direction:dir,multiplier:mult};break;}\n    case 'crash':{\n      if(action==='play'){\n        const r=rnd();const cp=r>=0.97?1:Math.max(1.01,Math.round((0.97/r)*100)/100);\n        S.session={game:'crash',bet,cp,started:Date.now(),cashed:false};\n        return {ok:true,session_id:1,crash_point:cp,bet,fair};}\n      const mult=Math.max(1.00,Math.min(parseFloat(data.multiplier)||1,(S.session&&S.session.cp?S.session.cp-0.01:1.01)));\n      payout=bet*mult;won=true;extra={multiplier:mult,crash_point:(S.session&&S.session.cp?S.session.cp:1)};break;}\n    case 'mines':{\n      const mines=Math.max(1,Math.min(10,parseInt(data.mines)||3));\n      if(action==='new'){\n        let bombs=new Set();while(bombs.size<mines)bombs.add(Math.floor(rnd()*25));\n        S.session={game:'mines',bet,mines,bombs:[...bombs],revealed:[]};\n        return {ok:true,session_id:1,grid:[...Array(25)].map((_,i)=>({i,revealed:false})),fair};}\n      const s=S.session;\n      if(action==='cashout'){\n        const m=minesMult(s.mines,s.revealed.length);payout=bet*m;won=true;\n        extra={multiplier:m,revealed:[...s.revealed]};break;}\n      const cell=parseInt(data.cell);\n      if(s.revealed.includes(cell))return {ok:false,error:'Already revealed.'};\n      s.revealed.push(cell);\n      if(s.bombs.includes(cell)){won=false;payout=0;extra={bomb_at:cell,revealed:[...s.revealed]};break;}\n      if(s.revealed.length>=25-s.mines){const m=minesMult(s.mines,s.revealed.length);payout=bet*m;won=true;extra={cleared:true,multiplier:m,revealed:[...s.revealed]};break;}\n      return {ok:true,won:null,cell,revealed:[...s.revealed],multiplier:minesMult(s.mines,s.revealed.length),potential_payout:bet*minesMult(s.mines,s.revealed.length),bet,fair};}\n    case 'towers':{\n      const diff=data.difficulty||'easy';const bad={easy:1,medium:2,hard:3}[diff];\n      if(action==='new'){\n        S.session={game:'towers',bet,bad,row:0,layout:[...Array(8)].map(function(){var b=new Set();while(b.size<bad)b.add(Math.floor(rnd()*3));return[...b];})};\n        return {ok:true,session_id:1,difficulty:diff,fair};}\n      const s=S.session;\n      if(action==='cashout'){const m=towMult(s.row,bad);payout=bet*m;won=true;extra={multiplier:m,row:s.row};break;}\n      const col=parseInt(data.col);\n      if(s.layout[s.row].includes(col)){won=false;payout=0;extra={row:s.row,col};break;}\n      s.row++;\n      const m=towMult(s.row,bad);\n      if(s.row>=8){payout=bet*m;won=true;extra={cleared:true,multiplier:m};break;}\n      return {ok:true,won:null,row:s.row,col,multiplier:m,potential_payout:bet*m,bet,fair};}\n    case 'blackjack':{\n      if(action==='new'){\n        const shoe=[];for(let i=0;i<6;i++)shoe.push(...DEMO.deck());\n        let p=[shoe.pop(),shoe.pop()],dl=[shoe.pop(),shoe.pop()];\n        S.session={game:'blackjack',bet,shoe:shoe,\n          hands:[{cards:p,bet:bet,doubled:false,split:false,stood:false,payout:0}],\n          current:0,dealer:dl,baseBet:bet,\n          insuranceOffered:dl[0]===14,insuranceTaken:false,insuranceDecided:!(dl[0]===14),\n          splitCount:0};\n        const pv=DEMO.bjVal(p);\n        if(pv===21&&!S.session.insuranceOffered)return bjDemoSettle(S.session);\n        return {ok:true,session_id:1,\n          hands:[{cards:p.map(cl),value:pv,bet:bet,active:true}],\n          dealer:[cl(dl[0]),'?'],insurance_offered:S.session.insuranceOffered,fair};}\n      const s=S.session;\n      if(!s||!s.hands)return {ok:false,error:'Session expired.'};\n      const curHand=()=>s.hands[s.current];\n      if(action==='insure'){\n        if(!s.insuranceOffered||s.insuranceDecided)return {ok:false,error:'Insurance is not offered.'};\n        S.balance-=s.baseBet/2;\n        s.insuranceTaken=true;s.insuranceDecided=true;\n        return bjDemoSettle(s);}\n      if(action==='decline'){\n        s.insuranceDecided=true;\n        if(DEMO.bjVal(curHand().cards)===21)return bjDemoSettle(s);\n        return bjDemoView(s,fair);}\n      if(!s.insuranceDecided)return {ok:false,error:'Decide on insurance first.'};\n      if(action==='hit'){\n        const h=curHand();\n        h.cards.push(s.shoe.pop());\n        const pv=DEMO.bjVal(h.cards);\n        if(pv>=21){\n          h.stood=true;\n          if(s.current<s.hands.length-1){s.current++;return bjDemoView(s,fair);}\n          return bjDemoSettle(s);}\n        return bjDemoView(s,fair);}\n      if(action==='stand'){\n        curHand().stood=true;\n        if(s.current<s.hands.length-1){s.current++;return bjDemoView(s,fair);}\n        return bjDemoSettle(s);}\n      if(action==='double'){\n        const h=curHand();const pv=DEMO.bjVal(h.cards);\n        if(h.cards.length!==2||h.doubled||h.split||pv<9||pv>11)return {ok:false,error:'Double down is allowed only on hard 9, 10 or 11.'};\n        S.balance-=h.bet;\n        h.bet*=2;h.doubled=true;h.cards.push(s.shoe.pop());h.stood=true;\n        if(s.current<s.hands.length-1){s.current++;return bjDemoView(s,fair);}\n        return bjDemoSettle(s);}\n      if(action==='surrender'){\n        const h=curHand();\n        if(s.hands.length!==1||h.cards.length!==2||h.doubled||h.split)return {ok:false,error:'Surrender is allowed only on your first two cards.'};\n        S.balance+=h.bet/2;\n        S.session=null;\n        return {ok:true,won:false,surrender:true,payout:h.bet/2,bet:h.bet,\n          hands:[{cards:h.cards.map(cl),value:DEMO.bjVal(h.cards),bet:h.bet,payout:h.bet/2,outcome:'surrender'}],\n          dealer_cards:s.dealer.map(cl),dealer_value:DEMO.bjVal(s.dealer),fair:demoFair()};}\n      if(action==='split'){\n        const h=curHand();\n        if(s.splitCount>=3||h.cards.length!==2||h.cards[0]!==h.cards[1])return {ok:false,error:'Split is allowed only on a pair (max 3).'};\n        S.balance-=h.bet;s.splitCount++;\n        const c1=h.cards[0],c2=h.cards[1];\n        s.hands[s.current]={cards:[c1,s.shoe.pop()],bet:h.bet,doubled:false,split:true,stood:false,payout:0};\n        s.hands.splice(s.current+1,0,{cards:[c2,s.shoe.pop()],bet:h.bet,doubled:false,split:true,stood:false,payout:0});\n        return bjDemoView(s,fair);}\n      return {ok:false,error:'Unknown action.'};}\n    case 'baccarat':{\n      const side=data.side||'player';\n      const winner=['player','banker','tie'][Math.floor(rnd()*3)];\n      won=winner===side;const mult={player:2,banker:1.95,tie:9}[side];\n      payout=won?bet*mult:0;\n      extra={winner,player_cards:['A','7'],banker_cards:['K','8'],player_value:8,banker_value:8,side};break;}\n    case 'roulette':{\n      const spin=Math.floor(rnd()*37);\n      let choice=data.choice||'red';\n      const color=spin===0?'green':([1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36].includes(spin)?'red':'black');\n      let mult=0;\n      if(choice==='red'||choice==='black')mult=color===choice?2:0;\n      else if(choice==='green')mult=spin===0?14:0;\n      else if(choice==='even'||choice==='odd')mult=spin!==0&&(spin%2===0)===(choice==='even')?2:0;\n      else if(choice==='low')mult=spin>=1&&spin<=18?2:0;\n      else if(choice==='high')mult=spin>=19?2:0;\n      else if(/^\\d+$/.test(choice)){mult=spin===parseInt(choice)?36:0;}\n      won=mult>0;payout=won?bet*mult:0;\n      extra={spin,color,choice};break;}\n    case 'hilo':{\n      if(action==='new'){let d=DEMO.deck(),cur=d.pop();\n        S.session={game:'hilo',bet,deck:d,current:cur,mult:1,step:0};\n        return {ok:true,session_id:1,card:cl(cur),higher_mult:1.2,lower_mult:1.2,cards_left:d.length,fair};}\n      const s=S.session;\n      if(action==='cashout'){payout=bet*s.mult;won=true;extra={multiplier:s.mult,steps:s.step};break;}\n      const card=s.deck.pop();\n      const ok=(action==='higher'&&card>s.current)||(action==='lower'&&card<s.current);\n      if(!ok){won=false;payout=0;extra={drawn:cl(card),had:cl(s.current),tie:card===s.current};break;}\n      s.current=card;s.step++;s.mult*=1.05;\n      if(s.deck.length===0){payout=bet*s.mult;won=true;extra={deck_cleared:true,multiplier:s.mult};break;}\n      return {ok:true,won:null,card:cl(card),higher_mult:1.2,lower_mult:1.2,multiplier:s.mult,potential_payout:bet*s.mult,cards_left:s.deck.length,fair};}\n    case 'plinko':{\n      const risk=['low','medium','high'].includes(data.risk)?data.risk:'low';\n      const rows={low:8,medium:10,high:12}[risk];\n      const tabs={\n        8:[4.41,2.94,1.69,0.73,0.20,0.73,1.69,2.94,4.41],\n        10:[5.18,3.76,2.51,1.46,0.65,0.20,0.65,1.46,2.51,3.76,5.18],\n        12:[5.90,4.54,3.30,2.22,1.30,0.59,0.20,0.59,1.30,2.22,3.30,4.54,5.90]}[rows];\n      const posRaw=parseInt(data.position);const pos=Number.isFinite(posRaw)?Math.max(0,Math.min(rows,posRaw)):Math.floor(rows/2);\n      let rights=0;for(let i=0;i<rows;i++){if(rnd()>=0.5)rights++;}\n      const bucket=Math.max(0,Math.min(rows,pos+2*rights-rows));\n      const mult=tabs[bucket];\n      payout=bet*mult;won=payout>0;extra={bucket,risk,rows,position:pos,multiplier:mult};break;}\n    case 'keno':{\n      const picks=(data.picks||[]).slice().sort((a,b)=>a-b);\n      let drawn=new Set();while(drawn.size<10)drawn.add(1+Math.floor(rnd()*80));\n      const hits=picks.filter(p=>drawn.has(p));\n      const mult=hits.length>=2?Math.min(1000,0.97/(picks.length-1)*comb(80,10)/(comb(picks.length,hits.length)*comb(80-picks.length,10-hits.length))):0;\n      payout=bet*mult;won=payout>0;\n      extra={picks,drawn:[...drawn].sort((a,b)=>a-b),hits,multiplier:mult};break;}\n    case 'wheel':{\n      const segs=[0,0.9,1.3,1.7,2.6,4.3,8.5],weights=[30,42,14,7,4,2,1];\n      let r=rnd()*100,idx=0,acc=0;\n      for(let i=0;i<weights.length;i++){acc+=weights[i];if(r<acc){idx=i;break;}}\n      const mult=segs[idx];payout=bet*mult;won=payout>0;extra={segment:idx,multiplier:mult};break;}\n    case 'limbo':{\n      const t=Math.max(1.01,Math.min(100000,parseFloat(data.target)||2));\n      const p=(1e8-t*1e6)/1e8,mult=0.97/p;\n      const roll=rnd();won=roll>=p;payout=won?bet*mult:0;\n      extra={target:t,multiplier:mult};break;}\n    case 'coinflip':{\n      const side=data.side||'heads';const landed=rnd()<0.5?'heads':'tails';\n      won=landed===side;payout=won?bet*1.94:0;extra={landed,side};break;}\n    case 'slots':{\n      const sym=['C','R','7','A','K','Q','J'];\n      const reel=[0,1,2].map(()=>sym[Math.floor(rnd()*sym.length)]);\n      const mult=reel.every(x=>x===reel[0])?{C:2,R:3,7:4,A:5,K:10,Q:20,J:50}[reel[0]]:0;\n      payout=bet*mult;won=payout>0;extra={reel,multiplier:mult};break;}\n  }\n  S.balance+=payout;S.session=null;\n  return {ok:true,won:won!==null?won:undefined,payout,bet,...extra,fair};\n}\nfunction bjDemoView(s,fair){\n  const h=s.hands[s.current];const pv=DEMO.bjVal(h.cards);\n  return {ok:true,session_id:1,\n    hands:s.hands.map((x,i)=>({cards:x.cards.map(cl),value:DEMO.bjVal(x.cards),bet:x.bet,\n      active:i===s.current,stood:x.stood,doubled:x.doubled})),\n    dealer:[cl(s.dealer[0]),'?'],current_value:pv,\n    can_double:h.cards.length===2&&!h.doubled&&!h.split&&pv>=9&&pv<=11,\n    can_split:h.cards.length===2&&h.cards[0]===h.cards[1]&&s.splitCount<3,\n    can_surrender:s.hands.length===1&&h.cards.length===2&&!h.doubled&&!h.split,fair};\n}\nfunction bjDemoSettle(s){\n  let dl=s.dealer;\n  while(DEMO.bjVal(dl)<17&&s.shoe.length)dl.push(s.shoe.pop());\n  const dv=DEMO.bjVal(dl);\n  const dealerBJ=dl.length===2&&dv===21;\n  let totalBet=0,totalPayout=0,anyWin=false,anyPush=false;\n  const handsOut=s.hands.map(h=>{\n    const bet=h.bet;totalBet+=bet;\n    const pv=DEMO.bjVal(h.cards);\n    const natural=!h.split&&h.cards.length===2&&pv===21;\n    let payout=0,outcome='lost';\n    if(pv>21){outcome='lost';}\n    else if(dealerBJ){payout=natural?bet:0;outcome=natural?'push':'lost';}\n    else if(natural&&dv<21){payout=Math.round(bet*2.5*100)/100;outcome='won';}\n    else if(dv>21||pv>dv){payout=Math.round(bet*2*100)/100;outcome='won';}\n    else if(pv===dv){payout=bet;outcome='push';}\n    totalPayout+=payout;\n    if(payout>0)anyWin=true;\n    if(outcome==='push')anyPush=true;\n    return {cards:h.cards.map(cl),value:pv,bet:bet,payout:Math.round(payout*100)/100,outcome,natural};});\n  let insPayout=0;\n  if(s.insuranceTaken&&dealerBJ){insPayout=s.baseBet;totalPayout+=insPayout;anyWin=true;}\n  S.balance+=totalPayout;S.session=null;\n  return {ok:true,won:anyWin,push:!anyWin&&anyPush,payout:Math.round(totalPayout*100)/100,bet:totalBet,\n    hands:handsOut,dealer_cards:dl.map(cl),dealer_value:dv,dealer_blackjack:dealerBJ,\n    insurance_payout:insPayout,fair:demoFair()};\n}\nfunction minesMult(mines,rev){if(!rev)return 1;return Math.round(0.97*comb(25,rev)/comb(25-mines,rev)*100)/100;}\nfunction towMult(row,bad){return Math.round(0.97*Math.pow(3/(3-bad),row)*100)/100;}\nfunction comb(n,k){let r=1;for(let i=0;i<k;i++)r=r*(n-i)/(i+1);return Math.round(r);}\nfunction cl(c){return c===14?'A':c===13?'K':c===12?'Q':c===11?'J':c===1?'A':String(c);}\n\n/* ============================== INTRO ============================== */\nlet introSkipped=false,introDone=false;\nfunction buildIntroTitle(){\n  const words='CASINO ROYALS';\n  const el=$('introTitle');\n  el.innerHTML=words.split('').map((ch,i)=>\n    `<span class=\"${ch===' '?'':(i>=words.indexOf('ROYALS')?'gold':'')}\" style=\"animation-delay:${0.15+i*0.05}s\">${ch===' '?'&nbsp;':ch}</span>`\n  ).join('');\n}\nfunction skipIntro(){\n  if(introDone)return;\n  introSkipped=true;\n  const it=$('intro');\n  if(it){it.classList.add('gone');}\n  setTimeout(()=>{if(it&&it.parentNode)it.parentNode.removeChild(it);introDone=true;},650);\n}\nfunction startIntro(){\n  buildIntroTitle();\n  sfx.unlock();\n  const it=$('intro');\n  it.addEventListener('click',skipIntro);\n  setTimeout(()=>{if(!introSkipped)sfx.fanfare();},300);\n  setTimeout(skipIntro,2900);\n  setTimeout(()=>{if(!introDone){introDone=true;if(it.parentNode)it.parentNode.removeChild(it);}},3600);\n}\n\n/* ============================== BOOTSTRAP ============================== */\nasync function boot(){\n  startIntro();\n  S.realMode=false;\n  try{\n    const w=window.Telegram&&Telegram.WebApp;\n    if(w){try{w.ready();w.expand();}catch(e){}}\n    const cfg=await api('/api/config');\n    if(!cfg.offline){\n      S.cfg=cfg;S.demo=!!cfg.demoMode;\n      S.crashHistory=(cfg.crashHistory&&cfg.crashHistory.length)?cfg.crashHistory:demoCrashHist();\n    }else{\n      S.cfg={appName:'Casino Royals',currency:'Coins',minBet:1,maxBet:100,games:GAMES_META,botUsername:null};\n      S.demo=true;S.crashHistory=demoCrashHist();\n    }\n    if(S.demo){\n      S.balance=1000;setBal(1000);\n    }else{\n      // Server has a real token. Try to authenticate.\n      if(!isMiniApp()){\n        // Outside Telegram: beautiful landing with an \"Open in Telegram\" button.\n        // The app remains usable in demo mode (dismissible) - nothing is blocked.\n        S.demo=true;S.balance=1000;setBal(1000);S.crashHistory=demoCrashHist();\n        showLanding();\n        renderGrid();renderStats();renderModeTag();\n      }else{\n        const init=await api('/api/init');\n        if(init&&init.ok&&init.user){\n          S.user=init.user;setBal(init.balance||0);\n          S.history=init.history||[];S.board=init.leaderboard||[];\n          S.stats=init.stats||S.stats;\n          S.profile=init.profile||null;\n          S.isAdmin=!!init.isAdmin;\n          renderProfile();\n          S.realMode=true;\n          const at=$('adminTab');if(at)at.style.display=S.isAdmin?'flex':'none';\n        }else{\n          // Auth failed inside Telegram: local demo play, real wallet untouched.\n          S.demo=true;S.balance=1000;setBal(1000);S.crashHistory=demoCrashHist();\n          const reason=(init&&init.error)?init.error:'unknown';\n          showBanner('Login failed: <b>'+em(reason)+'</b> - playing in preview mode. The server is bound to <b>@'+(S.cfg.botUsername||'your bot')+'</b> (token <code>'+(S.cfg.tokenHint||'?')+'</code>). Open the app from a bot whose token matches the server.');\n        }\n      }\n      if(S.cfg.tokenWarning){\n        showBanner('Security: the server is still running the <b>old leaked bot token</b>. On Railway set the <code>TELEGRAM_BOT_TOKEN</code> variable to your current @BotFather token, then redeploy.',true);\n      }\n    }\n    renderGrid();renderStats();renderModeTag();\n    $('depBtn').href='https://t.me/'+(S.cfg.botUsername||'');\n  }catch(err){\n    S.cfg={appName:'Casino Royals',currency:'Coins',minBet:1,maxBet:100,games:GAMES_META,botUsername:null};\n    S.demo=true;S.realMode=false;S.crashHistory=demoCrashHist();setBal(1000);renderGrid();renderStats();renderModeTag();\n    showBanner('Connection issue - running in preview mode. '+(err&&err.message?err.message:''),true);\n  }\n  document.getElementById('muteBtn').innerHTML=sfx.muted?ICON.muteOff:ICON.muteOn;\n  if(!S.realMode)startReconnect();\n}\n\n/* ============================== VIEWS ============================== */\ndocument.querySelectorAll('#tabs button').forEach(b=>b.onclick=()=>{\n  sfx.click();hap();\n  document.querySelectorAll('#tabs button').forEach(x=>x.classList.remove('on'));\n  b.classList.add('on');\n  document.querySelectorAll('.view').forEach(v=>v.classList.remove('on'));\n  const view=b.dataset.view;\n  $('view-'+view).classList.add('on');\n  if(view==='spin')renderSpin();\n  if(view==='wallet')renderWallet();\n  if(view==='board')renderBoard();\n  if(view==='admin')renderAdmin();\n});\nasync function renderAdmin(){\n  if(!S.isAdmin){return;}\n  const res=await api('/api/admin');\n  if(!res||!res.ok){toast(res&&res.error?res.error:'Admin data unavailable');return;}\n  $('adUsers').textContent=res.users||0;\n  $('adBalance').textContent=fmt(res.total_balance||0);\n  $('adGames').textContent=res.games||0;\n  $('adEdge').textContent=fmt(res.house_edge||0);\n  const pg=$('adPerGame');\n  if(pg&&res.per_game){\n    const entries=Object.entries(res.per_game);\n    pg.innerHTML=entries.length?entries.map(([g,s])=>\n      `<div class=\"row\"><div class=\"icon-ring\">${ICON[g]||ICON.dice}</div>\n      <div class=\"grow\"><div class=\"t1\">${em(gameName(g))}</div>\n      <div class=\"t2\">${s.games||0} games</div></div>\n      <div class=\"amt\">${fmt((s.wagered||0)-(s.paid||0))}</div></div>`).join('')\n      :`<div class=\"empty\">No games yet.</div>`;\n  }\n  const rc=$('adRecent');\n  if(rc&&res.recent){\n    rc.innerHTML=res.recent.length?res.recent.map(r=>{\n      const win=(r.payout||0)>0;\n      return `<div class=\"row\"><div class=\"icon-ring\">${ICON[r.game]||ICON.dice}</div>\n      <div class=\"grow\"><div class=\"t1\">#${r.id} - user ${r.user_id} - ${em(gameName(r.game))}</div>\n      <div class=\"t2\">${r.status} - bet ${fmt(r.bet)}</div></div>\n      <div class=\"amt ${win?'pos':'neg'}\">${win?'+':''}${fmt(r.payout||0)}</div></div>`;\n    }).join(''):`<div class=\"empty\">No rounds recorded.</div>`;\n  }\n}\nfunction renderSpin(){\n  openGameInto('crash','spinPanel',true);\n}\n\nlet currentCat='all';\nfunction tilesHTML(games){\n  return games.map(g=>{\n    const icon=ICON[g&&g.id]||ICON.dice;\n    const name=(g&&g.name)||'Game';\n    const tag=(g&&g.tag)?String(g.tag).toUpperCase():'';\n    return `\n    <div class=\"tile\" onclick=\"sfx.click();hap();openGame('${(g&&g.id)||''}')\">\n      <span class=\"tg\">${em(tag)}</span>\n      <div class=\"icon-ring\">${icon}</div>\n      <div class=\"nm\">${em(name)}</div>\n    </div>`;\n  }).join('');\n}\nfunction featuredHTML(g){\n  const icon=ICON[g.id]||ICON.dice;\n  const sub=(g.id==='crash')?'The royal favourite - cash out before the flight ends.':'A table favourite, provably fair every round.';\n  return `\n  <div class=\"featured\" onclick=\"sfx.click();hap();openGame('${g.id}')\">\n    <div class=\"f-stars\"></div>\n    <div class=\"f-plane\">${icon}</div>\n    <span class=\"f-tag\">FEATURED</span>\n    <h2>${em(g.name)}</h2>\n    <div class=\"f-sub\">${sub}</div>\n    <span class=\"f-play\">PLAY</span>\n    <span class=\"f-live\"><i></i>LIVE</span>\n  </div>`;\n}\nfunction ensureCats(games){\n  const row=$('catRow');\n  if(!row)return;\n  const tags=[...new Set(games.map(g=>g.tag).filter(Boolean))];\n  const existing=[...row.querySelectorAll('.cat')].map(b=>b.dataset.cat);\n  for(const t of tags){\n    if(existing.includes(t))continue;\n    const b=document.createElement('button');\n    b.className='cat'+(currentCat===t?' on':'');\n    b.dataset.cat=t;\n    b.textContent=t;\n    b.onclick=()=>setCat(t);\n    row.appendChild(b);\n  }\n}\nfunction renderGrid(){\n  const games=(S.cfg&&S.cfg.games&&S.cfg.games.length)?S.cfg.games:GAMES_META;\n  ensureCats(games);\n  const cats=[...new Set(games.map(g=>g.tag).filter(Boolean))];\n  const featured=games.find(g=>g.id==='crash')||games[0];\n  let html=featuredHTML(featured);\n  if(currentCat==='all'){\n    for(const cat of cats){\n      const items=games.filter(g=>(g.tag||'')===cat);\n      if(!items.length)continue;\n      html+=`<div class=\"sec-title\"><span class=\"bar\"></span>${em(cat)}<span class=\"rule\"></span></div><div class=\"grid sub\">${tilesHTML(items)}</div>`;\n    }\n  }else{\n    const items=games.filter(g=>(g.tag||'')===currentCat);\n    html+=`<div class=\"sec-title\"><span class=\"bar\"></span>${em(currentCat)}<span class=\"rule\"></span></div><div class=\"grid sub\">${tilesHTML(items)}</div>`;\n  }\n  $('grid').innerHTML=html;\n}\nfunction setCat(cat){\n  sfx.click();currentCat=cat;\n  document.querySelectorAll('#catRow .cat').forEach(b=>b.classList.toggle('on',b.dataset.cat===cat));\n  renderGrid();\n}\n\nfunction openGameInto(id,containerId,noBack){\n  S.game=id;S.session=null;\n  const g=(S.cfg.games||GAMES_META).find(x=>x.id===id)||{id:id,name:id,mono:(id[0]||'G').toUpperCase()};\n  renderPanelTo(g,containerId,noBack);\n}\nfunction openGame(id){\n  document.querySelectorAll('.view').forEach(v=>v.classList.remove('on'));\n  $('view-game').classList.add('on');\n  openGameInto(id,'panel',false);\n}\nfunction backGames(){sfx.click();document.querySelectorAll('.view').forEach(v=>v.classList.remove('on'));$('view-games').classList.add('on');}\n\n/* ============================== PANEL SHELL ============================== */\nfunction panelShell(g,inner,betCtrl=true,noBack=false){\n  const min=S.cfg.minBet||1,max=S.cfg.maxBet||100;\n  const icon=ICON[g.id]||ICON.dice;\n  return `\n  <div class=\"panel-head\">\n    ${noBack?'<div style=\"width:42px\"></div>':'<button class=\"back-btn\" onclick=\"backGames()\">&larr;</button>'}\n    <div class=\"icon-ring\">${icon}</div>\n    <div><h2>${em(g.name)}</h2><small>PROVABLY FAIR</small></div>\n  </div>\n  ${inner}\n  <div class=\"hint-msg\" id=\"panelMsg\"></div>\n  <div id=\"resultBox\"></div>\n  <div class=\"fair\" id=\"fairBox\"></div>\n  ${betCtrl?`\n  <div class=\"bet-row\" style=\"margin-top:16px;padding-top:14px;border-top:1px dashed var(--line)\"><label>BET</label><div class=\"bet-input\">\n    <input type=\"number\" id=\"betIn\" min=\"${min}\" max=\"${max}\" step=\"1\" value=\"${Math.max(min,Math.min(max,S.bet||min))}\"></div></div>\n  <div class=\"bet-row\"><label>SEED</label><div class=\"bet-input\">\n    <input type=\"text\" id=\"clientSeedIn\" placeholder=\"optional - your fair seed\" maxlength=\"64\" value=\"${S.clientSeed||''}\"></div></div>\n  <div class=\"chips\">\n    <button onclick=\"sfx.click();setBet('min')\">MIN</button>\n    <button onclick=\"sfx.click();setBet('p25')\">25%</button>\n    <button onclick=\"sfx.click();setBet('p50')\">50%</button>\n    <button onclick=\"sfx.click();setBet('max')\">MAX</button>\n  </div>`:''}`;\n}\nfunction setBet(kind){\n  const min=S.cfg.minBet||1,max=S.cfg.maxBet||100;\n  const bal=S.balance||0;\n  const pct=v=>Math.max(min,Math.min(max,Math.floor(bal*v/100)));\n  $('betIn').value=fmt(kind==='min'?min:kind==='p25'?pct(25):kind==='p50'?pct(50):max);\n}\nfunction getBet(){const v=parseFloat($('betIn')&&$('betIn').value);return isNaN(v)?0:v;}\n\nfunction renderPanelTo(g,containerId,noBack){\n  const m={crash:pnlCrash,mines:pnlMines,blackjack:pnlBJ,plinko:pnlPlinko};\n  // Only one game panel may exist at a time (unique element ids).\n  if(containerId==='panel'){const s=$('spinPanel');if(s)s.innerHTML='';}\n  else if(containerId==='spinPanel'){const p=$('panel');if(p)p.innerHTML='';}\n  S.gameContainer=containerId;S.gameNoBack=!!noBack;\n  $(containerId).innerHTML=panelShell(g,(m[g.id]||pnlDice)(),true,noBack);\n  // Plinko: draw the peg board immediately so the panel never looks empty.\n  if(g.id==='plinko'){try{drawPlinko();}catch(e){}}\n  if(g.id==='crash'){try{startFeed();}catch(e){}}\n  $('betIn')&&($('betIn').oninput=()=>{S.bet=parseFloat($('betIn').value)||0;});\n  renderHist();\n}\nfunction renderPanel(g){\n  renderPanelTo(g,'panel',false);\n}\n\nfunction showResult(res){\n  const box=$('resultBox');\n  if(!box)return;\n  if(res&&res.ok===false){box.innerHTML=`<div class=\"result lose\"><div class=\"lbl\">ERROR</div><div class=\"sub\">${em(res.error||'Request failed')}</div></div>`;return;}\n  if(res&&res.won===null)return;\n  if(res&&res.payout!==undefined){\n    S.balance=res.balance!==undefined?res.balance:S.balance;\n    setBal(S.balance);\n    const win=res.won&&res.payout>0;\n    const push=res.push;\n    if(win){sfx.win();if(res.payout>=((res.bet||1)*5)){sfx.bigwin();confettiBurst();}}\n    else if(push)sfx.coin();else sfx.lose();\n    box.innerHTML=`<div class=\"result ${win?'win':'lose'}\">\n      <div class=\"lbl\">${push?'PUSH':win?'YOU WIN':'ROUND LOST'}</div>\n      <div class=\"big\">${push?'RETURNED':(win?'+'+fmt(res.payout):'-'+fmt((res.bet||0)-(res.payout||0)||0))}</div>\n      <div class=\"sub\">Balance: <b>${fmt(S.balance)}</b></div></div>\n      <button class=\"primary replay-btn\" onclick=\"replayGame()\">Play Again</button>\n      <button class=\"primary alt\" style=\"margin-top:8px\" onclick=\"shareResult()\">Share Result</button>`;\n  }\n  if(res&&res.fair){\n    $('fairBox').innerHTML=`Seed <code>${res.fair.seed_hash}...</code> Nonce <code>${res.fair.nonce}</code>`;\n  }\n}\nfunction replayGame(){\n  sfx.click();\n  const box=$('resultBox'),fair=$('fairBox');\n  const boxHTML=box?box.innerHTML:'';\n  const fairHTML=fair?fair.innerHTML:'';\n  const g=(S.cfg.games||GAMES_META).find(x=>x.id===S.game)||{id:S.game,name:S.game,tag:''};\n  S.session=null;\n  renderPanelTo(g,S.gameContainer||'panel',!!S.gameNoBack);\n  const nb=$('resultBox');if(nb&&boxHTML)nb.innerHTML=boxHTML.replace('Play Again','');\n  const nf=$('fairBox');if(nf&&fairHTML)nf.innerHTML=fairHTML;\n}\nwindow.addEventListener('error',function(e){\n  try{toast('Error: '+(e.message||'unknown'));}catch(x){}\n});\n\n/* Share/copy the last round result. */\nasync function shareResult(){\n  const g=(S.cfg.games||GAMES_META).find(x=>x.id===S.game)||{name:'Game'};\n  const rb=$('resultBox');\n  const text='Casino Royals - '+g.name+': '+(rb?rb.textContent.replace(/\\s+/g,' ').trim().slice(0,140):'');\n  try{\n    await navigator.clipboard.writeText(text);\n    toast('Result copied - paste it anywhere!');\n  }catch(e){\n    toast('Copy failed: '+text.slice(0,80));\n  }\n}\n\nasync function doPlay(game,action,data){\n  if(S.busy)return;S.busy=true;\n  const si=$('clientSeedIn');\n  if(si){S.clientSeed=String(si.value||'').slice(0,64);if(S.clientSeed)data=Object.assign({},data,{client_seed:S.clientSeed});}\n  let res;\n  if(S.realMode){\n    res=await api('/api/play',{game,action,data});\n    if(res&&res.offline){res={ok:false,error:'No connection to the server.'};}\n  }else{\n    res=demoResult(game,action,data);\n    if(res.offline)res={ok:false,error:'Offline'};\n  }\n  S.busy=false;\n  if(S.realMode&&res&&res.balance!==undefined){S.balance=res.balance;setBal(res.balance);}\n  if(res&&res.ok&&res.result)res=Object.assign({balance:res.balance},res.result);\n  return res;\n}\n\n/* ============================== DICE ============================== */\nlet diceDir='over',diceTarget=50;\nfunction pnlDice(){\n  return `\n  <div class=\"dice-stage\"><div class=\"dice-num\" id=\"diceNum\">--</div></div>\n  <div class=\"payout-hint\" id=\"dHint\"></div>\n  <button class=\"primary heartbeat\" onclick=\"playDice()\">Roll The Dice</button>\n  <div class=\"ctrl-row\" style=\"margin-top:14px\">\n    <button class=\"ctrl on\" id=\"dOver\" onclick=\"sfx.click();diceDir='over';$('dOver').classList.add('on');$('dUnder').classList.remove('on');updDice()\">Over</button>\n    <button class=\"ctrl\" id=\"dUnder\" onclick=\"sfx.click();diceDir='under';$('dUnder').classList.add('on');$('dOver').classList.remove('on');updDice()\">Under</button>\n  </div>\n  <div class=\"range-row\"><input type=\"range\" id=\"dTarget\" min=\"1\" max=\"100\" value=\"50\" oninput=\"diceTarget=+this.value;updDice()\"><div class=\"val\" id=\"dTargetVal\">50</div></div>`;\n}\nfunction updDice(){\n  $('dTargetVal').textContent=diceTarget;\n  const wins=diceDir==='over'?(100-diceTarget):(diceTarget-1);\n  const m=wins>0?0.97*100/wins:0;\n  $('dHint').innerHTML=`Payout <b>${fmt(m)}x</b> - win <b>${fmt(getBet()*m)}</b>`;\n}\nasync function playDice(){\n  const bet=getBet();if(!bet)return notify('Enter a bet amount.');\n  sfx.roll();\n  const el=$('diceNum');el.classList.add('rolling');\n  const rollAnim=setInterval(()=>{el.textContent=1+Math.floor(Math.random()*100);},80);\n  const res=await doPlay('dice','play',{bet,direction:diceDir,target:diceTarget});\n  setTimeout(()=>{\n    clearInterval(rollAnim);\n    el.classList.remove('rolling');el.classList.add('land');\n    if(res&&res.roll!==undefined)el.textContent=res.roll;\n    setTimeout(()=>el.classList.remove('land'),550);\n    if(res&&res.roll!==undefined){\n      $('resultBox').insertAdjacentHTML('afterbegin',\n        `<div class=\"result ${res.won?'win':'lose'}\"><div class=\"lbl\">DICE</div><div class=\"big\">${res.roll}</div></div>`);\n    }\n    showResult(res);\n  },900);\n}\n\n/* ============================== CRASH (Aviator style) ============================== */\nconst PLANE_PATH='M0 8 L18 1 L30 5 L26 11 L30 15 L18 17 L8 13 L0 8 Z';\nfunction pnlCrash(){\n  return `\n  <div class=\"feed-strip\" id=\"feedStrip\"></div>\n  <div class=\"history-strip\" id=\"histStrip\"></div>\n  <div class=\"crash-stage\" id=\"crashStage\">\n    <div class=\"crash-idle\" id=\"crashIdle\">${ICON.crash}</div>\n    <div class=\"gridlines\"></div>\n    <div class=\"stars\"></div>\n    <canvas id=\"crashCv\"></canvas>\n    <div class=\"crash-mult\" id=\"crashMult\">1.00x</div>\n    <div class=\"crash-bet\" id=\"crashBet\">BET 0</div>\n  </div>\n  <div class=\"opt-row\">\n    <label>AUTO CASHOUT</label>\n    <input type=\"number\" id=\"autoCashIn\" min=\"1.01\" step=\"0.1\" value=\"${crashAutoCash||''}\" placeholder=\"off\" oninput=\"crashAutoCash=parseFloat(this.value)||0\">\n  </div>\n  <div class=\"opt-row\">\n    <label class=\"toggle\"><input type=\"checkbox\" id=\"autoBetIn\" ${crashAutoBet?'checked':''} onchange=\"crashAutoBet=this.checked\"> <span class=\"tknob\"></span> AUTO BET</label>\n    <label>STOP -</label><input type=\"number\" id=\"stopLossIn\" min=\"0\" step=\"1\" value=\"${crashStopLoss}\">\n    <label>WIN +</label><input type=\"number\" id=\"takeProfitIn\" min=\"0\" step=\"1\" value=\"${crashTakeProfit}\">\n  </div>\n  <button class=\"primary heartbeat\" id=\"crashStart\" onclick=\"playCrash()\">Take Off</button>`;\n}\nlet crashAutoCash=0,crashAutoBet=false,crashStopLoss=10,crashTakeProfit=20,crashSessionProfit=0;\nfunction crashCanvasFit(){\n  const cv=$('crashCv');if(!cv)return null;\n  const stage=$('crashStage');\n  const dpr=window.devicePixelRatio||1;\n  const w=stage.clientWidth,h=stage.clientHeight;\n  cv.width=w*dpr;cv.height=h*dpr;\n  const ctx=cv.getContext('2d');\n  if(!ctx)return null;\n  ctx.setTransform(dpr,0,0,dpr,0,0);\n  return {ctx,w,h};\n}\nfunction drawPlane(ctx,x,y,rot,scale){\n  ctx.save();\n  ctx.translate(x,y);ctx.rotate(rot);ctx.scale(scale||1.4,scale||1.4);\n  // flame\n  const fg=ctx.createLinearGradient(0,8,0,26);\n  fg.addColorStop(0,'#fde68a');fg.addColorStop(.5,'#f97316');fg.addColorStop(1,'rgba(239,68,68,0)');\n  ctx.fillStyle=fg;\n  ctx.beginPath();\n  ctx.moveTo(-3.5,8);ctx.lineTo(3.5,8);\n  ctx.lineTo(0,20+Math.random()*5);\n  ctx.closePath();ctx.fill();\n  // body\n  const bg=ctx.createLinearGradient(-9,0,9,0);\n  bg.addColorStop(0,'#cbd5e1');bg.addColorStop(.45,'#ffffff');bg.addColorStop(1,'#94a3b8');\n  ctx.fillStyle=bg;ctx.strokeStyle='#ef4444';ctx.lineWidth=1.1;\n  ctx.beginPath();\n  ctx.moveTo(0,-16);\n  ctx.quadraticCurveTo(10,-9,9,4);\n  ctx.quadraticCurveTo(8.5,11,5,12.5);\n  ctx.lineTo(-5,12.5);\n  ctx.quadraticCurveTo(-8.5,11,-9,4);\n  ctx.quadraticCurveTo(-10,-9,0,-16);\n  ctx.closePath();\n  ctx.fill();ctx.stroke();\n  // fins\n  ctx.fillStyle='#ef4444';\n  ctx.beginPath();ctx.moveTo(-8.5,-2);ctx.lineTo(-15.5,9);ctx.lineTo(-6,7);ctx.closePath();ctx.fill();\n  ctx.beginPath();ctx.moveTo(8.5,-2);ctx.lineTo(15.5,9);ctx.lineTo(6,7);ctx.closePath();ctx.fill();\n  // window\n  ctx.fillStyle='#7dd3fc';ctx.strokeStyle='#1d4ed8';ctx.lineWidth=1;\n  ctx.beginPath();ctx.arc(0,0.5,4.2,0,7);ctx.fill();ctx.stroke();\n  ctx.fillStyle='#0f2a6b';ctx.beginPath();ctx.arc(-1.4,-1,1.3,0,7);ctx.fill();\n  // bunny ears\n  ctx.fillStyle='#f9fafb';ctx.strokeStyle='#ef4444';ctx.lineWidth=.9;\n  ctx.beginPath();ctx.ellipse(-3.4,-23,2.2,6.4,-0.12,0,7);ctx.fill();ctx.stroke();\n  ctx.beginPath();ctx.ellipse(3.4,-23,2.2,6.4,0.12,0,7);ctx.fill();ctx.stroke();\n  ctx.fillStyle='#fca5a5';\n  ctx.beginPath();ctx.ellipse(-3.4,-24,1,3,-0.12,0,7);ctx.fill();\n  ctx.beginPath();ctx.ellipse(3.4,-24,1,3,0.12,0,7);ctx.fill();\n  ctx.restore();\n}\nlet crashLive=null; // shared flight state: {bet,cp,fair,mult,cashed}\n\nasync function playCrash(){\n  const bet=getBet();if(!bet)return notify('Enter a bet amount.');\n  sfx.unlock();\n  const res=await doPlay('crash','play',{bet});\n  if(!res||!res.ok){showResult(res);return;}\n  const cp=res.crash_point;\n  S.crashHistory=(S.crashHistory||[]);\n  S.crashHistory.unshift(Math.round(cp*100)/100);\n  S.crashHistory=S.crashHistory.slice(0,20);\n  renderHist();\n  // Real session id (server mode) - required for cash-out.\n  S.session=Object.assign({},S.session||{},{id:res.session_id||1,game:'crash',bet,cp:cp,started:Date.now(),cashed:false});\n  const ci=$('crashIdle');if(ci)ci.remove();\n  $('crashStart')&&$('crashStart').remove();\n  $('crashBet').textContent='BET '+fmt(bet)+' | WIN '+fmt(bet);\n  // 3-2-1 countdown builds tension before the flight.\n  const cd=document.createElement('div');\n  cd.className='countdown';\n  cd.innerHTML='<b>3</b>';\n  (function(){const st=stageNow();if(st)st.appendChild(cd);})();\n  function stageNow(){return $('crashStage');}\n  let cdLeft=3;\n  await new Promise((resolve)=>{\n    const iv=setInterval(()=>{\n      cdLeft--;\n      if(cdLeft>0){cd.querySelector('b').textContent=cdLeft;sfx.tick();}\n      else{\n        clearInterval(iv);\n        cd.querySelector('b').textContent='GO';\n        cd.classList.add('go');\n        sfx.fanfare&&sfx.click();\n        setTimeout(()=>{cd.remove();resolve();},420);\n      }\n    },650);\n  });\n  const fit=crashCanvasFit();\n  let particles=[];\n  let raf=null;\n  const stage=$('crashStage');\n  const DUR=(window.CRASH_DUR||6500),t0=Date.now();\n  const trail=[];\n  const curveX=f=>0.06+0.84*Math.pow(f,1.25);\n  const curveY=f=>0.9-0.82*Math.pow(f,1.35);\n  // WHERE the rocket explodes is tied to the random crash point:\n  //   cp=1    -> explodes near the start (low, early)\n  //   cp=30+  -> explodes at the top corner\n  // so the explosion looks random every round, exactly like Aviator.\n  const crashT=Math.max(0.06,Math.min(1,Math.log(Math.max(cp,1.01))/Math.log(30)));\n  const multAtF=f=>cp>1?Math.exp(Math.log(cp)*f):1;\n  crashLive={bet:bet,cp:cp,fair:res.fair,mult:null,cashed:false};\n  sfx.tick();\n  function frame(){\n    const t=Math.min(1,(Date.now()-t0)/DUR);\n    const f=crashLive.cashed?crashLive.f:Math.min(1,t/crashT);\n    const mult=crashLive.cashed?crashLive.mult:multAtF(f);\n    const cm=$('crashMult');\n    cm.textContent=fmt(mult)+'x';\n    cm.className='crash-mult '+(mult<2?'m-green':mult<5?'m-yellow':'m-red');\n    $('crashBet').textContent='BET '+fmt(bet)+' | WIN '+fmt(bet*mult);\n    if(!crashLive.cashed&&crashAutoCash>0&&mult>=crashAutoCash&&!crashLive.autoDone){\n      crashLive.autoDone=true;\n      cashCrash();\n      return;\n    }\n    if(fit){\n      const {ctx,w,h}=fit;\n      ctx.clearRect(0,0,w,h);\n      if(!crashLive.cashed){\n        const px=curveX(f)*w,py=curveY(f)*h;\n        trail.push({x:px,y:py});\n        if(trail.length>1){\n          for(let i=1;i<trail.length;i++){\n            const a=trail[i-1],b=trail[i];\n            const alpha=i/trail.length;\n            ctx.strokeStyle='rgba(248,113,113,'+(0.15+0.65*alpha)+')';\n            ctx.lineWidth=2.5+3.5*alpha;\n            ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.stroke();\n          }\n        }\n        const dx=curveX(Math.min(1,f+0.02))*w-px;\n        const dy=curveY(Math.min(1,f+0.02))*h-py;\n        const rot=Math.atan2(dy,dx)+0.35;\n        drawPlane(ctx,px,py,rot,1.35);\n      }else{\n        // Cashed: freeze the rocket on a golden trail.\n        for(let i=1;i<trail.length;i++){\n          ctx.strokeStyle='rgba(245,158,11,'+(0.2+0.5*i/trail.length)+')';\n          ctx.lineWidth=2.5+2.5*i/trail.length;\n          ctx.beginPath();ctx.moveTo(trail[i-1].x,trail[i-1].y);ctx.lineTo(trail[i].x,trail[i].y);ctx.stroke();\n        }\n        if(trail.length){\n          const last=trail[trail.length-1];\n          drawPlane(ctx,last.x-16,last.y-14,-0.9,1.0);\n        }\n        return; // stop the loop on cash-out\n      }\n      particles=particles.filter(p=>p.life>0);\n      particles.forEach(p=>{\n        p.x+=p.vx;p.y+=p.vy;p.vy+=0.15;p.life--;\n        ctx.globalAlpha=Math.max(0,p.life/28);\n        ctx.fillStyle=p.color;\n        ctx.beginPath();ctx.arc(p.x,p.y,p.r,0,7);ctx.fill();\n      });\n      ctx.globalAlpha=1;\n    }\n    if(!crashLive.cashed&&t>=crashT){\n      // BOOM - at the position the random crash point dictates.\n      cancelAnimationFrame(raf);\n      stage.classList.add('boom');\n      sfx.boom();\n      if(fit&&trail.length){\n        const last=trail[trail.length-1];\n        for(let i=0;i<42;i++){\n          particles.push({x:last.x,y:last.y,vx:(Math.random()-0.5)*7,vy:(Math.random()-0.6)*6,\n            life:26+Math.floor(Math.random()*16),r:1.6+Math.random()*3.4,\n            color:['#ef4444','#f87171','#fca5a5','#fbbf24'][i%4]});\n        }\n        const boomFrames=()=>{\n          if(!fit)return;\n          const c2=fit;\n          c2.ctx.clearRect(0,0,c2.w,c2.h);\n          for(let i=1;i<trail.length;i++){\n            c2.ctx.strokeStyle='rgba(248,113,113,.35)';\n            c2.ctx.lineWidth=2.5;\n            c2.ctx.beginPath();c2.ctx.moveTo(trail[i-1].x,trail[i-1].y);c2.ctx.lineTo(trail[i].x,trail[i].y);c2.ctx.stroke();\n          }\n          particles=particles.filter(p=>p.life>0);\n          particles.forEach(p=>{p.x+=p.vx;p.y+=p.vy;p.vy+=0.16;p.life--;\n            c2.ctx.globalAlpha=Math.max(0,p.life/26);c2.ctx.fillStyle=p.color;\n            c2.ctx.beginPath();c2.ctx.arc(p.x,p.y,p.r,0,7);c2.ctx.fill();});\n          c2.ctx.globalAlpha=1;\n          if(particles.length)requestAnimationFrame(boomFrames);\n        };\n        boomFrames();\n      }\n      setTimeout(()=>{stage.classList.remove('boom');},550);\n      S.session=null;\n      crashLive=null;\n      afterCrashSettled({ok:true,won:false,payout:0,bet,balance:S.balance,fair:res.fair});\n      return;\n    }\n    raf=requestAnimationFrame(frame);\n  }\n  raf=requestAnimationFrame(frame);\n  const target=$('panel').querySelector('#cashBtn')?null:null;\n  $('panel').insertAdjacentHTML('beforeend',\n    `<button class=\"primary alt\" id=\"cashBtn\" style=\"margin-top:14px\" onclick=\"cashCrash()\">Cash Out</button>`);\n  const spinC=$('spinPanel');\n  if(spinC&&!$('cashBtn2'))spinC.insertAdjacentHTML('beforeend',\n    `<button class=\"primary alt\" id=\"cashBtn2\" style=\"margin-top:14px\" onclick=\"cashCrash()\">Cash Out</button>`);\n}\nasync function cashCrash(){\n  const btn=$('cashBtn');if(!btn||btn.disabled)return;btn.disabled=true;\n  const b2=$('cashBtn2');if(b2)b2.disabled=true;\n  if(!crashLive||crashLive.cashed)return;\n  const cur=parseFloat($('crashMult').textContent)||1;\n  // Freeze the flight at the cash-out moment.\n  crashLive.cashed=true;\n  crashLive.mult=cur;\n  crashLive.f=Math.min(1,Math.log(Math.max(cur,1.01))/Math.log(Math.max(crashLive.cp,1.01)));\n  sfx.cash();hap('medium');\n  const res=await doPlay('crash','cashout',{session_id:S.session&&S.session.id||1,multiplier:cur});\n  S.session=null;\n  const b1=$('cashBtn');b1&&b1.remove();\n  b2&&b2.remove();\n  crashLive=null;\n  afterCrashSettled(res);\n}\n\n/* Auto-bet engine: re-launches rounds with the same bet until stop-loss or\n   take-profit is reached. */\nlet autoBetBusy=false;\nfunction afterCrashSettled(res){\n  showResult(res);\n  if(!crashAutoBet||autoBetBusy)return;\n  const delta=res&&res.won?(res.payout-res.bet):-(res.bet||0);\n  crashSessionProfit+=delta;\n  const sl=$('stopLossIn'),tp=$('takeProfitIn');\n  const stopL=sl?parseFloat(sl.value)||0:0;\n  const takeP=tp?parseFloat(tp.value)||0:0;\n  if(stopL>0&&crashSessionProfit<=-stopL){\n    crashAutoBet=false;\n    const abi=$('autoBetIn');if(abi)abi.checked=false;\n    toast('Auto-bet stopped: stop-loss hit ('+fmt(crashSessionProfit)+')');\n    return;\n  }\n  if(takeP>0&&crashSessionProfit>=takeP){\n    crashAutoBet=false;\n    const abi=$('autoBetIn');if(abi)abi.checked=false;\n    sfx.bigwin();confettiBurst();\n    toast('Auto-bet stopped: take-profit reached (+'+fmt(crashSessionProfit)+')');\n    return;\n  }\n  autoBetBusy=true;\n  setTimeout(()=>{autoBetBusy=false;if(crashAutoBet)playCrash();},1600);\n}\nfunction curGame(){return (S.cfg.games||GAMES_META).find(x=>x.id===S.game);}\n\n/* ============================== MINES ============================== */\nlet minesCount=3;\nfunction pnlMines(){\n  let chips='';\n  for(let m2=1;m2<=10;m2++){\n    chips+=`<button class=\"cat ${m2===minesCount?'on':''}\" onclick=\"sfx.click();minesCount=${m2};renderPanel(curGame())\">${m2}</button>`;\n  }\n  return `\n  <div class=\"board\"><div class=\"mines-grid\" id=\"mGrid\"></div></div>\n  <div class=\"payout-hint\" id=\"minesHint\">Pick your bomb count (1-10)</div>\n  <button class=\"primary heartbeat\" id=\"mStart\" onclick=\"startMines()\">Start Round</button>\n  <div class=\"cat-row\" style=\"margin-top:14px\">${chips}</div>`;\n}\nasync function startMines(){\n  const bet=getBet();if(!bet)return notify('Enter a bet amount.');\n  sfx.click();\n  const res=await doPlay('mines','new',{bet,mines:minesCount});\n  if(!res||!res.ok){showResult(res);return;}\n  S.session=Object.assign({},S.session||{},{id:res.session_id||1,game:'mines',bet});\n  drawMines(res.fair);\n}\nfunction drawMines(fair){\n  const g=$('mGrid');g.innerHTML='';\n  for(let i=0;i<25;i++){\n    const c=document.createElement('div');c.className='mcell';c.id='mc'+i;\n    c.style.position='relative';\n    c.onclick=()=>revealMine(i);\n    g.appendChild(c);\n  }\n  if(fair)$('fairBox').innerHTML=`Seed <code>${fair.seed_hash}...</code>`;\n  $('mStart').remove();\n  $('panel').insertAdjacentHTML('beforeend',\n    `<div class=\"ctrl-row\" style=\"margin-top:14px\">\n      <button class=\"ctrl\" onclick=\"luckyMine()\">Lucky Pick</button>\n      <button class=\"ctrl\" onclick=\"cashMines()\">Cash Out</button>\n    </div>`);\n}\nfunction luckyMine(){\n  const s=S.session;if(!s||!s.revealed)return;\n  const left=[];\n  for(let i=0;i<25;i++){if(!s.revealed.includes(i))left.push(i);}\n  if(!left.length)return;\n  const pick=left[Math.floor(Math.random()*left.length)];\n  sfx.coin();hap();\n  revealMine(pick);\n}\nfunction minesRisk(res){\n  const s=S.session;if(!s)return;\n  const rev=(res&&res.revealed)?res.revealed.length:(s.revealed?s.revealed.length:0);\n  const mines=s.mines||0;\n  const safe=25-mines-rev;\n  const pct=Math.round(safe/(25-rev)*100);\n  $('minesHint').innerHTML='Next tile safe: <b style=\"color:#4ade80\">'+pct+'%</b> - multiplier <b>'+fmt(res?res.multiplier:1)+'x</b>';\n}\nfunction burst(el){\n  const b=document.createElement('span');b.className='burst';\n  for(let i=0;i<8;i++){\n    const d=document.createElement('i');\n    const a=i*Math.PI/4;\n    d.style.setProperty('--dx',Math.cos(a)*26+'px');\n    d.style.setProperty('--dy',Math.sin(a)*26+'px');\n    b.appendChild(d);\n  }\n  el.appendChild(b);\n  setTimeout(()=>b.remove(),600);\n}\nasync function revealMine(cell){\n  if(!S.session)return;\n  sfx.click();hap();\n  const res=await doPlay('mines','reveal',{session_id:S.session.id,cell});\n  if(res&&res.ok===false){showResult(res);return;}\n  const el=$('mc'+cell);\n  if(res.won===false){\n    el.innerHTML='<div class=\"boom\"></div>';el.classList.add('dead');\n    sfx.boom();\n    (res.revealed||[]).forEach(r=>{const e=$('mc'+r);if(e&&e.children.length===0){e.innerHTML='<div class=\"gem\"></div>';e.classList.add('rev');}});\n    S.session=null;const c=$('mCash');c&&c.remove();\n    showResult(res);\n  }else if(res.won===true){\n    el.innerHTML='<div class=\"gem\"></div>';el.classList.add('rev');\n    burst(el);sfx.coin();\n    S.session=null;const c=$('mCash');c&&c.remove();\n    showResult(res);\n  }else{\n    el.innerHTML='<div class=\"gem\"></div>';el.classList.add('rev');\n    burst(el);sfx.tick();\n    minesRisk(res);\n    $('resultBox').innerHTML=`<div class=\"result lose\"><div class=\"lbl\">MULTIPLIER</div><div class=\"big\">${fmt(res.multiplier)}x</div><div class=\"sub\">Cash out <b>${fmt(res.potential_payout)}</b></div></div>`;\n  }\n}\nasync function cashMines(){\n  if(!S.session)return;\n  sfx.cash();hap('medium');\n  const res=await doPlay('mines','cashout',{session_id:S.session.id});\n  S.session=null;const c=$('mCash');c&&c.remove();\n  showResult(res);\n}\n\n/* ============================== TOWERS ============================== */\nlet towDiff='easy';\nfunction pnlTowers(){\n  return `\n  <div class=\"board\"><div id=\"towBoard\" style=\"display:flex;flex-direction:column;align-items:center\"></div></div>\n  <button class=\"primary heartbeat\" id=\"towStart\" onclick=\"startTowers()\">Start Round</button>\n  <div class=\"ctrl-row\" style=\"margin-top:14px\">\n    ${['easy','medium','hard'].map(d=>`<button class=\"ctrl ${d===towDiff?'on':''}\" onclick=\"sfx.click();towDiff='${d}';renderPanel(curGame())\">${d[0].toUpperCase()+d.slice(1)}</button>`).join('')}\n  </div>`;\n}\nfunction towRowsHTML(cleared,deadRow,deadCol){\n  let h='';\n  for(let r=7;r>=0;r--){\n    h+=`<div style=\"display:flex;gap:7px;margin-bottom:7px\">`;\n    for(let c=0;c<3;c++){\n      const state=r<cleared?'clr':(r===cleared?'cur':(r===deadRow&&c===deadCol?'dead':'fut'));\n      const styles={\n        clr:'border-color:rgba(59,130,246,.6);background:#fff;box-shadow:0 0 14px rgba(59,130,246,.4)',\n        cur:'border-color:rgba(59,130,246,.35);background:linear-gradient(160deg,#fff,#dce9ff)',\n        dead:'border-color:rgba(239,68,68,.7);background:linear-gradient(160deg,#fee2e2,#fecaca)',\n        fut:'border-color:rgba(59,130,246,.16);background:rgba(255,255,255,.65)'}[state];\n      const inner=state==='clr'?'<div class=\"gem\"></div>':state==='dead'?'<div class=\"boom\"></div>':'';\n      const on=state==='cur'?`onclick=\"pickTower(${c})\"`:'';\n      h+=`<div class=\"mcell\" style=\"width:54px;${styles};${state==='cur'?'cursor:pointer':''}\" ${on}>${inner}</div>`;\n    }\n    h+='</div>';\n  }\n  return h;\n}\nasync function startTowers(){\n  const bet=getBet();if(!bet)return notify('Enter a bet amount.');\n  sfx.click();\n  const res=await doPlay('towers','new',{bet,difficulty:towDiff});\n  if(!res||!res.ok){showResult(res);return;}\n  S.session=Object.assign({},S.session||{},{id:res.session_id||1,game:'towers',bet,cleared:0});\n  $('towStart').remove();\n  $('towBoard').innerHTML=towRowsHTML(0,-1,-1);\n  $('fairBox').innerHTML=`Seed <code>${res.fair.seed_hash}...</code>`;\n  $('panel').insertAdjacentHTML('beforeend',\n    `<button class=\"primary alt\" id=\"towCash\" style=\"margin-top:14px\" onclick=\"cashTowers()\">Cash Out</button>`);\n}\nasync function pickTower(col){\n  if(!S.session)return;\n  sfx.click();hap();\n  const res=await doPlay('towers','pick',{session_id:S.session.id,col});\n  if(res&&res.ok===false){showResult(res);return;}\n  if(res.won===false){\n    sfx.boom();\n    $('towBoard').innerHTML=towRowsHTML(S.session.cleared,res.row,col);\n    S.session=null;const c=$('towCash');c&&c.remove();showResult(res);\n  }else if(res.won===true){\n    sfx.coin();\n    $('towBoard').innerHTML=towRowsHTML(8,-1,-1);\n    S.session=null;const c=$('towCash');c&&c.remove();showResult(res);\n  }else{\n    sfx.tick();\n    S.session.cleared=res.row;\n    $('towBoard').innerHTML=towRowsHTML(res.row,-1,-1);\n    $('resultBox').innerHTML=`<div class=\"result lose\"><div class=\"lbl\">MULTIPLIER</div><div class=\"big\">${fmt(res.multiplier)}x</div><div class=\"sub\">Cash out <b>${fmt(res.potential_payout)}</b></div></div>`;\n  }\n}\nasync function cashTowers(){\n  if(!S.session)return;\n  sfx.cash();hap('medium');\n  const res=await doPlay('towers','cashout',{session_id:S.session.id});\n  S.session=null;const c=$('towCash');c&&c.remove();showResult(res);\n}\n\n/* ============================== BLACKJACK ============================== */\nfunction pnlBJ(){\n  return `\n  <div class=\"hand-label\">DEALER</div>\n  <div class=\"cardzone\" id=\"bjDealer\"></div>\n  <div id=\"bjHands\"></div>\n  <div class=\"payout-hint\" id=\"bjHint\"></div>\n  <div id=\"bjControls\"></div>\n  <button class=\"primary\" id=\"bjStart\" onclick=\"startBJ()\">Deal</button>`;\n}\nfunction bjStrategy(hintVal){\n  const v=hintVal||0;\n  if(v<=8)return 'Hit - you cannot bust yet.';\n  if(v===9)return 'Double (9) or hit against a low dealer card.';\n  if(v===10||v===11)return 'Double down (10/11) is the strong play.';\n  if(v===12)return 'Hit vs dealer 2/3/7+, stand vs 4-6.';\n  if(v>=13&&v<=16)return 'Stand vs dealer 2-6, hit vs 7+.';\n  if(v>=17)return 'Stand - 17+ is a made hand.';\n  return '';\n}\nfunction bjRender(res){\n  if(!res)return;\n  const dealBack=c=>c==='?'?'<div class=\"pcard back\"></div>':`<div class=\"pcard flip-in\">${c}</div>`;\n  if(res.dealer)$('bjDealer').innerHTML=res.dealer.map(dealBack).join('');\n  if(res.hands){\n    let h='';\n    res.hands.forEach((hd,i)=>{\n      const cls=hd.active?'':'opacity:.55';\n      const lbl=res.hands.length>1?('HAND '+(i+1)+(hd.active?' - ACTIVE':'')):'YOUR HAND';\n      h+=`<div style=\"${cls}\"><div class=\"hand-label\">${lbl} - ${hd.value}${hd.bet?' - BET '+fmt(hd.bet):''}</div>\n        <div class=\"cardzone\">${hd.cards.map(c=>`<div class=\"pcard flip-in\">${c}</div>`).join('')}</div></div>`;\n    });\n    $('bjHands').innerHTML=h;\n  }\n  if(res.insurance_offered){\n    $('bjControls').innerHTML=`\n      <div class=\"payout-hint\">Dealer shows an Ace - take insurance? (pays 2:1 on a blackjack)</div>\n      <div class=\"ctrl-row\">\n        <button class=\"ctrl on\" onclick=\"bjAct('insure')\">Insure</button>\n        <button class=\"ctrl\" onclick=\"bjAct('decline')\">No Thanks</button>\n      </div>`;\n  }else if(res.hands){\n    const cur=res.hands.find(hd=>hd.active)||res.hands[0];\n    const hint=res.current_value!==undefined?bjStrategy(res.current_value):'';\n    $('bjControls').innerHTML=`\n      <div class=\"ctrl-row\">\n        <button class=\"ctrl on\" onclick=\"bjAct('hit')\">Hit</button>\n        <button class=\"ctrl\" onclick=\"bjAct('stand')\">Stand</button>\n        <button class=\"ctrl\" ${res.can_double?'':'style=\"opacity:.4\"'} onclick=\"bjAct('double')\">Double</button>\n        <button class=\"ctrl\" ${res.can_split?'':'style=\"opacity:.4\"'} onclick=\"bjAct('split')\">Split</button>\n        <button class=\"ctrl\" ${res.can_surrender?'':'style=\"opacity:.4\"'} onclick=\"bjAct('surrender')\">Surrender</button>\n      </div>\n      <div class=\"payout-hint\">${hint?hint:'Double only on hard 9-11 - split pairs up to 3 times.'}</div>`;\n  }\n}\nasync function startBJ(){\n  const bet=getBet();if(!bet)return notify('Enter a bet amount.');\n  sfx.deal();\n  const res=await doPlay('blackjack','new',{bet});\n  if(!res||!res.ok){showResult(res);return;}\n  S.session=Object.assign({},S.session||{},{id:res.session_id||1,game:'blackjack',bet});\n  $('fairBox').innerHTML=`Seed <code>${res.fair.seed_hash}...</code>`;\n  $('bjStart').remove();\n  if(res.hands&&res.hands.length===1&&res.hands[0].value===21&&res.won!==undefined){\n    bjSettleView(res);return;\n  }\n  bjRender(res);\n}\nfunction bjSettleView(res){\n  const dealBack=c=>`<div class=\"pcard flip-in\">${c}</div>`;\n  $('bjDealer').innerHTML=res.dealer_cards.map(dealBack).join('');\n  let h='';\n  res.hands.forEach((hd,i)=>{\n    h+=`<div><div class=\"hand-label\">HAND ${i+1} - ${hd.value} - ${hd.outcome.toUpperCase()} ${hd.outcome==='push'?'(PUSH)':hd.outcome==='surrender'?'+'+fmt(hd.payout)+' BACK':hd.outcome==='won'?'+'+fmt(hd.payout):'-'+fmt(hd.bet)}</div>\n      <div class=\"cardzone\">${hd.cards.map(dealBack).join('')}</div></div>`;\n  });\n  $('bjHands').innerHTML=h;\n  if(res.insurance_payout)$('bjHint').innerHTML=`Dealer <b>${res.dealer_value}</b>${res.dealer_blackjack?' - BLACKJACK':''} - Insurance paid <b>${fmt(res.insurance_payout)}</b>`;\n  else $('bjHint').innerHTML=`Dealer <b>${res.dealer_value}</b>${res.dealer_blackjack?' - BLACKJACK':''}`;\n  $('bjControls').innerHTML='';\n  S.session=null;\n  showResult(res);\n}\nasync function bjAct(act){\n  if(!S.session)return;\n  sfx.deal();\n  const res=await doPlay('blackjack',act,{session_id:S.session.id});\n  if(res&&res.ok===false){showResult(res);return;}\n  if(res.hands&&res.won===undefined){bjRender(res);return;}\n  if(res.hands){bjSettleView(res);}\n}\n\n/* ============================== BACCARAT ============================== */\nlet bacSide='player';\nfunction pnlBaccarat(){\n  return `\n  <div class=\"hand-label\">BANKER</div><div class=\"cardzone\" id=\"bacB\"></div>\n  <div class=\"hand-label\">PLAYER</div><div class=\"cardzone\" id=\"bacP\"></div>\n  <div class=\"payout-hint\" id=\"bacHint\"></div>\n  <button class=\"primary heartbeat\" onclick=\"playBac()\">Deal</button>\n  <div class=\"ctrl-row\" style=\"margin-top:14px\">\n    <button class=\"ctrl on\" onclick=\"sfx.click();bacSide='player';updBac()\">Player 2x</button>\n    <button class=\"ctrl\" onclick=\"sfx.click();bacSide='banker';updBac()\">Banker 1.95x</button>\n    <button class=\"ctrl\" onclick=\"sfx.click();bacSide='tie';updBac()\">Tie 9x</button>\n  </div>`;\n}\nfunction updBac(){$('bacHint').innerHTML=`Betting on <b>${bacSide}</b> at ${bacSide==='player'?'2x':bacSide==='banker'?'1.95x':'9x'}`;}\nasync function playBac(){\n  const bet=getBet();if(!bet)return notify('Enter a bet amount.');\n  sfx.deal();\n  const res=await doPlay('baccarat','play',{bet,side:bacSide});\n  if(res&&res.player_cards){\n    $('bacB').innerHTML=res.banker_cards.map(c=>`<div class=\"pcard flip-in\">${c}</div>`).join('');\n    $('bacP').innerHTML=res.player_cards.map(c=>`<div class=\"pcard flip-in\">${c}</div>`).join('');\n    $('bacHint').innerHTML=`Player <b>${res.player_value}</b> - Banker <b>${res.banker_value}</b> - Winner: <b>${res.winner.toUpperCase()}</b>`;\n  }\n  showResult(res);\n}\n\n/* ============================== ROULETTE ============================== */\nlet roulChoice='red';\nfunction pnlRoulette(){\n  return `\n  <div class=\"roul-wheel\"><div class=\"ball\" id=\"roulBall\"></div><div class=\"hub\"><span>CR</span></div></div>\n  <div class=\"ctrl-row\">\n    <button class=\"ctrl on\" onclick=\"sfx.click();roulChoice='red';markRoul()\">Red</button>\n    <button class=\"ctrl\" onclick=\"sfx.click();roulChoice='black';markRoul()\">Black</button>\n    <button class=\"ctrl\" onclick=\"sfx.click();roulChoice='green';markRoul()\">Zero</button>\n    <button class=\"ctrl\" onclick=\"sfx.click();roulChoice='even';markRoul()\">Even</button>\n    <button class=\"ctrl\" onclick=\"sfx.click();roulChoice='odd';markRoul()\">Odd</button>\n    <button class=\"ctrl\" onclick=\"sfx.click();roulChoice='low';markRoul()\">1-18</button>\n    <button class=\"ctrl\" onclick=\"sfx.click();roulChoice='high';markRoul()\">19-36</button>\n  </div>\n  <div class=\"num-pad\" id=\"roulPad\"></div>\n  <button class=\"primary\" onclick=\"playRoul()\">Spin</button>`;\n}\nfunction markRoul(){\n  document.querySelectorAll('#view-game .ctrl').forEach(b=>{\n    const t=b.textContent.trim();\n    const map={'Red':'red','Black':'black','Zero':'green','Even':'even','Odd':'odd','1-18':'low','19-36':'high'};\n    b.classList.toggle('on',map[t]===roulChoice);\n  });\n  document.querySelectorAll('#roulPad button').forEach(b=>b.classList.toggle('on',b.textContent===roulChoice));\n}\nasync function playRoul(){\n  const bet=getBet();if(!bet)return notify('Enter a bet amount.');\n  const res=await doPlay('roulette','play',{bet,choice:roulChoice});\n  $('roulBall').style.transition='none';\n  $('roulBall').style.transform='rotate(0deg)';\n  void $('roulBall').offsetWidth;\n  $('roulBall').style.transition='';\n  requestAnimationFrame(()=>{\n    $('roulBall').style.transform='rotate('+(1800+Math.random()*720)+'deg)';\n  });\n  const tickI=setInterval(()=>sfx.tick(),170);\n  if(res&&res.spin!==undefined){\n    const deg=res.spin*(360/37);\n    setTimeout(()=>{$('roulBall').style.transform='rotate('+(1800+deg)+'deg)';},250);\n    setTimeout(()=>{\n      clearInterval(tickI);\n      $('resultBox').insertAdjacentHTML('afterbegin',\n        `<div class=\"result ${res.won?'win':'lose'}\"><div class=\"lbl\">NUMBER</div><div class=\"big\">${res.spin} ${res.color.toUpperCase()}</div></div>`);\n    },1600);\n  }\n  setTimeout(()=>{clearInterval(tickI);showResult(res);},4400);\n}\n\n/* ============================== HI-LO ============================== */\nfunction pnlHilo(){\n  return `\n  <div class=\"cardzone\" id=\"hiloCard\"></div>\n  <div class=\"payout-hint\" id=\"hiloHint\"></div>\n  <button class=\"primary\" id=\"hiloStart\" onclick=\"startHilo()\">Deal Card</button>`;\n}\nasync function startHilo(){\n  const bet=getBet();if(!bet)return notify('Enter a bet amount.');\n  sfx.deal();\n  const res=await doPlay('hilo','new',{bet});\n  if(!res||!res.ok){showResult(res);return;}\n  S.session=Object.assign({},S.session||{},{id:res.session_id||1,game:'hilo',bet});\n  $('hiloCard').innerHTML=`<div class=\"pcard flip-in\">${res.card}</div>`;\n  $('hiloHint').innerHTML=`Higher <b>${fmt(res.higher_mult)}x</b> - Lower <b>${fmt(res.lower_mult)}x</b> - chain <b>1x</b>`;\n  $('fairBox').innerHTML=`Seed <code>${res.fair.seed_hash}...</code>`;\n  $('hiloStart').remove();\n  $('panel').insertAdjacentHTML('beforeend',`\n    <div class=\"ctrl-row\" style=\"margin-top:14px\">\n      <button class=\"ctrl on\" onclick=\"hiloAct('higher')\">Higher</button>\n      <button class=\"ctrl\" onclick=\"hiloAct('lower')\">Lower</button>\n    </div>\n    <button class=\"primary alt\" onclick=\"hiloAct('cashout')\">Cash Out</button>`);\n}\nasync function hiloAct(act){\n  if(!S.session)return;\n  sfx.deal();\n  const res=await doPlay('hilo',act,{session_id:S.session.id});\n  if(res&&res.ok===false){showResult(res);return;}\n  if(res.card!==undefined&&res.won===undefined){\n    $('hiloCard').innerHTML=`<div class=\"pcard flip-in\">${res.card}</div>`;\n    $('hiloHint').innerHTML=`Higher <b>${fmt(res.higher_mult)}x</b> - Lower <b>${fmt(res.lower_mult)}x</b> - chain <b>${fmt(res.multiplier)}x</b> - cash out <b>${fmt(res.potential_payout)}</b>`;\n    return;\n  }\n  if(res.drawn!==undefined&&res.won===false){\n    $('hiloCard').innerHTML=`<div class=\"pcard flip-in\">${res.drawn}</div>`;\n    if(res.tie)$('hiloHint').innerHTML='Tie - round lost.';\n    S.session=null;showResult(res);return;\n  }\n  S.session=null;showResult(res);\n}\n\n/* ============================== PLINKO ============================== */\nlet plinkoRisk='low',plinkoPos=4,plinkoAuto=false;\nconst PLINKO_TABS={\n  8:[4.41,2.94,1.69,0.73,0.20,0.73,1.69,2.94,4.41],\n  10:[5.18,3.76,2.51,1.46,0.65,0.20,0.65,1.46,2.51,3.76,5.18],\n  12:[5.90,4.54,3.30,2.22,1.30,0.59,0.20,0.59,1.30,2.22,3.30,4.54,5.90]};\nconst plinkoRows=()=>({low:8,medium:10,high:12}[plinkoRisk]||8);\nfunction pnlPlinko(){\n  return `\n  <div class=\"heat-row\" id=\"plinkoHeat\"></div>\n  <div class=\"pos-row\" id=\"plinkoPos\"></div>\n  <div class=\"plinko-board\" id=\"plinkoBoard\"></div>\n  <div class=\"opt-row\">\n    <label class=\"toggle\"><input type=\"checkbox\" id=\"plinkoAutoIn\" ${plinkoAuto?'checked':''} onchange=\"plinkoAuto=this.checked\"> <span class=\"tknob\"></span> AUTO DROP</label>\n  </div>\n  <div class=\"ctrl-row\">\n    <button class=\"ctrl\" onclick=\"luckyDrop()\">Lucky Drop</button>\n    <button class=\"primary heartbeat\" style=\"flex:1.6\" onclick=\"playPlinko()\">Drop Ball</button>\n  </div>\n  <div class=\"ctrl-row\" style=\"margin-top:14px\">\n    ${['low','medium','high'].map(r=>`<button class=\"ctrl ${r===plinkoRisk?'on':''}\" onclick=\"sfx.click();plinkoRisk='${r}';plinkoPos=Math.floor(plinkoRows()/2);renderPanel(curGame())\">${r[0].toUpperCase()+r.slice(1)}</button>`).join('')}\n  </div>`;\n}\nfunction plinkoHeatData(){\n  try{return JSON.parse(localStorage.getItem('cr_plinko_heat')||'[]');}catch(e){return [];}\n}\nfunction plinkoHeatPush(bucket){\n  const h=plinkoHeatData();h.push(bucket);\n  while(h.length>60)h.shift();\n  try{localStorage.setItem('cr_plinko_heat',JSON.stringify(h));}catch(e){}\n  drawPlinkoHeat();\n}\nfunction drawPlinkoHeat(){\n  const el=$('plinkoHeat');if(!el)return;\n  const rows=plinkoRows();\n  const h=plinkoHeatData();\n  const counts=new Array(rows+1).fill(0);\n  h.forEach(b=>{if(b>=0&&b<=rows)counts[b]++;});\n  const mx=Math.max(1,...counts);\n  let html='';\n  counts.forEach((c,i)=>{\n    const pct=Math.round(c/mx*100);\n    html+=`<div class=\"heat-cell\"><div class=\"hfill\" style=\"height:${pct}%\"></div><span>${c}</span></div>`;\n  });\n  el.innerHTML=html;\n}\nfunction drawPlinkoPos(){\n  const el=$('plinkoPos');if(!el)return;\n  const rows=plinkoRows();\n  let html='';\n  for(let i=0;i<=rows;i++){\n    html+=`<button class=\"pos ${i===plinkoPos?'on':''}\" onclick=\"sfx.click();plinkoPos=${i};drawPlinkoPos()\">${i}</button>`;\n  }\n  el.innerHTML=html;\n}\nfunction drawPlinko(){\n  const b=$('plinkoBoard');b.innerHTML='';\n  const rows=plinkoRows();\n  const tabs=PLINKO_TABS[rows];\n  tabs.forEach((m,i)=>{\n    const d=document.createElement('div');d.className='pbucket';d.id='pb'+i;\n    d.textContent=fmt(m)+'x';d.style.left=(i*(100/(rows+1)))+'%';d.style.width=(100/(rows+1))+'%';\n    b.appendChild(d);\n  });\n  const boardH=Math.max(260,rows*26+70);\n  b.style.height=boardH+'px';\n  for(let r=0;r<rows;r++){\n    const pegs=r+1;\n    for(let pi=0;pi<pegs;pi++){\n      const peg=document.createElement('div');peg.className='ppeg';\n      peg.style.left=(9+((pi+0.5)/pegs)*82)+'%';\n      peg.style.top=(26+r*24)+'px';\n      b.appendChild(peg);\n    }\n  }\n  drawPlinkoHeat();\n  drawPlinkoPos();\n}\nfunction luckyDrop(){\n  plinkoPos=Math.floor(Math.random()*(plinkoRows()+1));\n  sfx.coin();hap();\n  drawPlinkoPos();\n  playPlinko();\n}\nasync function playPlinko(){\n  const bet=getBet();if(!bet)return notify('Enter a bet amount.');\n  drawPlinko();\n  const rows=plinkoRows();\n  const board=$('plinkoBoard');\n  const ball=document.createElement('div');ball.className='pball';ball.id='pball';\n  ball.style.left=((9+((plinkoPos+0.5)/(rows+1))*82))+'%';\n  board.appendChild(ball);\n  const res=await doPlay('plinko','play',{bet,risk:plinkoRisk,position:plinkoPos});\n  const bucket=(res&&res.bucket!==undefined)?res.bucket:Math.floor(rows/2);\n  // Visual bounce: drift randomly, then land in the decided bucket.\n  let cell=plinkoPos;\n  const steps=[];\n  for(let r=1;r<=rows;r++){\n    if(r<rows){\n      const dir=Math.random()<0.5?-1:1;\n      cell=Math.max(0,Math.min(r,cell+dir));\n    }else{\n      cell=bucket;\n    }\n    steps.push({row:r,cell});\n  }\n  let si=0;\n  const tick=()=>{\n    if(si>=steps.length){\n      ball.style.top='92%';\n      setTimeout(()=>{\n        document.querySelectorAll('.pbucket').forEach((b2,i)=>b2.classList.toggle('hit',i===bucket));\n        plinkoHeatPush(bucket);\n        if(plinkoAuto){\n          setTimeout(playPlinko,1400);\n        }else{\n          showResult(res);\n        }\n      },260);\n      return;\n    }\n    const st=steps[si++];\n    const total=rows+1,w=82/total;\n    ball.style.left=(9+w/2+st.cell*w)+'%';\n    ball.style.top=(20+st.row*24)+'px';\n    sfx.tick();\n    setTimeout(tick,140);\n  };\n  setTimeout(tick,80);\n}\n\n/* ============================== KENO ============================== */\nlet kenoPicks=new Set();\nfunction pnlKeno(){\n  kenoPicks=new Set();\n  let cells='';\n  for(let i=1;i<=80;i++)cells+=`<div class=\"kcell\" id=\"k${i}\" onclick=\"toggleKeno(${i})\">${i}</div>`;\n  return `\n  <div class=\"keno-status\" id=\"kenoStatus\">Pick 1 to 10 numbers</div>\n  <div class=\"board\"><div class=\"keno-grid\">${cells}</div></div>\n  <button class=\"primary\" onclick=\"playKeno()\">Play Keno</button>`;\n}\nfunction toggleKeno(n){\n  sfx.click();\n  const el=$('k'+n);\n  if(kenoPicks.has(n)){kenoPicks.delete(n);el.classList.remove('sel');}\n  else if(kenoPicks.size<10){kenoPicks.add(n);el.classList.add('sel');}\n  $('kenoStatus').textContent=`Pick 1 to 10 numbers - selected ${kenoPicks.size}`;\n}\nasync function playKeno(){\n  if(!kenoPicks.size)return notify('Pick at least one number.');\n  const bet=getBet();if(!bet)return notify('Enter a bet amount.');\n  const res=await doPlay('keno','play',{bet,picks:[...kenoPicks]});\n  if(res&&res.drawn){\n    res.drawn.forEach((n,i)=>{\n      setTimeout(()=>{\n        const el=$('k'+n);\n        el.classList.add(kenoPicks.has(n)?'both':'hit');\n        if(kenoPicks.has(n))sfx.coin();else sfx.tick();\n      },i*260);\n    });\n    setTimeout(()=>{\n      $('kenoStatus').textContent=`Hits: ${res.hits.length} - payout ${fmt(res.multiplier)}x`;\n      showResult(res);\n    },res.drawn.length*260+300);\n  }\n}\n\n/* ============================== WHEEL ============================== */\nconst WHEEL_SEGS=[{m:0,w:30,c:'#dbeafe'},{m:0.9,w:42,c:'#bfdbfe'},{m:1.3,w:14,c:'#93c5fd'},\n  {m:1.7,w:7,c:'#60a5fa'},{m:2.6,w:4,c:'#3b82f6'},{m:4.3,w:2,c:'#2563eb'},{m:8.5,w:1,c:'#f59e0b'}];\nfunction pnlWheel(){\n  let total=WHEEL_SEGS.reduce((a,s)=>a+s.w,0);\n  let segs='',acc=0;\n  WHEEL_SEGS.forEach(s=>{\n    const a0=acc/total*360,a1=(acc+s.w)/total*360;\n    segs+=`<path d=\"${arc(115,115,110,a0,a1)}\" fill=\"${s.c}\" stroke=\"#fff\" stroke-width=\"2.5\"/>`;\n    const mid=(a0+a1)/2*Math.PI/180;\n    segs+=`<text x=\"${115+92*Math.sin(mid)}\" y=\"${115-92*Math.cos(mid)+5}\" text-anchor=\"middle\" font-family=\"Georgia,serif\" font-size=\"15\" font-weight=\"800\" fill=\"${s.c==='#f59e0b'?'#fff':'#1e3a8a'}\">${s.m}x</text>`;\n    acc+=s.w;\n  });\n  return `\n  <div class=\"wheel-wrap\">\n    <div class=\"wheel-pointer\"></div>\n    <svg class=\"wheel-svg\" id=\"wheelSvg\" viewBox=\"0 0 230 230\">${segs}</svg>\n  </div>\n  <button class=\"primary\" onclick=\"playWheel()\">Spin The Wheel</button>`;\n}\nfunction arc(cx,cy,r,a0,a1){\n  const p=(a)=>[cx+r*Math.sin(a*Math.PI/180),cy-r*Math.cos(a*Math.PI/180)];\n  const [x0,y0]=p(a0),[x1,y1]=p(a1);\n  const large=a1-a0>180?1:0;\n  return `M ${cx} ${cy} L ${x0} ${y0} A ${r} ${r} 0 ${large} 1 ${x1} ${y1} Z`;\n}\nasync function playWheel(){\n  const bet=getBet();if(!bet)return notify('Enter a bet amount.');\n  const res=await doPlay('wheel','play',{bet});\n  const idx=(res&&res.segment!==undefined)?res.segment:0;\n  let total=WHEEL_SEGS.reduce((a,s)=>a+s.w,0),acc=0;\n  for(let i=0;i<idx;i++)acc+=WHEEL_SEGS[i].w;\n  const target=(acc+WHEEL_SEGS[idx].w/2)/total*360;\n  const rot=1800+(360-target)+90;\n  const svg=$('wheelSvg');\n  svg.style.transition='none';svg.style.transform='rotate(0deg)';\n  void svg.offsetWidth;svg.style.transition='';\n  requestAnimationFrame(()=>{svg.style.transform='rotate('+rot+'deg)';});\n  const tickI=setInterval(()=>sfx.tick(),140);\n  setTimeout(()=>{clearInterval(tickI);showResult(res);},4500);\n}\n\n/* ============================== LIMBO ============================== */\nlet limboTarget=2;\nfunction pnlLimbo(){\n  const t=limboTarget,p=(1e8-t*1e6)/1e8,m=0.97/p;\n  return `\n  <div class=\"limbo-beam\">\n    <div class=\"limbo-num\" id=\"limboNum\">1.00x</div>\n    <div class=\"limbo-dot\" id=\"limboDot\" style=\"bottom:12px\"></div>\n  </div>\n  <div class=\"payout-hint\">Win chance <b>${fmt(p*100)}%</b> - payout <b>${fmt(m)}x</b></div>\n  <button class=\"primary heartbeat\" onclick=\"playLimbo()\">Launch</button>\n  <div class=\"limbo-target\" style=\"margin-top:14px\">\n    <label>TARGET</label>\n    <input type=\"number\" id=\"limboIn\" value=\"${limboTarget}\" step=\"0.01\" min=\"1.01\" oninput=\"limboTarget=parseFloat(this.value)||2;updLimbo()\">\n    <div class=\"val\" id=\"limboMult\">${fmt(m)}x</div>\n  </div>`;\n}\nfunction updLimbo(){\n  const t=Math.max(1.01,Math.min(100000,limboTarget));\n  const p=(1e8-t*1e6)/1e8,m=0.97/p;\n  $('limboMult').textContent=fmt(m)+'x';\n}\nasync function playLimbo(){\n  const bet=getBet();if(!bet)return notify('Enter a bet amount.');\n  const res=await doPlay('limbo','play',{bet,target:limboTarget});\n  if(res&&res.multiplier!==undefined){\n    const dot=$('limboDot'),num=$('limboNum');\n    const m=res.multiplier;\n    const target=res.target;\n    const climb=Math.min(1,(m/target));\n    dot.style.bottom=(12+climb*210)+'px';\n    const t0=Date.now();\n    const iv=setInterval(()=>{\n      const t=Math.min(1,(Date.now()-t0)/1400);\n      num.textContent=fmt(1+(m-1)*t)+'x';\n      if(t>=1){clearInterval(iv);num.textContent=fmt(m)+'x';\n        if(res.won)sfx.win();else sfx.lose();}\n    },40);\n    if(res.won)sfx.tick();\n    $('resultBox').insertAdjacentHTML('afterbegin',\n      `<div class=\"result ${res.won?'win':'lose'}\"><div class=\"lbl\">TARGET ${fmt(target)}x</div><div class=\"big\">${fmt(m)}x</div></div>`);\n  }\n  showResult(res);\n}\n\n/* ============================== COIN FLIP ============================== */\nlet coinSide='heads';\nfunction pnlCoin(){\n  return `\n  <div class=\"coin-stage\"><div class=\"coin\" id=\"coinEl\">CR</div></div>\n  <div class=\"ctrl-row\">\n    <button class=\"ctrl on\" onclick=\"sfx.click();coinSide='heads'\">Heads</button>\n    <button class=\"ctrl\" onclick=\"sfx.click();coinSide='tails'\">Tails</button>\n  </div>\n  <div class=\"payout-hint\">Payout <b>1.94x</b></div>\n  <button class=\"primary\" onclick=\"playCoin()\">Flip</button>`;\n}\nasync function playCoin(){\n  const bet=getBet();if(!bet)return notify('Enter a bet amount.');\n  sfx.coin();\n  $('coinEl').classList.remove('flip');void $('coinEl').offsetWidth;\n  $('coinEl').classList.add('flip');\n  const res=await doPlay('coinflip','play',{bet,side:coinSide});\n  if(res&&res.landed){\n    setTimeout(()=>{\n      $('coinEl').textContent=res.landed==='heads'?'H':'T';\n      $('resultBox').insertAdjacentHTML('afterbegin',\n        `<div class=\"result ${res.won?'win':'lose'}\"><div class=\"lbl\">LANDED</div><div class=\"big\">${res.landed.toUpperCase()}</div></div>`);\n    },760);\n  }\n  setTimeout(()=>showResult(res),1600);\n}\n\n/* ============================== SLOTS ============================== */\nfunction pnlSlots(){\n  return `\n  <div class=\"slots-row\">\n    <div class=\"sreel\" id=\"sr0\"><div class=\"strip\"></div></div>\n    <div class=\"sreel\" id=\"sr1\"><div class=\"strip\"></div></div>\n    <div class=\"sreel\" id=\"sr2\"><div class=\"strip\"></div></div>\n  </div>\n  <button class=\"primary\" onclick=\"playSlots()\">Spin</button>`;\n}\nconst SLOT_SYM=['C','R','7','A','K','Q','J'];\nfunction fillReel(el,stopAt){\n  const strip=el.querySelector('.strip');\n  let syms=[];\n  for(let i=0;i<12;i++)syms.push(SLOT_SYM[Math.floor(Math.random()*SLOT_SYM.length)]);\n  syms[10]=stopAt;\n  strip.innerHTML=syms.map(s=>`<span>${s}</span>`).join('');\n}\nasync function playSlots(){\n  const bet=getBet();if(!bet)return notify('Enter a bet amount.');\n  const res=await doPlay('slots','play',{bet});\n  const reel=(res&&res.reel)?res.reel:[SLOT_SYM[0],SLOT_SYM[0],SLOT_SYM[0]];\n  [0,1,2].forEach(i=>{const el=$('sr'+i);el.classList.remove('win');el.classList.add('spinning');fillReel(el,reel[i]);});\n  sfx.roll();\n  setTimeout(()=>{\n    [0,1,2].forEach(i=>{\n      const el=$('sr'+i);el.classList.remove('spinning');\n      el.querySelector('.strip').style.transform='translateY(-'+(10*104)+'px)';\n    });\n    if(res&&res.won&&res.reel&&res.reel.every(x=>x===res.reel[0])){\n      [0,1,2].forEach(i=>$('sr'+i).classList.add('win'));\n      sfx.bigwin();\n    }\n    showResult(res);\n  },1700);\n}\n\n/* ============================== WALLET / BOARD ============================== */\nfunction renderStats(){\n  const st=S.stats||{};\n  $('stGames').textContent=st.games||0;\n  $('stWagered').textContent=fmt(st.wagered||0);\n  const net=(st.paid||0)-(st.wagered||0);\n  const netEl=$('stNet');\n  netEl.textContent=(net>=0?'+':'')+fmt(net);\n  netEl.style.color=net>=0?'#4ade80':'#f87171';\n  const streak=(S.profile&&S.profile.streak)||0;\n  const stEl=$('stStreak');\n  stEl.textContent=(streak>0?'W':'L')+Math.abs(streak);\n  stEl.style.color=streak>=0?'#4ade80':'#f87171';\n  // daily chart\n  const chart=$('walletChart');\n  if(chart&&S.profile&&S.profile.daily){\n    const days=S.profile.daily;\n    const mx=Math.max(1,...days.map(d=>Math.max(d.wagered,d.paid)));\n    chart.innerHTML=days.map((d,i)=>{\n      const h=Math.max(3,Math.round(d.wagered/mx*86));\n      const win=d.paid>d.wagered;\n      const lbl=String(i+1);\n      return `<div class=\"bar ${win?'win':''}\" style=\"height:${h}px;animation-delay:${i*0.05}s\" title=\"${d.date}: w ${fmt(d.wagered)} p ${fmt(d.paid)}\"><span>${lbl}</span></div>`;\n    }).join('');\n  }\n  // per-game stats\n  const pg=$('perGame');\n  if(pg&&S.profile&&S.profile.per_game){\n    const entries=Object.entries(S.profile.per_game);\n    pg.innerHTML=entries.length?entries.map(([g,s])=>{\n      const win=(s.paid||0)>(s.wagered||0);\n      return `<div class=\"row\"><div class=\"icon-ring\">${ICON[g]||ICON.dice}</div>\n        <div class=\"grow\"><div class=\"t1\">${em(gameName(g))}</div>\n        <div class=\"t2\">${s.wins||0}W / ${s.losses||0}L - biggest ${fmt(s.biggest||0)}</div></div>\n        <div class=\"amt ${win?'pos':'neg'}\">${win?'+':''}${fmt((s.paid||0)-(s.wagered||0))}</div></div>`;\n    }).join(''):`<div class=\"empty\">Play a few rounds to build your stats.</div>`;\n  }\n}\nfunction renderWallet(){\n  renderStats();\n  const hist=S.history||[];\n  $('history').innerHTML=hist.length?hist.map(h=>{\n    const win=(h.payout||0)>0;\n    return `<div class=\"row\"><div class=\"icon-ring\">${ICON[h.game]||ICON.dice}</div>\n      <div class=\"grow\"><div class=\"t1\">${em(gameName(h.game))}</div><div class=\"t2\">${h.status}${h.created_at?' - '+h.created_at.slice(0,16).replace('T',' '):''}</div></div>\n      <div class=\"amt ${win?'pos':'neg'}\">${win?'+':'-'}${fmt(h.payout||0)}</div></div>`;\n  }).join(''):`<div class=\"empty\">No rounds yet.<br>Take a seat at one of the tables.</div>`;\n}\nlet lbPeriod='all',lbMetric='profit';\nfunction lbSet(what,val){\n  sfx.click();\n  if(what==='period')lbPeriod=val;else lbMetric=val;\n  document.querySelectorAll('#lbPeriod .cat').forEach(b=>b.classList.toggle('on',b.dataset.p===lbPeriod));\n  document.querySelectorAll('#lbMetric .cat').forEach(b=>b.classList.toggle('on',b.dataset.m===lbMetric));\n  renderBoard();\n}\nasync function renderBoard(){\n  let b=S.board||[];\n  if(S.realMode){\n    try{\n      const res=await api('/api/leaderboard',{period:lbPeriod,metric:lbMetric});\n      if(res&&res.ok&&res.leaderboard){S.board=res.leaderboard;b=res.leaderboard;}\n    }catch(e){}\n  }\n  const metricLabel={profit:'profit',games:'games',multiplier:'best x'}[lbMetric]||'profit';\n  $('board').innerHTML=b.length?b.map(u=>{\n    const val=lbMetric==='profit'?(u.profit>=0?'+':'')+fmt(u.profit):lbMetric==='games'?u.games:fmt(u.multiplier)+'x';\n    return `\n    <div class=\"row\"><div class=\"rank ${(u.rank||0)<=3?'gold':''}\">${u.rank||(b.indexOf(u)+1)}</div>\n    <div class=\"profile-avatar\" style=\"width:38px;height:38px;font-size:15px\">${em((u.first_name||u.username||'P')[0].toUpperCase())}</div>\n    <div class=\"grow\"><div class=\"t1\">${em(u.first_name||u.username||'Player')}</div>\n    <div class=\"t2\">@${em(u.username||'anonymous')} - ${u.games||0} games</div></div>\n    <div class=\"amt\">${val}</div></div>`;\n  }).join(''):`<div class=\"empty\">The leaderboard populates once players connect through the bot.</div>`;\n}\nfunction walletGo(kind){\n  if(S.demo)return notify('Deposits and withdrawals are handled by the bot after deployment.');\n  const u=S.cfg.botUsername;\n  if(!u)return notify('Bot username not configured. Set TELEGRAM_BOT_TOKEN.');\n  window.open('https://t.me/'+u+(kind==='deposit'?'?start=deposit':''),'_blank');\n  return false;\n}\nfunction gameName(g){const m={dice:'Dice',crash:'Crash',mines:'Mines',towers:'Towers',blackjack:'Blackjack',baccarat:'Baccarat',roulette:'Roulette',hilo:'Hi-Lo',plinko:'Plinko',keno:'Keno',wheel:'Wheel of Fortune',limbo:'Limbo',coinflip:'Coin Flip',slots:'Slots'};return m[g]||g;}\n\n/* ============================== GAME REGISTRY ============================== */\nconst GAMES_META=[\n  {id:'crash',name:'Crash',tag:'Live'},\n  {id:'mines',name:'Mines',tag:'Skill'},\n  {id:'blackjack',name:'Blackjack',tag:'Cards'},\n  {id:'plinko',name:'Plinko',tag:'Instant'},\n];\n\n/* roulette number pad injection after render */\nconst _origRenderPanel=renderPanel;\nrenderPanel=function(g){\n  _origRenderPanel(g);\n  if(g.id==='roulette'){\n    let h='';\n    for(let n=0;n<=36;n++)h+=`<button onclick=\"sfx.click();roulChoice='${n}';markRoul()\">${n}</button>`;\n    $('roulPad').innerHTML=h;\n  }\n};\n\nwindow.skipIntro=skipIntro;\nboot();\n</script>\n</body>\n</html>\n"
# <EMBED-INDEX-END>

_sess_lock = threading.Lock()
MINI_SESSIONS: Dict[int, Dict[str, Any]] = {}  # live in-memory game state
CRASH_HISTORY: List[float] = []  # recent crash points, most recent first
LIVE_FEED: List[Dict[str, Any]] = []  # recent bets across all games (masked)


def feed_push(game: str, name: str, bet: float, multiplier: float) -> None:
    masked = (str(name)[:2] + "***") if name else "Player***"
    LIVE_FEED.insert(0, {
        "game": game, "user": masked, "bet": round(float(bet), 2),
        "multiplier": round(float(multiplier or 0), 2), "ts": int(time.time()),
    })
    del LIVE_FEED[12:]


def crash_history_push(mult: float) -> None:
    CRASH_HISTORY.insert(0, round(float(mult), 2))
    del CRASH_HISTORY[20:]

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


# --- Plinko (8/10/12 rows by risk, drop position, edge-weighted payouts) ---
PLINKO_ROWS_BY_RISK = {"low": 8, "medium": 10, "high": 12}
PLINKO_TABLES = {
    8: [Decimal("4.41"), Decimal("2.94"), Decimal("1.69"), Decimal("0.73"), Decimal("0.20"),
        Decimal("0.73"), Decimal("1.69"), Decimal("2.94"), Decimal("4.41")],
    10: [Decimal("5.18"), Decimal("3.76"), Decimal("2.51"), Decimal("1.46"), Decimal("0.65"),
         Decimal("0.20"), Decimal("0.65"), Decimal("1.46"), Decimal("2.51"), Decimal("3.76"),
         Decimal("5.18")],
    12: [Decimal("5.90"), Decimal("4.54"), Decimal("3.30"), Decimal("2.22"), Decimal("1.30"),
         Decimal("0.59"), Decimal("0.20"), Decimal("0.59"), Decimal("1.30"), Decimal("2.22"),
         Decimal("3.30"), Decimal("4.54"), Decimal("5.90")],
}


def plinko_bucket(seed: str, nonce: int, position: int, rows: int) -> int:
    """Ball starts at column `position` (0..rows) and walks left/right once per
    row. Final bucket = clamp(position + 2*rights - rows, 0, rows)."""
    rights = sum(1 for i in range(rows) if p_outcome(seed, nonce, f"plinko:{i}") >= 0.5)
    return max(0, min(rows, position + 2 * rights - rows))


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

LAST_AUTH_REASON = ""


def _set_auth_reason(reason: str) -> None:
    global LAST_AUTH_REASON
    LAST_AUTH_REASON = reason


def _unsigned_user_hint(data: Dict[str, Any]) -> str:
    """Informational only (unsigned): which account opened the app."""
    try:
        u = json.loads(data.get("user") or "{}")
        uid = u.get("id")
        if uid:
            name = u.get("username") or u.get("first_name") or ""
            return f"opened as user {uid}" + (f" (@{name})" if name else "")
    except Exception:
        pass
    return 


def validate_init_data(init_data: str) -> Optional[Dict[str, Any]]:
    """Returns the parsed Telegram WebApp user payload, or None if invalid.
    LAST_AUTH_REASON is updated with a human-readable cause on failure."""
    global LAST_AUTH_REASON
    LAST_AUTH_REASON = ""
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
        _set_auth_reason(
            "No login data - this page was opened outside Telegram. "
            "Open the casino from your bot's menu button inside Telegram."
        )
        return None
    pairs = parse_qsl(init_data, keep_blank_values=True)
    data = dict(pairs)
    received_hash = data.pop("hash", "")
    if not received_hash:
        _set_auth_reason("Login data has no signature.")
        return None
    # Telegram requires the data-check-string fields sorted alphabetically
    # by key. Using the raw query order breaks HMAC verification (which is
    # why real Mini App logins were rejected -> balance stayed 0).
    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(pairs, key=lambda p: p[0]) if k != "hash"
    )
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode("utf-8"), hashlib.sha256).digest()
    calc = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, received_hash):
        hint = _unsigned_user_hint(data)
        _set_auth_reason(
            "Signature mismatch"
            + (f" - {hint}" if hint else "")
            + ". The bot that opened the app does not match the server token. "
            "Fix: set TELEGRAM_BOT_TOKEN on the server to the SAME bot's token."
        )
        return None
    try:
        auth_date = int(data.get("auth_date", "0"))
        if auth_date and time.time() - auth_date > 86400:
            _set_auth_reason("Login data expired.")
            return None
        user = json.loads(data.get("user", "{}"))
    except Exception:
        _set_auth_reason("Malformed login data.")
        return None
    if "id" not in user:
        _set_auth_reason("Login data contains no user.")
        return None
    return {"user": user, "demo": False}


def _token_hint() -> str:
    tok = BOT_TOKEN or ""
    if not tok:
        return "<empty>"
    if len(tok) <= 12:
        return tok[:4] + "..."
    return tok[:6] + "..." + tok[-4:]


def user_from_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    u = payload["user"]
    uid = int(u["id"])
    username = str(u.get("username") or "")
    first_name = str(u.get("first_name") or "Player")
    last_name = str(u.get("last_name") or "")
    photo_url = str(u.get("photo_url") or "")
    is_premium = bool(u.get("is_premium"))
    return {
        "id": uid, "username": username, "name": first_name, "last_name": last_name,
        "photo_url": photo_url, "is_premium": is_premium,
        "demo": payload.get("demo", False),
    }


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


def _apply_client_seed(server_seed: str, data: Dict[str, Any]) -> Tuple[str, str]:
    """Combines the server seed with the player's optional client seed. The
    player's seed is disclosed in the fair block so anyone can verify that
    the result could not have been rigged."""
    cs = str(data.get("client_seed") or "")[:64] if isinstance(data, dict) else ""
    if cs:
        return server_seed + "|" + cs, cs
    return server_seed, ""


def fair_block(seed: str, nonce: int, client_seed: str = "") -> Dict[str, str]:
    return {
        "seed_hash": hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24],
        "nonce": str(nonce),
        "client_seed_hash": hashlib.sha256(client_seed.encode("utf-8")).hexdigest()[:12] if client_seed else "",
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
            seed, cs = _apply_client_seed(seed, data)
            cp = crash_point(seed, nonce)
            crash_history_push(cp)
            mini_debit(uid, bet, "crash")
            state = {"bet": float(bet), "crash_point": float(cp), "cashed": False, "started": time.time()}
            sid = mini_session_insert(uid, "crash", bet, seed, nonce, state)
            MINI_SESSIONS[sid] = state
            return {"ok": True, "session_id": sid, "crash_point": float(cp),
                    "bet": float(bet), "fair": fair_block(seed, nonce, cs)}
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
            if not 1 <= mines <= 10:
                raise MiniGameError("Mines must be between 1 and 10.")
            seed, nonce = new_seed(), 0
            seed, cs = _apply_client_seed(seed, data)
            bombs = sorted(shuffled(seed, nonce, list(range(25)))[:mines])
            mini_debit(uid, bet, "mines")
            state = {"mines_count": mines, "bombs": bombs, "revealed": [], "bet": float(bet)}
            sid = mini_session_insert(uid, "mines", bet, seed, nonce, state)
            MINI_SESSIONS[sid] = state
            return {"ok": True, "session_id": sid, "grid": [{"i": i, "revealed": False} for i in range(25)],
                    "fair": fair_block(seed, nonce, cs)}
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
        # Standard rules: 6-deck shoe, dealer stands on soft 17, double on
        # hard 9-11, split pairs up to 3 hands, insurance vs dealer ace.
        if action == "new":
            bet = _parse_bet(data)
            seed, nonce = new_seed(), 0
            seed, cs = _apply_client_seed(seed, data)
            shoe = shuffled(seed, nonce, (list(range(2, 15)) * 4) * BJ_DECKS)
            player = [shoe.pop(0), shoe.pop(0)]
            dealer = [shoe.pop(0), shoe.pop(0)]
            mini_debit(uid, bet, "blackjack")
            state = {
                "shoe": shoe,
                "hands": [{"cards": player, "bet": float(bet), "doubled": False,
                           "split": False, "stood": False, "payout": 0.0}],
                "current": 0,
                "dealer": dealer,
                "base_bet": float(bet),
                "insurance_offered": dealer[0] == 14,
                "insurance_taken": False,
                "insurance_decided": not (dealer[0] == 14),
                "split_count": 0,
            }
            sid = mini_session_insert(uid, "blackjack", bet, seed, nonce, state)
            MINI_SESSIONS[sid] = state
            pv, _ = bj_value(player)
            if pv == 21 and not state["insurance_offered"]:
                return _bj_settle(sid, uid)
            return {"ok": True, "session_id": sid,
                    "hands": [{"cards": [card_label(c) for c in player], "value": pv,
                               "bet": float(bet), "active": True}],
                    "dealer": [card_label(dealer[0]), "?"],
                    "insurance_offered": state["insurance_offered"],
                    "fair": fair_block(seed, nonce, cs)}
        if action in ("hit", "stand", "double", "split", "insure", "decline", "surrender"):
            try:
                sid = int(data.get("session_id"))
            except Exception:
                raise MiniGameError("Missing session.")
            sess = mini_session(sid)
            if sess is None or int(sess["user_id"]) != uid or str(sess["status"]) != "active":
                raise MiniGameError("Session not active.", "session_gone")
            state = json.loads(sess["state"])
            seed, nonce = sess["seed"], int(sess["nonce"])
            shoe = state["shoe"]
            hands = state["hands"]

            def current_hand():
                return hands[state["current"]]

            if action == "insure":
                if not state["insurance_offered"] or state["insurance_decided"]:
                    raise MiniGameError("Insurance is not offered.")
                if state["insurance_taken"]:
                    raise MiniGameError("Insurance already decided.")
                side = quantize_money(Decimal(str(state["base_bet"])) / 2)
                mini_debit(uid, side, "blackjack")
                state["insurance_taken"] = True
                state["insurance_decided"] = True
                mini_session_update(sid, state=state)
                return _bj_settle(sid, uid)

            if action == "decline":
                if state["insurance_decided"]:
                    raise MiniGameError("Insurance already decided.")
                state["insurance_decided"] = True
                mini_session_update(sid, state=state)
                pv, _ = bj_value(current_hand()["cards"])
                if pv == 21:
                    return _bj_settle(sid, uid)
                return {"ok": True, "session_id": sid, "insurance_resolved": True,
                        "hands": _bj_hands_view(hands, state["current"]),
                        "dealer": [card_label(state["dealer"][0]), "?"],
                        "fair": fair_block(seed, nonce)}

            if not state["insurance_decided"]:
                raise MiniGameError("Decide on insurance first.")

            if action == "surrender":
                if state["insurance_decided"] is False:
                    raise MiniGameError("Decide on insurance first.")
                h = current_hand()
                if len(hands) != 1 or len(h["cards"]) != 2 or h["doubled"] or h["split"]:
                    raise MiniGameError("Surrender is allowed only on your first two cards of a single hand.")
                half = quantize_money(Decimal(str(h["bet"])) / 2)
                h["surrender_payout"] = float(half)
                h["stood"] = True
                mini_session_update(sid, state=state)
                return _bj_settle(sid, uid)

            if action == "hit":
                h = current_hand()
                if h["stood"] or h["doubled"]:
                    raise MiniGameError("This hand cannot hit.")
                h["cards"].append(shoe.pop(0))
                state["shoe"] = shoe
                pv, _ = bj_value(h["cards"])
                if pv > 21 or (pv == 21):
                    h["stood"] = True
                    mini_session_update(sid, state=state)
                    if state["current"] < len(hands) - 1:
                        state["current"] += 1
                        mini_session_update(sid, state=state)
                        return _bj_action_view(sid, state, seed, nonce)
                    return _bj_settle(sid, uid)
                mini_session_update(sid, state=state)
                return _bj_action_view(sid, state, seed, nonce)

            if action == "stand":
                h = current_hand()
                h["stood"] = True
                state["shoe"] = shoe
                mini_session_update(sid, state=state)
                if state["current"] < len(hands) - 1:
                    state["current"] += 1
                    mini_session_update(sid, state=state)
                    return _bj_action_view(sid, state, seed, nonce)
                return _bj_settle(sid, uid)

            if action == "double":
                h = current_hand()
                pv, _ = bj_value(h["cards"])
                if len(h["cards"]) != 2 or h["doubled"] or h["split"]:
                    raise MiniGameError("Double down is allowed only on your first two cards.")
                if pv < 9 or pv > 11:
                    raise MiniGameError("Double down is allowed only on hard 9, 10 or 11.")
                mini_debit(uid, Decimal(str(h["bet"])), "blackjack")
                h["bet"] = float(quantize_money(Decimal(str(h["bet"])) * 2))
                h["doubled"] = True
                h["cards"].append(shoe.pop(0))
                h["stood"] = True
                state["shoe"] = shoe
                mini_session_update(sid, state=state)
                if state["current"] < len(hands) - 1:
                    state["current"] += 1
                    mini_session_update(sid, state=state)
                    return _bj_action_view(sid, state, seed, nonce)
                return _bj_settle(sid, uid)

            if action == "split":
                h = current_hand()
                if state["split_count"] >= 3:
                    raise MiniGameError("Maximum of 3 splits.")
                if len(h["cards"]) != 2 or h["cards"][0] != h["cards"][1]:
                    raise MiniGameError("Split is allowed only on a pair.")
                mini_debit(uid, Decimal(str(h["bet"])), "blackjack")
                state["split_count"] += 1
                c1, c2 = h["cards"][0], h["cards"][1]
                hands[state["current"]] = {"cards": [c1, shoe.pop(0)], "bet": h["bet"],
                                           "doubled": False, "split": True,
                                           "stood": False, "payout": 0.0}
                hands.insert(state["current"] + 1,
                             {"cards": [c2, shoe.pop(0)], "bet": h["bet"],
                              "doubled": False, "split": True,
                              "stood": False, "payout": 0.0})
                state["shoe"] = shoe
                mini_session_update(sid, state=state)
                return _bj_action_view(sid, state, seed, nonce)
            raise MiniGameError("Unknown action.")
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
        if risk not in PLINKO_ROWS_BY_RISK:
            raise MiniGameError("Risk must be low, medium or high.")
        rows = int(PLINKO_ROWS_BY_RISK[risk])
        try:
            position = int(data.get("position", rows // 2))
        except (TypeError, ValueError):
            position = rows // 2
        if not 0 <= position <= rows:
            raise MiniGameError(f"Drop position must be between 0 and {rows}.")
        seed, nonce = new_seed(), 0
        seed, cs = _apply_client_seed(seed, data)
        bucket = plinko_bucket(seed, nonce, position, rows)
        mult = PLINKO_TABLES[rows][bucket]
        payout = quantize_money(bet * mult) if mult > 0 else Decimal("0")
        mini_debit(uid, bet, "plinko")
        if payout > 0:
            mini_credit(uid, payout, "plinko")
        result = {"bucket": bucket, "risk": risk, "rows": rows, "position": position,
                  "multiplier": float(mult), "won": payout > 0,
                  "payout": float(payout), "bet": float(bet)}
        mini_history_insert(uid, "plinko", bet, payout, "won" if payout > 0 else "lost", seed, nonce, result)
        return {**result, "fair": fair_block(seed, nonce, cs)}

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


BJ_DECKS = 6


def _bj_hands_view(hands: List[Dict[str, Any]], current: int) -> List[Dict[str, Any]]:
    view = []
    for i, h in enumerate(hands):
        v, _ = bj_value(h["cards"])
        view.append({"cards": [card_label(c) for c in h["cards"]], "value": v,
                     "bet": float(h["bet"]), "active": i == current,
                     "stood": bool(h["stood"]), "doubled": bool(h["doubled"])})
    return view


def _bj_action_view(sid: int, state: Dict[str, Any], seed: str, nonce: int) -> Dict[str, Any]:
    h = state["hands"][state["current"]]
    pv, _ = bj_value(h["cards"])
    return {"ok": True, "session_id": sid,
            "hands": _bj_hands_view(state["hands"], state["current"]),
            "dealer": [card_label(state["dealer"][0]), "?"],
            "current_value": pv,
            "can_double": len(h["cards"]) == 2 and not h["doubled"] and not h["split"] and 9 <= pv <= 11,
            "can_surrender": len(state["hands"]) == 1 and len(h["cards"]) == 2 and not h["doubled"] and not h["split"],
            "can_split": (len(h["cards"]) == 2 and h["cards"][0] == h["cards"][1]
                          and state["split_count"] < 3),
            "fair": fair_block(seed, nonce)}


def _bj_settle(sid: int, uid: int) -> Dict[str, Any]:
    sess = mini_session(sid)
    if sess is None or int(sess["user_id"]) != uid or str(sess["status"]) != "active":
        raise MiniGameError("Session not active.", "session_gone")
    state = json.loads(sess["state"])
    seed, nonce = sess["seed"], int(sess["nonce"])
    shoe = state["shoe"]
    dealer = state["dealer"]

    # Dealer plays: stands on all 17s (soft 17 included) - S17 rule.
    dv, dsoft = bj_value(dealer)
    while dv < 17 and shoe:
        dealer.append(shoe.pop(0))
        dv, dsoft = bj_value(dealer)
    dealer_blackjack = len(dealer) == 2 and dv == 21
    state["dealer"] = dealer
    state["shoe"] = shoe

    total_bet = Decimal("0")
    total_payout = Decimal("0")
    hands_out = []
    any_win = False
    for h in state["hands"]:
        bet = Decimal(str(h["bet"]))
        total_bet += bet
        cards = h["cards"]
        pv, _ = bj_value(cards)
        is_natural = (not h["split"]) and len(cards) == 2 and pv == 21
        if h.get("surrender_payout") is not None:
            payout = Decimal(str(h["surrender_payout"]))
            outcome = "surrender"
        elif pv > 21:
            payout = Decimal("0")
            outcome = "lost"
        elif dealer_blackjack:
            payout = bet if is_natural else Decimal("0")
            outcome = "push" if is_natural else "lost"
        elif is_natural and dv < 21:
            payout = quantize_money(bet * Decimal("2.5"))
            outcome = "won"
        elif dv > 21 or pv > dv:
            payout = quantize_money(bet * Decimal("2"))
            outcome = "won"
        elif pv == dv:
            payout = bet
            outcome = "push"
        else:
            payout = Decimal("0")
            outcome = "lost"
        h["payout"] = float(payout)
        h["outcome"] = outcome
        total_payout += payout
        if payout > 0:
            any_win = True
        hands_out.append({"cards": [card_label(c) for c in cards], "value": pv,
                          "bet": float(bet), "payout": float(payout), "outcome": outcome,
                          "natural": is_natural})

    # Insurance: pays 2:1 on the side bet when the dealer has blackjack.
    ins_payout = Decimal("0")
    if state.get("insurance_taken") and dealer_blackjack:
        ins_payout = quantize_money(Decimal(str(state["base_bet"])))
        total_payout += ins_payout
        any_win = True

    status = "won" if total_payout > 0 else "lost"
    mini_session_update(sid, status=status, state=state)
    if total_payout > 0:
        mini_credit(uid, total_payout, "blackjack")

    result = {"hands": hands_out,
              "dealer_cards": [card_label(c) for c in dealer],
              "dealer_value": dv,
              "dealer_blackjack": dealer_blackjack,
              "insurance_payout": float(ins_payout),
              "total_bet": float(total_bet),
              "payout": float(total_payout),
              "bet": float(total_bet),
              "won": any_win,
              "push": not any_win and any(o == "push" for o in [h["outcome"] for h in hands_out]) if hands_out else False,
              "fair_round": True}
    mini_history_insert(uid, "blackjack", total_bet, total_payout,
                        "won" if total_payout > 0 else "lost", seed, nonce, result)
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

# The four flagship table games of Casino Royals. Every result is derived
# from a server-side SHA-256 seeded random value - provably fair, verifiable,
# and impossible to influence from the client.
GAME_META = [
    {"id": "crash", "name": "Crash", "mono": "C", "tag": "Live"},
    {"id": "mines", "name": "Mines", "mono": "M", "tag": "Skill"},
    {"id": "blackjack", "name": "Blackjack", "mono": "BJ", "tag": "Cards"},
    {"id": "plinko", "name": "Plinko", "mono": "P", "tag": "Instant"},
]

_bot_username: Optional[str] = None

# The token that leaked when the original bot file was shared. If the server
# still runs it, players' Mini App logins can be spoofed - warn the operator.
_KNOWN_LEAKED_TOKENS = {
    "8307026945:AAGEwptqpHWeyekQ9a3lMZwLx5Xdhc9tYEM",
}


def _token_warning() -> bool:
    return bool(BOT_TOKEN) and BOT_TOKEN in _KNOWN_LEAKED_TOKENS


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
        "tokenHint": _token_hint(),
        "crashHistory": list(CRASH_HISTORY),
        "tokenWarning": _token_warning(),
        "adminIds": sorted(int(a) for a in getattr(CB, "ADMIN_IDS", set())),
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
            # solo (mini app) table stats
            row = conn.execute(
                "SELECT COUNT(*) AS games, COALESCE(SUM(bet),0) AS wagered, COALESCE(SUM(payout),0) AS paid, "
                "SUM(CASE WHEN status='won' THEN 1 ELSE 0 END) AS wins, "
                "SUM(CASE WHEN status='lost' THEN 1 ELSE 0 END) AS losses "
                "FROM solo_history WHERE user_id = ?",
                (uid,),
            ).fetchone()
            solo = dict(row)
            # bot-wide stats from the users table (PVP games counted by the bot)
            urow = conn.execute(
                "SELECT wins, losses, games FROM users WHERE user_id = ?", (uid,)
            ).fetchone()
            bot_games = int(urow["games"] or 0) if urow else 0
            bot_wins = int(urow["wins"] or 0) if urow else 0
            bot_losses = int(urow["losses"] or 0) if urow else 0
            hist = conn.execute(
                "SELECT game, bet, payout, status, created_at FROM solo_history WHERE user_id = ? "
                "ORDER BY id DESC LIMIT 20",
                (uid,),
            ).fetchall()
            return {
                "stats": {
                    "games": (int(solo["games"] or 0) + bot_games),
                    "wins": (int(solo["wins"] or 0) + bot_wins),
                    "losses": (int(solo["losses"] or 0) + bot_losses),
                    "wagered": solo["wagered"],
                    "paid": solo["paid"],
                    "solo_games": int(solo["games"] or 0),
                    "bot_games": bot_games,
                },
                "history": [dict(h) for h in hist],
            }
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


def _user_profile_stats(uid: int) -> Dict[str, Any]:
    conn = CB._solo_conn()
    try:
        CB._solo_ensure_tables(conn)
        # per-game breakdown
        per_game = {}
        for r in conn.execute(
            "SELECT game, COUNT(*) AS games, "
            "SUM(CASE WHEN status='won' THEN 1 ELSE 0 END) AS wins, "
            "SUM(CASE WHEN status='lost' THEN 1 ELSE 0 END) AS losses, "
            "COALESCE(SUM(bet),0) AS wagered, COALESCE(SUM(payout),0) AS paid, "
            "MAX(payout) AS biggest "
            "FROM solo_history WHERE user_id = ? GROUP BY game", (uid,)
        ).fetchall():
            per_game[str(r["game"])] = dict(r)
        # win/loss streak (most recent first)
        rows = conn.execute(
            "SELECT status FROM solo_history WHERE user_id = ? AND status IN ('won','lost') "
            "ORDER BY id DESC LIMIT 60", (uid,)
        ).fetchall()
        streak = 0
        if rows:
            first = rows[0]["status"]
            for r in rows:
                if r["status"] == first:
                    streak += 1
                else:
                    break
            streak = streak if first == "won" else -streak
        # daily wagers, last 7 days
        days = []
        for i in range(6, -1, -1):
            d = datetime.now(timezone.utc) - timedelta(days=i)
            key = d.strftime("%Y-%m-%d")
            row = conn.execute(
                "SELECT COALESCE(SUM(bet),0) AS wagered, COALESCE(SUM(payout),0) AS paid "
                "FROM solo_history WHERE user_id = ? AND substr(created_at,1,10) = ?",
                (uid, key),
            ).fetchone()
            days.append({"date": key, "wagered": float(row["wagered"] or 0),
                         "paid": float(row["paid"] or 0)})
        join_row = conn.execute("SELECT join_date FROM users WHERE user_id = ?", (uid,)).fetchone()
        return {"per_game": per_game, "streak": int(streak),
                "daily": days, "join_date": str(join_row["join_date"] or "") if join_row else ""}
    finally:
        conn.close()


def _leaders_period(period: str, metric: str, limit: int = 25) -> List[Dict[str, Any]]:
    conn = CB._solo_conn()
    try:
        CB._solo_ensure_tables(conn)
        period = period if period in ("daily", "weekly", "monthly") else "all"
        metric = metric if metric in ("profit", "games", "multiplier") else "profit"
        since = ""
        if period == "daily":
            since = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        elif period == "weekly":
            since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
        elif period == "monthly":
            since = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
        where = f"WHERE user_id != {int(CB.SOLO_HOUSE_ID)}"
        if since:
            where += f" AND created_at >= '{since}'"
        rows = conn.execute(
            f"SELECT user_id, COUNT(*) AS games, COALESCE(SUM(bet),0) AS wagered, "
            f"COALESCE(SUM(payout),0) AS paid FROM solo_history {where} GROUP BY user_id"
        ).fetchall()
        leaders = []
        for r in rows:
            d = dict(r)
            d["profit"] = float(d["paid"] or 0) - float(d["wagered"] or 0)
            if metric == "multiplier":
                mx = conn.execute(
                    f"SELECT result FROM solo_history WHERE user_id = ? "
                    f"{('AND created_at >= ?' if since else '')} ORDER BY id DESC LIMIT 200",
                    (r["user_id"],) + ((since,) if since else ()),
                ).fetchall()
                best = 0.0
                for mrow in mx:
                    try:
                        res = json.loads(mrow["result"] or "{}")
                        mult = float(res.get("multiplier") or 0)
                        if mult > best:
                            best = mult
                    except Exception:
                        pass
                d["multiplier"] = best
            leaders.append(d)
        key = {"profit": "profit", "games": "games", "multiplier": "multiplier"}[metric]
        leaders.sort(key=lambda x: x.get(key, 0), reverse=True)
        out = []
        for i, d in enumerate(leaders[:limit]):
            urow = conn.execute(
                "SELECT first_name, username, wins, losses, games, balance FROM users WHERE user_id = ?",
                (d["user_id"],),
            ).fetchone()
            u = dict(urow) if urow else {}
            out.append({
                "rank": i + 1, "user_id": d["user_id"],
                "first_name": u.get("first_name") or "Player",
                "username": u.get("username") or "",
                "balance": float(u.get("balance") or 0),
                "games": int(d.get("games") or 0),
                "profit": round(d.get("profit", 0.0), 2),
                "multiplier": round(d.get("multiplier", 0.0), 2),
                "metric": metric, "period": period,
            })
        return out
    finally:
        conn.close()


def _admin_overview() -> Dict[str, Any]:
    conn = CB._solo_conn()
    try:
        CB._solo_ensure_tables(conn)
        users = conn.execute(
            f"SELECT COUNT(*) AS n, COALESCE(SUM(balance),0) AS bal FROM users WHERE user_id != {int(CB.SOLO_HOUSE_ID)}"
        ).fetchone()
        agg = conn.execute(
            "SELECT COUNT(*) AS games, COALESCE(SUM(bet),0) AS wagered, COALESCE(SUM(payout),0) AS paid FROM solo_history"
        ).fetchone()
        recent = conn.execute(
            "SELECT id, user_id, game, bet, payout, status, created_at FROM solo_history "
            "ORDER BY id DESC LIMIT 20"
        ).fetchall()
        per_game = {}
        for r in conn.execute(
            "SELECT game, COUNT(*) AS games, COALESCE(SUM(bet),0) AS wagered, COALESCE(SUM(payout),0) AS paid "
            "FROM solo_history GROUP BY game"
        ).fetchall():
            per_game[str(r["game"])] = dict(r)
        return {
            "users": int(users["n"] or 0),
            "total_balance": float(users["bal"] or 0),
            "games": int(agg["games"] or 0),
            "wagered": float(agg["wagered"] or 0),
            "paid": float(agg["paid"] or 0),
            "house_edge": round(float((agg["wagered"] or 0) - (agg["paid"] or 0)), 2),
            "per_game": per_game,
            "recent": [dict(r) for r in recent],
        }
    finally:
        conn.close()


def _leaders() -> List[Dict[str, Any]]:
    conn = CB._solo_conn()
    try:
        rows = conn.execute(
            "SELECT user_id, first_name, username, balance, wins, losses, games FROM users "
            "WHERE user_id != ? AND balance > 0 ORDER BY balance DESC LIMIT 25",
            (CB.SOLO_HOUSE_ID,),
        ).fetchall()
        leaders = []
        for i, r in enumerate(rows):
            d = dict(r)
            d["rank"] = i + 1
            leaders.append(d)
        return leaders
    finally:
        conn.close()


@app.post("/api/init")
async def api_init(request: Request) -> JSONResponse:
    body = await request.json()
    payload = validate_init_data(str(body.get("initData") or ""))
    if payload is None:
        return JSONResponse(
            {"ok": False, "error": LAST_AUTH_REASON or "Invalid Telegram data.",
             "reason": LAST_AUTH_REASON},
            status_code=401,
        )
    user = user_from_payload(payload)
    await db_call(CB.DB.ensure_user, user["id"], user["username"], user["name"])
    overview = await db_call(_user_overview, user["id"])
    profile = await db_call(_user_profile_stats, user["id"])
    leaders = await db_call(_leaders)
    return JSONResponse({
        "ok": True, "user": user, **overview,
        "profile": profile,
        "isAdmin": int(user["id"]) in set(getattr(CB, "ADMIN_IDS", set())),
        "leaderboard": leaders,
    })


@app.post("/api/balance")
async def api_balance(request: Request) -> JSONResponse:
    """Lightweight balance refresh (for the header + after deposits)."""
    body = await request.json()
    payload = validate_init_data(str(body.get("initData") or ""))
    if payload is None:
        return JSONResponse(
            {"ok": False, "error": LAST_AUTH_REASON or "Invalid Telegram data.",
             "reason": LAST_AUTH_REASON},
            status_code=401,
        )
    user = user_from_payload(payload)
    await db_call(CB.DB.ensure_user, user["id"], user["username"], user["name"])
    overview = await db_call(_user_overview, user["id"])
    return JSONResponse(
        {
            "ok": True,
            "user": user,
            "balance": overview["balance"],
            "held": overview["held"],
            "available": overview["available"],
            "stats": overview["stats"],
        }
    )


@app.post("/api/leaderboard")
async def api_leaderboard(request: Request) -> JSONResponse:
    body = await request.json()
    payload = validate_init_data(str(body.get("initData") or ""))
    if payload is None:
        return JSONResponse(
            {"ok": False, "error": LAST_AUTH_REASON or "Invalid Telegram data.",
             "reason": LAST_AUTH_REASON},
            status_code=401,
        )
    period = str(body.get("period") or "all").lower()
    metric = str(body.get("metric") or "profit").lower()
    leaders = await db_call(_leaders_period, period, metric)
    return JSONResponse({"ok": True, "leaderboard": leaders, "period": period, "metric": metric})


@app.post("/api/admin")
async def api_admin(request: Request) -> JSONResponse:
    body = await request.json()
    payload = validate_init_data(str(body.get("initData") or ""))
    if payload is None:
        return JSONResponse(
            {"ok": False, "error": LAST_AUTH_REASON or "Invalid Telegram data.",
             "reason": LAST_AUTH_REASON},
            status_code=401,
        )
    user = user_from_payload(payload)
    if int(user["id"]) not in set(getattr(CB, "ADMIN_IDS", set())):
        return JSONResponse({"ok": False, "error": "Admins only."}, status_code=403)
    overview = await db_call(_admin_overview)
    return JSONResponse({"ok": True, **overview})


@app.get("/api/feed")
async def api_feed() -> JSONResponse:
    """Live betting feed + latest crash history (polled by the UI)."""
    return JSONResponse({"ok": True, "feed": list(LIVE_FEED), "crashHistory": list(CRASH_HISTORY)})


@app.get("/api/auth-debug")
async def api_auth_debug() -> JSONResponse:
    """Diagnostics: which bot this server is bound to and the token prefix.
    Compare the token prefix with the bot token of the bot you open the
    Mini App from - they must be the same bot."""
    return JSONResponse({
        "ok": True,
        "demoMode": DEMO_MODE,
        "botUsername": _bot_username,
        "tokenHint": _token_hint(),
    })


_rate_buckets: Dict[int, List[float]] = {}


def _rate_limited(uid: int) -> bool:
    now = time.time()
    bucket = _rate_buckets.setdefault(uid, [])
    bucket[:] = [t for t in bucket if now - t < 60]
    if len(bucket) >= 50:
        return True
    bucket.append(now)
    return False


@app.post("/api/play")
async def api_play(request: Request) -> JSONResponse:
    body = await request.json()
    payload = validate_init_data(str(body.get("initData") or ""))
    if payload is None:
        return JSONResponse(
            {"ok": False, "error": LAST_AUTH_REASON or "Invalid Telegram data.",
             "reason": LAST_AUTH_REASON},
            status_code=401,
        )
    user = user_from_payload(payload)
    await db_call(CB.DB.ensure_user, user["id"], user["username"], user["name"])
    if _rate_limited(int(user["id"])):
        return JSONResponse(
            {"ok": False, "error": "Too many requests - slow down a little.", "code": "rate_limited"},
            status_code=429,
        )
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
        try:
            if action in ("play", "new") and isinstance(result, dict) and result.get("bet"):
                feed_push(game, user["name"], result["bet"], result.get("multiplier") or 0)
        except Exception:
            pass
        return {"ok": True, "result": result, "balance": overview["balance"],
                "available": overview["available"]}

    out = await db_call(_run)
    status = 200 if out.get("ok") else 400
    return JSONResponse(out, status_code=status)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
