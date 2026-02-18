# AI Research Workspace

A focused workspace for managing the full lifecycle of AI research:

**Papers → Thesis → Experiments → Results → Findings**

This system exists to preserve continuity between what I believe, why I believe it, and the evidence supporting or refuting those beliefs.

---

## Core Concept

Research is not just reading papers or running experiments.
It is the continuous refinement of claims under evidence.

This workspace enforces a simple structure:

1. **Collect knowledge**
2. **Develop structured ideas**
3. **Design and run experiments**
4. **Extract findings**
5. **Update beliefs**

Every step remains connected.

---

## The Research Loop

The system revolves around a single reinforcing loop:

**Save Paper → Attach to Idea → Design Experiment → Run → Summarize → Extract Finding → Update Idea**

Each cycle strengthens or weakens a thesis.
Nothing floats unanchored.

---

## Foundational Objects

The workspace is built around a small set of research primitives.

### Paper

A structured representation of external knowledge.

* Metadata and source
* Core claims
* Methods and evaluation details
* Notes and commentary
* Links to related ideas

Papers become structured inputs to reasoning, not static PDFs.

---

### Idea (Thesis)

A living argument under development.

* Problem statement
* Hypothesis
* Testable predictions
* Linked papers
* Linked experiments
* Linked findings
* Open questions

Ideas evolve as evidence accumulates.

---

### Experiment

A concrete test of a prediction.

* Goal and protocol
* Configuration snapshot
* Metrics and evaluation criteria
* Linked runs
* Summary of results

Experiments are the operationalization of a thesis.

---

### Run

An executed instance of an experiment.

* Configuration and commit state
* Logged metrics
* Artifacts and outputs
* Structured summary

Runs provide raw evidence.

---

### Finding

A claim supported by empirical evidence.

* Statement
* Supporting runs
* Confidence level
* Impacted ideas

Findings are the bridge between data and belief.

---

## Structural Principle

Everything must be linkable.

* Papers inform Ideas
* Ideas generate Experiments
* Experiments produce Runs
* Runs produce Findings
* Findings update Ideas

The system forms a research graph, not a document folder.

---

## Design Philosophy

* Minimal object model
* Persistent research memory
* Evidence-backed claims
* No context fragmentation
* No detached experiments
* No unsupported beliefs

The workspace does not replace experimental tools or literature sources.
It connects them.

---

## Purpose

To create a persistent, structured research memory where:

* Hypotheses remain explicit
* Evidence remains traceable
* Results are not forgotten
* Iteration compounds

This is not a note-taking system.
It is a belief refinement engine for AI research.

---

## Quick Start: GPT-5 + Semantic Scholar

This repo now includes a minimal chat assistant wired to Semantic Scholar tools:

- Search papers
- Get paper recommendations
- Fetch paper details
- Read open-access full paper text (when available)

### Setup

1. Create and activate a Python environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Ensure your `.env` includes:

- `OPENAI_API_KEY`
- `S2_KEY`

### Run

```bash
python gpt5_semantic_scholar_chat.py
```

### Example prompts

- "Find the best recent papers on verifier-guided question generation."
- "Recommend papers similar to arXiv:2301.00001."
- "Read the full paper for CorpusID:123456 and summarize evaluation."

If a paper does not expose an open-access PDF through Semantic Scholar, the assistant will report that and suggest alternatives.

---

## Runtime State Environments

`minimal_memory_chat.py` supports isolated runtime state environments via `RM_ENV`.

- Default: `dev`
- Allowed values: `dev`, `prod`
- State files:
  - `state/dev/index.jsonl` + `state/dev/generated/`
  - `state/prod/index.jsonl` + `state/prod/generated/`

Run examples:

```bash
RM_ENV=dev python minimal_memory_chat.py
RM_ENV=prod python minimal_memory_chat.py
```

For production-style runs that always sync to `main` first:

```bash
./scripts/run_prod.sh
```
