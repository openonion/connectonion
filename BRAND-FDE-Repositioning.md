# ConnectOnion × Forward Deployed Engineers — Brand Repositioning

**Status:** Draft for review — *documentation only, no implementation yet.*
**Date:** 2026-06-30
**Author:** Strategy draft for Aaron
**Decision requested:** Approve the direction (Section 2 + 3) and the open questions (Section 10) before any copy or code changes.

---

## 0. TL;DR

We reposition ConnectOnion from a generic "simple AI agent framework" to **the agent framework Forward Deployed Engineers ship with** — and we anchor it on one insight the market handed us:

> The #1 documented failure mode of FDE work is drowning in throwaway, per-client bespoke code (a16z calls FDE "the hottest job in startups," but every playbook warns it collapses into a consulting shop). **ConnectOnion's skill system is the cure.** You build a bespoke agent for a client in an afternoon — and keep it as a reusable, portable, even publishable *skill* instead of throwaway code.

So the brand line is not just "simple framework for FDEs." It is:

**Build the bespoke thing fast. Keep it as a skill. Reuse it at the next client.**
*Build → Ship → Reuse.*

This is a **wedge and an audience**, not a replacement for our soul. Simplicity stays the promise ("keep simple things simple, make complicated things possible"). FDE is the *who*. "2 lines of Python" stays the proof. Skills + the CLI become the *how*.

---

## 1. Why this, why now (the strategic bet)

### 1.1 The category trap we're escaping
"AI agent framework" is an unwinnable head-on fight: LangChain, CrewAI, AutoGen, LlamaIndex, OpenAI Agents SDK, and a dozen more own that search term and that mindshare. We cannot out-SEO or out-fund "the best agent framework." Broad positioning is where small frameworks go to die.

A wedge wins by being **narrow, ownable, and high-intent.** "The framework FDEs ship with" has near-zero competition and is a phrase the exact right person will recognize instantly.

### 1.2 FDE is the hottest wedge in AI right now
From current (2025–2026) market research:
- a16z called the Forward Deployed Engineer **"the hottest job in startups,"** with **~800% growth in 2025**.
- Lineage: **Palantir invented it in 2008 → OpenAI & Anthropic rebuilt it for the LLM era in 2023 → by 2026 every Series A AI startup with six-figure ACV hires at least one.**
- Comp signals seriousness: **$200K at seed → $450K–$550K+ at Series C**, frontier-lab staff FDEs clearing $700K. These are high-influence, tool-choosing engineers.
- The job in one line: **"an engineer with customer judgment who lives in the customer's environment for 60–180 days, ships integrations, and converts vague enterprise problems into shippable product."**

That description *is* the ConnectOnion user.

### 1.3 This is not a pivot — it's naming the person who already matches our soul
Our existing tagline — "keep simple things simple, make complicated things possible" — **is the FDE creed**: ship something working today, but be able to go arbitrarily deep when the client's reality gets weird. We're not changing what we are. We're putting a face on it. That's why this repositioning is low-risk: the product doesn't have to change to make the message true.

### 1.4 The killer insight: skills = the FDE's productization engine
Every FDE playbook says the same thing: **the function dies if it becomes a billable-hours consulting shop. The whole game is turning bespoke client work into reusable product.**

That is *exactly* the job ConnectOnion's **skills** do for an individual engineer:
- Build a one-off agent/tool for **Client A**.
- `co`-package it as a **skill** (reusable workflow with auto permission scoping).
- Publish/subscribe via **`oo`** so it's portable across machines, teammates, and clients.
- Start **Client B** from that skill instead of a blank file.

No other agent framework frames itself as **the antidote to the FDE's central career risk.** That is a differentiated, ownable, emotionally resonant promise — not a feature list. We should build the whole brand on it.

---

## 2. Positioning statement (the formal spine)

> **For** Forward Deployed Engineers and small teams building custom AI agents for clients,
> **who** need to ship bespoke solutions fast *and* stop drowning in throwaway per-client code,
> **ConnectOnion is** the simple Python/TypeScript agent framework + skill system
> **that** lets you build an agent in 2 lines, ship it to any client, and keep every solution as a reusable skill,
> **unlike** heavyweight frameworks (LangChain/CrewAI) and disposable per-client scripts,
> **because** it's simple by default and deep when the client gets weird — and skills make every bespoke win portable.

---

## 3. Messaging hierarchy

Think of the brand as four layers. Only the **audience layer** is new; the rest we already own.

| Layer | Content | Status |
|---|---|---|
| **Brand promise (durable)** | "Keep simple things simple, make complicated things possible." | Keep — never demote |
| **Audience wedge (timely)** | Forward Deployed Engineers | **New** |
| **Magnet headline (proof)** | "Build AI Agents in 2 lines of Python" | Keep — it converts |
| **The loop (the how)** | **Build → Ship → Reuse** (library → CLI/deploy → skills) | **New framing of existing parts** |

### 3.1 Recommended copy stack
- **H1 (unchanged magnet):** Build AI Agents in 2 lines of Python
- **New positioning sub-line:** *The simple framework Forward Deployed Engineers ship with — build a bespoke agent for any client in an afternoon, and keep it as a reusable skill, not throwaway code.*
- **Brand line (footer / everywhere):** Keep simple things simple, make complicated things possible.

> **Deliberate choice:** the literal acronym "FDE" does **not** lead the global homepage H1 (acronym opacity — see 8.1). It is spelled out one line down, and goes *front-and-center* on a dedicated `/fde` page and in FDE-channel content. Lead with the concrete, provable hook; let the persona claim it underneath.

### 3.2 Four supporting pillars (each must carry a proof, not an adjective)
1. **Fast to first value** — 2 lines of Python; `co create` to a running agent in 60s. *(speed an FDE is judged on)*
2. **Deep when it has to be** — drop to raw Python, custom tools, trust levels, approval gates, multi-agent. *(handles the messy client requirement)*
3. **Reusable, not disposable** — turn any client solution into a skill; publish/subscribe across clients. *(the productization promise)*
4. **No lock-in** — just Python/TS, your models, your infra. *(FDEs distrust frameworks that trap them)*

### 3.3 Voice & tone
The FDE audience has a finely tuned bullshit detector. The brand voice must be **builder-to-builder**:
- Show **code**, not adjectives. Every claim near a snippet.
- Terse. Respect the reader's time (mirrors our own engineering values).
- Real client scenarios, not "revolutionize your workflow."
- Never "enterprise-grade," "seamless," "powerful." Ban the SaaS thesaurus.

---

## 4. Brand architecture (resolve the moving parts)

We have three entities and they must each have one clear job in the FDE story:

| Entity | What it is | Job in the story | Surface |
|---|---|---|---|
| **ConnectOnion** | The framework / library (Python + TS) + the `co` CLI | **The engine** — build the agent | docs.connectonion.com |
| **Skills** | `SKILL.md` reusable workflows w/ permission scoping | **The unit of reuse** — keep the bespoke win | docs + `oo` distribution |
| **OpenOnion / `oo`** | Platform: identity, publish/subscribe, managed models (`co/...`) | **The distribution + identity layer** — ship & share | oo.openonion.ai / o.openonion.ai |

### 4.1 What "heavily for skills and CLI" precisely means
It means leaning into the two surfaces FDEs live in:
- **The `co` CLI** — the framework's workflow tool (`co create`, `co ai`, `co copy`, `co status`, deploy). This is where the FDE works.
- **Skills** — the artifact an FDE *produces and carries* from client to client.

It does **not** mean building a second runtime or a parallel CLI wrapper around the library. That keeps us consistent with our standing principle: *"Skill IS the interface, library IS the engine; no parallel CLI on top of connectonion."* The `co` CLI is the framework's native CLI; the `oo` skill bundles are the cross-tool interface. They are not competing CLIs — confirm this is the canonical story (see open decision 10.2).

### 4.2 The one architecture decision this forces
**Is the umbrella brand ConnectOnion or OpenOnion?** Recommendation: keep **ConnectOnion as the developer-facing brand** that carries the FDE positioning (it's the framework FDEs touch daily), and keep **OpenOnion as the platform/company** behind models + distribution. The FDE story is told on ConnectOnion; OpenOnion is the backend that makes Ship/Reuse real. Confirm in 10.1.

---

## 5. The narrative (the story we actually tell)

Every brand surface should be able to tell this 30-second story:

> You're an FDE. Monday you land at a new client. Their problem is vague and their systems are a mess. With ConnectOnion you wrap their internal API as an agent tool in 10 lines and have a working prototype by lunch — **Build.** You add approval gates and deploy it behind their auth that afternoon — **Ship.** Friday you `co`-package the useful half as a skill and publish it to your `oo` identity. Next month, at the next client, you start from that skill instead of a blank file — **Reuse.** You never become the consultant who rewrites the same thing forever. You compound.

**Build → Ship → Reuse** is the spine for the homepage, the docs narrative, the README, and every talk. It maps one-to-one onto library → CLI/deploy → skills.

---

## 6. What changes — surface by surface

> Principle: **positioning cost is almost entirely consistency cost.** Each surface is all-or-nothing. Phased rollout in Section 9.

### 6.1 Homepage (docs.connectonion.com)
**Before**
- H1: "Build AI Agents in 2 lines of Python"
- Sub: "Keep simple things simple, make complicated things possible. No boilerplate. No framework lock-in. Just Python."

**After**
- H1: *Build AI Agents in 2 lines of Python* (unchanged)
- Sub: *The simple framework Forward Deployed Engineers ship with — build a bespoke agent for any client in an afternoon, and keep it as a reusable skill, not throwaway code.*
- New section directly under hero: **"Built for the way FDEs actually work"** → three columns **Build / Ship / Reuse**, each with a 5-line code or CLI snippet.
- Keep the "2 lines vs 30+ lines" comparison — reframe the caption as *"ship faster at the client."*

### 6.2 Docs information architecture
Keep all technical pages (Agent API, CLI Reference, Models, Plugins, TUI, Auto Debug, Logging) — but reframe the *narrative spine* and add FDE-shaped entry points:
- **New:** `/fde` — "ConnectOnion for Forward Deployed Engineers" (the persona landing page; this is where the acronym leads).
- **New:** "Skills: your reusable client toolkit" guide — productization framed.
- **New:** "Ship to a client" deploy guide — approval gates, trust levels, auth.
- Reframe Quickstart's narration around the Build→Ship→Reuse loop (no API changes, just framing).

### 6.3 README (GitHub / PyPI / npm)
- Open with the FDE one-liner + the 2-line snippet + the reuse promise (skills) in the first screenful.
- Package descriptions (PyPI/npm) updated to the positioning sub-line.

### 6.4 Examples (highest-leverage change)
Replace toy demos with **FDE jobs**:
1. *Wrap a client's internal REST API as an agent tool in 10 lines.*
2. *Turn a one-off data-cleanup script into a reusable skill.*
3. *Deploy a client-facing support agent with approval gates + trust levels.*

The examples **are** the positioning. This is where skeptics convert.

### 6.5 `co` CLI onboarding copy
- First-run and `co create` output should reinforce the loop (e.g., a closing hint: *"Reuse this? `co` package it as a skill."*).
- Keep it terse — no marketing in the terminal.

### 6.6 SEO / content
- Own the uncontested phrases: **"agent framework for forward deployed engineers," "FDE tooling," "reusable AI agent skills," "FDE agent stack."**
- One cornerstone page + a few FDE-workflow posts. These rank because nobody is fighting for them yet.

### 6.7 Social / launch narrative
- Launch thread = the Section 5 story, not a feature list.
- Target FDE channels (the a16z/Pragmatic Engineer/PostHog FDE discourse is active and link-friendly).

---

## 7. What does NOT change (guardrails)

These are load-bearing. The repositioning must not erode them:
- **Simplicity stays the promise.** FDE is the audience, not a replacement for "simple."
- **"2 lines of Python" stays** — concrete, provable, memorable.
- **Progressive disclosure** as design principle.
- **No lock-in, just Python/TS.**
- **No over-engineering in the product or the copy** — no try/except theater, no SaaS adjectives.
- **Agents return raw data**, code doesn't format agent output (our engineering value, visible in examples).

---

## 8. Risks & mitigations

| # | Risk | Mitigation |
|---|---|---|
| 8.1 | **Acronym opacity** — "FDE" means nothing to outsiders | Keep the concrete H1; spell out "Forward Deployed Engineers" one line down; reserve bare "FDE" for the `/fde` page and FDE channels |
| 8.2 | **TAM panic** — self-identified FDEs are a small (fast-growing) set | Correct for a *wedge*. Keep an explicit expansion path in the narrative: *FDEs today → everyone shipping custom agents tomorrow* |
| 8.3 | **Consulting-shop misread** — "for FDEs" sounds like services | Lead with **Reuse/productization**, not staffing. We sell the antidote to consulting, not consulting |
| 8.4 | **Inconsistency** — half-migrated message reads as confused | All-or-nothing per surface; phased rollout (Section 9) |
| 8.5 | **Demoting simplicity** — chasing a trend dilutes the moat | Guardrail 7: simplicity is the durable promise; FDE is the timely bet. Promise > audience |
| 8.6 | **Trend risk** — "FDE" cools off in 2 years | Even if the label fades, the *job* (ship bespoke, productize it) is permanent. The Build→Ship→Reuse spine survives a rename |

---

## 9. Rollout plan (phased, cheap-and-reversible first)

- **Phase 0 — Decide.** Approve this doc + answer Section 10. *(No code.)*
- **Phase 1 — Messaging layer.** Homepage sub-line, README, package descriptions, brand line. *Cheap, reversible, highest signal-per-effort.*
- **Phase 2 — Proof layer.** Rewrite examples as FDE jobs; ship the `/fde` page; one SEO cornerstone.
- **Phase 3 — Product surface.** `co` CLI onboarding copy; "Skills as your reusable toolkit" + "Ship to a client" guides.
- **Phase 4 — Distribution.** FDE-targeted launch thread + content; engage the FDE discourse.

Each phase is independently shippable and independently reversible. Stop after any phase and the brand is still coherent.

---

## 10. Open decisions for Aaron (need answers before Phase 1)

1. **Umbrella brand:** ConnectOnion-forward (rec) or OpenOnion-forward? Where does the FDE story live?
2. **CLI canon:** Confirm `co` (framework) vs `oo` (platform) roles, and that "heavily CLI" = the `co` CLI + `oo` distribution, *not* a new wrapper. Reconcile explicitly with "Skill IS the interface, library IS the engine."
3. **Acronym placement:** Agree FDE leads the `/fde` page + channels, but the global H1 stays the concrete "2 lines" magnet? (rec: yes)
4. **Audience precision:** Primary = solo FDEs at AI startups? agencies/dev-shops building agents per client? both? (changes example choice + tone)
5. **Tagline lock:** Pick the final positioning sub-line from Appendix A.
6. **Scope of v1:** Phase 1 only (messaging), or commit through Phase 2 (examples + `/fde` page) as the real launch?

---

## Appendix A — Slogan / sub-line candidates

Headline (keep, all options): **Build AI Agents in 2 lines of Python**

Positioning sub-line candidates:
1. *(rec)* "The simple framework Forward Deployed Engineers ship with — build a bespoke agent in an afternoon, keep it as a reusable skill."
2. "Ship bespoke agents. Keep them as skills." *(shortest; productization-forward)*
3. "From client hack to reusable skill — in one framework."
4. "The FDE's agent framework: build fast, ship to any client, reuse everything."
5. "Simple agents for Forward Deployed Engineers. Build → Ship → Reuse."

Durable brand line (unchanged): **Keep simple things simple, make complicated things possible.**

## Appendix B — Three FDE example use-cases (to replace toy demos)
1. **Wrap a client API in 10 lines** — function-as-tool, no wrappers; running agent by lunch.
2. **One-off script → reusable skill** — take a throwaway data-cleanup script, `co`-package it, publish via `oo`, reuse next client.
3. **Client-facing agent, safely** — approval gates + trust levels + deploy behind the client's auth.

## Appendix C — Sources (FDE market)
- Pragmatic Engineer — *What are Forward Deployed Engineers, and why are they so in demand?*
- a16z framing — "the hottest job in startups," ~800% growth in 2025
- Perspective AI — *State of Forward Deployed Engineering 2026 (survey of 1,500 FDEs)* and *2026 Founder's Playbook*
- PostHog — *WTF is a forward deployed engineer?*
- Rocketlane — *Forward Deployed Engineer: The Essential 2026 Guide*
- Wikipedia — *Forward Deployed Engineer*

---

*This document is intentionally pre-implementation. Nothing here changes code or copy until Phase 0 is approved.*
