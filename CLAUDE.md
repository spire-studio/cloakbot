# CloakBot — Privacy-Preserving AI Assistant

## Project Overview

This project is a fork of [cloakbot](https://github.com/HKUDS/cloakbot) (MIT license), 
renamed CloakBot, extended with a privacy-preserving sanitization layer powered by 
a local Gemma 4 model via Ollama.

## Core Architecture
User Input
  → [Local Gemma 4 via Ollama] — PII detection, prompt injection filter, sensitive data scrubbing
  → [Remote LLM API] — Claude or GPT for final response
  → [Optional: Gemma 4 output filter] — scrub any sensitive data in the response

## What I'm Adding (My Core Contribution)
- `cloakbot/sanitizer/` — new module for the sanitization pipeline
  - `pii_detector.py` — detect and redact personally identifiable information
  - `injection_filter.py` — detect prompt injection attacks
  - `sanitize.py` — main entry point, calls local Gemma 4 via Ollama
- `cloakbot/providers/ollama.py` — new local provider for Gemma 4 via Ollama
- Modified `cloakbot/agent/loop.py` — insert sanitization step before remote LLM call

## What I'm NOT Changing (cloakbot original code)
- Channel integrations (Telegram, WhatsApp)
- Session management
- Cron / scheduled tasks
- CLI commands
- Memory system

## Tech Stack
- Local model: Gemma 4 E4B via Ollama (runs on laptop)
- Remote LLM: Claude API (via OpenRouter) or GPT
- Language: Python 3.11+
- Framework: built on cloakbot

## Hackathon Context
Submitted to: Gemma 4 Good Hackathon (Kaggle, deadline May 18 2026)
Target tracks: Main Track + Ollama Special Track ($10,000)

## Development Guidelines
- Always run sanitization locally first — never skip this step
- Keep the sanitizer module independent from cloakbot core (easy to test in isolation)
- When modifying loop.py, add sanitization as a middleware step, not hardcoded logic
- Write tests for the sanitizer module in `tests/test_sanitizer.py`
- Document what types of PII and injection patterns are detected

## How to Run Locally
1. Install Ollama: https://ollama.com
2. Pull Gemma 4: `ollama pull gemma4:e4b`
3. Install dependencies: `pip install -e .`
4. Set API key in `~/.cloakbot/config.json`
5. Run: `cloakbot agent -m "Hello"`
