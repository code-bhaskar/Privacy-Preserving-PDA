# BuildSprint Idea Briefs

**Prepared for team discussion — LatentForce.ai BuildSprint (48-hour online build sprint, no fixed theme).**

Nine candidate ideas, grouped into three families:

- **A. AI-Infrastructure / Dev Tools** — PromptCI, AgentProfiler, DeadChunk, BreakBot
- **B. Privacy & Trust Products** — ProofOfDelete, ConsentLedger, PPDA
- **C. Code Provenance** — GitGuard, CodeTwin

---

## Family A — AI-Infrastructure / Dev Tools

> Theme: everyone is shipping LLM systems, but the tooling to **test, debug, profile, and maintain** them barely exists. These projects fill gaps *in the AI field itself*.

### 1. PromptCI — Regression testing for prompts 🥇 (AI-infra pick)

**One-liner:** *"Prompts are code. Nobody tests them. We built the CI."*

**Problem:** Teams change prompts, bump model versions, or switch providers to save cost — and discover what broke from angry users. Prompt changes are the most-deployed, least-tested artifact in modern software.

**Solution:** A CI pipeline for prompts. Save real inputs/outputs from logs as test cases. On every prompt/model change, PromptCI re-runs all cases against OLD vs NEW and reports:

```
✓ 34 cases unchanged
🟠 3 cases changed semantically (side-by-side diff)
🔴 2 cases now fail assertions:
   - case #12: output no longer valid JSON
   - case #29: total_amount wrong (₹4,820 → ₹482)
→ Block merge  /  Approve & re-baseline
```

**Key features:**
- Deterministic assertions (JSON schema, regex, must-contain, numeric tolerance) + semantic diff for the rest
- "Capture from logs → save as test case" workflow (test creation is nearly free)
- Baseline-approval flow wired into git (block merge on regression)

**Tech:** CLI + FastAPI backend, test runner, embedding-based semantic diff, simple web report UI.

**Demo arc (2 min):** Edit one line of a prompt → push → report catches a regression the naked eye would miss → block merge → fix → green.

**Strengths:** Maximum resonance with AI-dev-tools judges; clean 48h decomposition; real unowned gap (as a simple, self-hostable git-native tool).
**Risks:** Space is warming up (LangSmith, Braintrust adjacent) — differentiation must live in the workflow, not the concept.

---

### 2. AgentProfiler — The flame graph for LLM pipelines

**One-liner:** *"Where do your agent's tokens, seconds, and rupees actually go?"*

**Problem:** An agent run costs ₹18 and takes 40s. Why? Which step? Which retries? What % of the context window is boilerplate re-sent 12 times? Today the answer is "grep the logs." Normal software has profilers/APM; AI has a void.

**Solution:** A lightweight Python decorator/proxy that wraps LLM calls and renders a cost/latency/token flame graph per run:

```
Run #4412 — ₹18.40, 41.2s, 9 LLM calls
█████████████ planner   41% (₹7.60) ← 3 retries!
⚠ 61% of input tokens = repeated system prompt
💡 Cache-hit potential: ₹6.10/run (33%)
```

**Key features:** per-step cost/latency breakdown, retry detection, repeated-context waste analysis, cache-savings estimator.

**Tech:** 100% deterministic engineering — token counting, timing, tree visualization. **No AI needed in the build; nothing can flake mid-demo.**

**Demo arc:** Run an agent → open the flame graph → spot the waste → apply fix → re-run at 33% lower cost.

**Strengths:** Zero-flake demo; unglamorous space = little competition; judge-proof punchline.
**Risks:** Needs a realistic demo agent to profile; less "wow" for non-technical audiences.

---

### 3. DeadChunk — Auditor for rotting RAG knowledge bases

**One-liner:** *"Your RAG answers are only as good as your knowledge base — and nobody audits the knowledge base."*

**Problem:** RAG KBs rot silently: chunks that are never retrieved, near-duplicate chunks that split relevance scores, and chunks that **contradict each other** (old policy vs new policy). Teams debug the retriever and the prompt, never the data.

**Solution:** Point it at a vector store + query logs. It reports:

```
🔴 412 chunks never retrieved (dead weight, 31% of KB)
🔴 18 contradiction pairs (e.g. "refund within 30 days" vs "14 days")
🟠 96 near-duplicate clusters splitting retrieval scores
🟠 44 stale chunks (superseded by newer docs)
→ Cleaned KB export + before/after retrieval quality comparison
```

**Tech:** embeddings + clustering for duplicates; NLI or LLM-judge for contradictions; log analysis for dead chunks.

**Demo arc:** Ask a question → RAG gives a wrong answer sourced from a stale chunk → DeadChunk flags the contradiction → clean → same question now answered correctly.

**Strengths:** Genuinely under-served gap; strong "aha" demo (contradictory chunks are shocking).
**Risks:** Medium — needs a convincing demo KB with planted rot; contradiction detection can false-positive.

---

### 4. BreakBot — Dependency-upgrade impact analysis

**One-liner:** *"npm audit tells you what's vulnerable. Nothing tells you what breaks."*

**Problem:** Everyone freezes dependencies at old versions because upgrading is terrifying. Dependabot opens the PR, CI goes red, you close it. The info needed to upgrade safely exists (changelogs, migration guides, your call sites) — no human wants to cross-reference them.

**Solution:** Give it your repo + "upgrade pydantic 1.10 → 2.8". It fetches the changelog, finds every place *your* code touches changed APIs, and produces a verdict per call site:

```
🔴 app/models.py:41   .dict() removed → use .model_dump()
🔴 app/api/user.py:88 validator syntax changed
🟠 app/config.py:12   default coercion changed silently
🟢 61 other usages unaffected
[Generate fix PR] → patched diff, ready to review
```

**Key differentiator:** every verdict cites the changelog lines it's based on (credibility feature). AI is essential here — changelog-to-callsite reasoning can't be done with regex.

**Tech:** repo ingestion (`ast` parsing for imports/usages), changelog fetcher, LLM verdict per call site, patch generation, web report.

**Demo arc:** Red impact report → click "Generate fix PR" → tests go green. Scope honestly: one language (Python), 3–4 famous breaking upgrades (pydantic 1→2, SQLAlchemy 1.4→2.0).

**Strengths:** Dev judges feel this pain personally; agentic AI doing *real* reasoning, not a chatbot wrapper.
**Risks:** Patch generation quality; must pre-select demo repos/upgrades carefully.

---

## Family B — Privacy & Trust Products

> Theme: leverages our existing PPDA codebase (hash-chained audit logs, AES-GCM, JWT, Shamir secret sharing, ONNX on-device inference). ~30–40% head start on infrastructure.

### 5. ConsentLedger — "A receipt for your data"

**One-liner:** *"Companies keep consent records for legal protection. Users keep nothing."*

**Problem:** When you sign up for an app, upload a document, or talk to an AI, you have no record of what you consented to, what data left your device, or who can see it.

**Solution:** A personal, tamper-evident ledger of every data-sharing event:

```
Event: Uploaded resume to JobPortal.com
Data: name, phone, employment history
Consent scope: "recruitment matching only"
Retention claimed: 180 days
Hash-chained record ✓ (provably un-editable)
Later: "JobPortal's policy changed on 12 Mar —
        no longer matches your stored consent. Review?"
```

**Key features:** hash-chained (tamper-evident) event log, AES-GCM encrypted payloads, policy-text differ that alerts when terms drift from recorded consent.

**Tech reuse:** PPDA's audit hash-chain + encryption-at-rest + JWT auth, nearly as-is. Add capture flow (extension or upload) + dashboard + policy differ.

**Demo arc:** Record consents → live-tamper with the database → ledger screams → policy-diff alert fires. Theatrical and 10 seconds to show.

**Strengths:** ~40% pre-built; India's DPDP Act makes consent records legally hot right now; "receipt for your data" lands in 20 seconds.
**Risks:** Consumer adoption story is hand-wavy (who installs this?); capture flow must not look like vaporware.

---

### 6. ProofOfDelete — Verifiable data-deletion certificates

**One-liner:** *"They said 'your data has been deleted.' Prove it."*

**Problem:** GDPR/DPDP grant the right to be forgotten, but when a company claims deletion, users just have to believe them. There is no verifiable artifact.

**Solution:** A deletion-attestation service. Companies integrate a small SDK that emits a **cryptographically signed deletion certificate** (record hash + timestamp + position in a public hash chain). Users hold verifiable proof; regulators get an audit trail.

**Tech:** signing service + hash chain (reuse PPDA audit chain), SDK stub, verification portal.

**Demo arc:** Simulate a company deleting a record → certificate issued → user verifies → then simulate a *fake* deletion → verification fails.

**Strengths:** Sharp B2B compliance story (DPDP Act tailwind); technically distinctive.
**Risks:** Two-sided market — demo requires simulating the company side; judges may ask "why would companies adopt this?" (answer: regulatory pressure, but it's a debate).

---

### 7. PPDA — Privacy-Preserving Digital Assistant (existing project)

**One-liner:** *"A personal assistant where the privacy guarantees are cryptographic, not promises."*

**What it is (already built):** Local-first assistant backend — FastAPI + PostgreSQL/SQLite:
- Zero-trust JWT auth, rate limiting, IDOR immunity
- AES-256-GCM encryption at rest for events/reminders/messages
- On-device ONNX intent classifier (<1 ms) + occlusion-saliency explainability
- Tamper-evident audit logging (append-only triggers + SHA-256 hash chaining)
- Cryptographic federated learning: Bonawitz secure aggregation (X25519, ChaCha20 masking, Shamir threshold shares) + Rényi DP accounting

**As a BuildSprint entry:** Strongest *technical depth* of all nine, but it's pre-existing work (sprint rules and judge perception may penalize that), and "privacy assistant" takes longer than 20 seconds to pitch. **Best used as an infrastructure quarry** for ConsentLedger / ProofOfDelete rather than as the entry itself.

---

## Family C — Code Provenance

> Theme: "was this project derived from that one?" Discussed earlier; kept here for completeness with our earlier verdicts.

### 8. GitGuard — Explainable project provenance

**One-liner:** *"Code similarity says 'these look alike.' GitGuard asks 'is there evidence this project was derived from that registered project?'"*

**Concept:** Register a project → generate a digital fingerprint (code, AST, dependencies, structure, semantics, metadata/timestamps) → compare future repositories against it → output an **explainable provenance score** with evidence breakdown (Original / Related / Potentially Derived / Highly Similar).

**Differentiator vs plain similarity tools:** similarity is *evidence*, not the product. The product is the **registration → fingerprint → later comparison → explainable evidence** workflow.

**Strengths:** Broader problem statement than clone detection; explainability angle.
**Risks:** Judges may still bucket it as "another plagiarism detector"; provenance claims are hard to validate rigorously in 48h; weakest fit for an AI-dev-tools audience among the strong candidates.

---

### 9. CodeTwin — Structural/semantic code similarity ⚠️ (previously rejected)

**One-liner:** *"Find structurally and semantically similar code across repositories."*

**Concept:** AST normalization + code fingerprints + semantic embeddings → similarity scores between codebases.

**Earlier verdict (unchanged):** ❌ **Do not build as a standalone project.** It overlaps with existing code-similarity tools (e.g. the "Ponytail" comparison) and reads as "another code clone detector." Its techniques are better used as the similarity-evidence engine *inside* GitGuard — or dropped entirely.

---

## Comparison Matrix

| Idea | Family | Problem clarity (20s test) | AI-judge appeal | 48h feasibility | Novelty | Uses our existing skills/code | Overall |
|---|---|---|---|---|---|---|---|
| **PromptCI** | AI-infra | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | FastAPI, LLM orchestration | 🥇 |
| **AgentProfiler** | AI-infra | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | Pure engineering | 🥈 |
| **BreakBot** | AI-infra | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | Python/AST, LLM | 🥉 |
| **DeadChunk** | AI-infra | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | Embeddings, RAG experience | Strong |
| **ConsentLedger** | Privacy | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ~40% from PPDA | Strong |
| **ProofOfDelete** | Privacy | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | Hash chain from PPDA | Medium |
| **PPDA** | Privacy | ⭐⭐ | ⭐⭐⭐ | (pre-built) | ⭐⭐⭐ | It *is* our code | Quarry, not entry |
| **GitGuard** | Provenance | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | Some | Backup only |
| **CodeTwin** | Provenance | ⭐⭐⭐ | ⭐ | ⭐⭐⭐ | ⭐ | Some | ❌ Rejected |

## Recommended team decision framing

1. **If judges are AI-dev-tools people (LatentForce = yes):** pick from Family A. → **PromptCI** (max resonance) or **AgentProfiler** (zero-flake demo, least competition).
2. **If we want to reuse the most existing code:** **ConsentLedger** (PPDA hash-chain + crypto, DPDP Act tailwind).
3. **If we want AI doing visible heavy-lifting in the demo:** **BreakBot**.
4. **Avoid:** CodeTwin standalone; PPDA as-is (pre-existing work); GitGuard only as fallback.

**Suggested vote:** each teammate ranks their top 3; tie-break on "which demo can we make bulletproof by hour 40?"
