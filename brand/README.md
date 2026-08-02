# Pulse Brand Assets

> **Heartbeat for your repo** — Agentic PR Triage & Review

This directory holds the official brand assets for Pulse: logos, app icon, social card, and color tokens. The brand is built on three ideas: **watchfulness** (the pulse waveform), **vitality** (the cyan→gold gradient on the alert peak), and **clarity** (clean slate dark mode with no noise).

## Files

| File | Format | Size | Use |
|---|---|---|---|
| `app-icon/pulse-app-icon.png` | PNG | 2048×2048 | macOS/Linux app launcher, iOS app icon (export smaller sizes) |
| `logos/pulse-mark.png` | PNG (transparent) | 2048×2048 | Favicon, GitHub social preview icon, watermark |
| `logos/pulse-logo-horizontal.png` | PNG | 2752×1536 | README header, docs site, presentations |
| `social/pulse-social-card.png` | PNG | 2752×1536 | GitHub OG image, Twitter card, blog hero |
| `palette/pulse-palette.png` | PNG | 1376×768 | Brand reference, design handoff |
| `colors.json` | JSON | — | Machine-readable color tokens for code |

## Color System

| Role | Name | Hex | When to use |
|---|---|---|---|
| **Primary** | Cyan | `#06B6D4` | Brand mark, links, primary actions, focus rings |
| **Base** | Slate | `#1E293B` | Dark mode surfaces, cards, panels |
| **Base deep** | Slate Deep | `#0F172A` | Page background |
| **Alert** | Orange | `#F97316` | High-risk alerts, critical events, the "important" peak |
| **Accent** | Gold | `#F59E0B` | Approved states, success highlights, premium finish |
| **Text primary** | Slate 50 | `#F8FAFC` | Headlines, body text on dark |
| **Text secondary** | Slate 400 | `#94A3B8` | Subtitle, metadata |

The cyan + orange/gold gradient on the heartbeat peak is the signature visual — the line is the "watching," the orange/gold peak is the "signal worth your attention."

## Typography

- **Wordmark "Pulse"** — Geist / Inter / system-ui sans-serif. Bold weight, clean geometry.
- **Tagline "HEARTBEAT FOR YOUR REPO"** — JetBrains Mono / ui-monospace, tracked uppercase, light slate.

## Voice

- Calm, technical, opinionated.
- The agent that watches so you don't have to.
- Never alarmist, never salesy.

## Tagline

> **Heartbeat for your repo**

Use it. It's the line. Variants ("Triage the signal from the noise", etc.) are fine for body copy but the headline is the heartbeat one.

## Usage rules

- The brand mark **must** appear on a dark background. Don't place it on white — the glow dies.
- Never recolor the cyan line. The orange→gold peak is the focal point.
- Don't stretch, rotate, or skew the logo.
- Don't add drop shadows. The pulse already glows.
- For light-mode contexts, invert to white-on-slate (we don't have an official light variant yet — request one before shipping).

## TODO (future brand work)

- [ ] Light-mode variants of all assets
- [ ] Monochrome (single-color) variants for tight contexts
- [ ] Animated logo (the pulse line drawn in over 1.5s, looping)
- [ ] Favicon set (16/32/64/180/192/512)
- [ ] Sticker / pack assets for merch / swag
