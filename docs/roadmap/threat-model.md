# Multi‑Agent Collaboration Threat Model (Top 10)

## 1) Capability Fraud

- Scenario: An agent claims high‑quality capability (e.g., translation) but actually uses low‑quality/free backends.
- Real cases:
  - Claims “GPT‑4” but actually uses GPT‑3.5
  - Claims medical competence without relevant training
  - Claims originality but outputs plagiarized mashups
- Why critical:
  - Easy to execute (change description only)
  - Hard to verify (deep testing required)
  - Strong economic incentive (adverse selection)
  - Already widespread in today’s API market
- Impact: Task failure, data leakage, financial loss, collapse of trust

## 2) Data Harvesting

- Scenario: Malicious agents offer free/cheap services to harvest data.
- Real cases:
  - “Free” translation logs all business docs
  - Image processing stores all uploads
  - Code assistants collect proprietary algorithms
- Why dangerous:
  - Users unaware; high data value; scales easily; hard to trace
- Impact: Trade secret leakage, privacy violations, IP theft, loss of competitiveness

## 3) Cost Manipulation

- Scenario: Malicious agents trigger high‑cost operations to drain resources.
- Real cases:
  - Infinite loops, oversized inputs, recursive call chains
  - Inducing expensive third‑party API calls
- Why realistic:
  - Exploits metered billing
  - Hard to distinguish malicious vs. normal
  - Can cause rapid, large losses
  - Defenses can impair normal use
- Impact: Large bills, outages, resource exhaustion, budget overruns

## 4) Collusion Attacks

- Scenario: Multiple agents collude to fabricate validation and deceive the system.
- Real cases:
  - Fake review networks; mutual endorsements; consensus manipulation
  - Synthetic market signals
- Why hard:
  - Resembles normal network effects
  - Distributed collaboration is hard to detect
  - Evades simple verification
  - Social‑engineering component
- Impact: Market manipulation, trust failure, wrong decisions, systemic risk

## 5) Prompt Poisoning

- Scenario: Malicious instructions embedded in normal inputs alter agent behavior.
- Real cases:
  - Control directives embedded in text to translate
  - Context hijacking; jailbreaks; persistent backdoors
- Why common:
  - Inherent LLM weakness; hard to fully filter; covert propagation; very low cost
- Impact: Loss of control, boundary bypass, cross‑agent contamination, integrity breach

## 6) Service Degradation

- Scenario: Agent gradually lowers quality, then ransoms access after lock‑in.
- Real cases:
  - High quality at first, then degrade; fail at critical times; “maintenance” outages; paywalls to restore
- Why insidious:
  - Boiling‑frog pattern; switching cost exploitation; timing for max damage; monopoly‑like behavior
- Impact: Business interruption, forced payments, high migration cost, missed windows

## 7) Identity Theft

- Scenario: Malicious agent impersonates a trusted/known one.
- Real cases:
  - Fake “official” services; clones of popular OSS; counterfeit CAs; mimicking behavior of famous agents
- Why easy:
  - No global identity; users can’t easily verify; behavior can be mimicked; brand trust is exploitable
- Impact: User fraud, brand damage, misattribution, legal exposure

## 8) Supply Chain Poisoning

- Scenario: Attack upstream dependencies (models, data, libs, endpoints).
- Real cases:
  - Tainted training data; swapped model weights; modified libraries; hijacked APIs
- Why severe:
  - Affects all downstream; hard to detect; long‑lived; costly to remediate
- Impact: Massive leaks, systemic bias, backdoors, cascading failures

## 9) Privacy Inference

- Scenario: Repeated interactions allow inference of sensitive information.
- Real cases:
  - Inferring business plans from translation jobs
  - Deriving algorithms from code completions
  - Building user profiles from Q&A history; side‑channel analysis
- Why covert:
  - Each request looks benign; value emerges from aggregation; users unaware; regulatory grey areas
- Impact: Privacy leaks, competitive intel theft, profiling markets, targeted attacks

## 10) Dependency Hijacking

- Scenario: Free/cheap at first; once dependent, sudden price hikes or shutdowns.
- Real cases:
  - 10× price hike; key features paywalled; export disabled; forced incompatible upgrades
- Why real:
  - Common online business tactic; exploits switching costs; data lock‑in; time pressure
- Impact: Budget blow‑outs, forced rewrites, continuity risk, weak bargaining position

---

## Severity Matrix

```
High Probability + High Impact (prioritize):
├── Capability Fraud
├── Data Harvesting
└── Cost Manipulation

High Probability + Medium Impact:
├── Prompt Poisoning
├── Service Degradation
└── Identity Theft

Low Probability + High Impact:
├── Collusion Attacks
├── Supply Chain Poisoning
└── Dependency Hijacking

Persistent Threat:
└── Privacy Inference (cumulative)
```

---

## Key Insights

1) Economic incentives are the root cause — most threats are profit‑driven; they will happen.
2) Trust asymmetry is the vulnerability — information asymmetry enables deception.
3) Scale amplifies risk — automation makes attacks replicable to millions.
4) Combined attacks are worse — compositions create exponential damage.
5) Defense cost dilemma — perfect defense can cost more than expected loss.

---

## Defensive Principles (Not to block all attacks, but to make them unprofitable)

- Make attack cost > payoff
- Keep damage bounded and recoverable
- Ensure actions are auditable
- Grow antifragility under pressure

Core strategies:
- Economic alignment: make honesty more profitable
- Transparent auditing: leave malicious action no cover
- Risk dispersion: avoid single points of dependence
- Rapid recovery: accept failure, recover fast