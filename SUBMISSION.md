---
title: "Kshetrajna Drift: I Let a Local Llama Deal With My Download Pile"
published: false
tags: devchallenge, hf26challenge
---

*This is a submission for the [Hacktoberfest Open-Source AI Challenge Week 3: Slow and Steady](https://dev.to/challenges/hacktoberfest-week3-2026-10-19).*

## What I Built

I don't usually put off filing a document because dragging it is difficult. I put it off because I have to decide what it is, where it belongs, and whether I will find it again.

**Kshetrajna Drift** takes that first decision off my plate. It is a small local companion that reads one approved folder, asks an open-weight model to suggest homes for loose files, and shows an explanation for each suggestion. I select the moves I agree with and approve them together.

A receipt, a client brief, and a picnic note might all be `.txt` files. They should not necessarily live together. Drift groups by purpose: Study, Work, Receipts, Personal, Read Later, or Keep here.

The final category matters. Sometimes the laziest sensible action is to leave something alone.

## Demo

The package includes `evidence/walkthrough.gif`: a recorded walkthrough made from seven actual browser UI snapshots. Waiting is condensed. The files are synthetic, but the inference, approved move and undo are real.

The walkthrough shows a client handover brief going to Work, revision notes to Study, a payment receipt to Receipts, a bird article to Read Later, and a picnic note to Personal. An ambiguous note containing “blue / maybe next time / 42” stays where it is. I then move the receipt and undo it.

Run the same demo with `python app.py --demo`. It creates a disposable copy of the six bundled samples and leaves personal Downloads alone.

**Draft publication note:** add the public source and recorded-demo links here before publishing. Those uploads require a separate approval; this draft does not claim they are already online.

## Code

The new standalone source package contains the Python application, dependency-free browser interface, six fixtures, tests, setup guide, license and measured evidence. The code is MIT licensed. The public repository link is pending publication approval.

**Credit:** Drift is inspired by our existing [Kshetrajna project](https://github.com/Team-SankatMochan/KSHETRAJNA-OS), especially its Observe → Explain → Approve → Act → Recover approach. This is a new application created on October 25, not the older application presented as fresh work. No source files were copied from that repository.

## How I Built It

The reasoning engine is **Llama 3.1 8B**, running through an installed **Ollama** service on the same computer. The model receives file IDs, filenames, sizes, and optionally short previews of supported text files. The real-folder default sends filenames and sizes only. The sample demo enables previews so the purpose of vague filenames is visible.

The model must return structured JSON: a known file ID, an allowed category, and a short reason. Drift independently validates the answer. Missing IDs, duplicates, invented categories, unexpected fields and invalid explanations stop the plan. If the model is unavailable, the app reports an error and moves nothing. There is no hidden filename-rule classifier substituting for AI.

The rest uses Python's standard library, SQLite and plain HTML/CSS/JavaScript. The local server binds to loopback. The model cannot issue shell commands or choose arbitrary filesystem paths.

```mermaid
flowchart LR
    A[Approved folder] --> B[Bounded local scan]
    B --> C[Ollama and Llama 3.1 8B]
    C --> D[Validate IDs and categories]
    D --> E[Explained plan]
    E --> F[Select and approve]
    F --> G[Recheck files and destinations]
    G --> H[Journal then move]
    H --> I[Undo and restart recovery]
```

Before execution, Drift rechecks hashes, file identity, sizes and modification times. Existing destinations block the selection. Each file's move intent is committed to SQLite before its destination is created without overwriting another file. The source name is then removed. This requires same-volume hard-link support; unsupported filesystems fail without a copy/delete fallback.

The batch is not atomic: if a later move fails, earlier successful moves remain visible and undoable. Undo refuses changed files or occupied original names. Interrupted operations are reconciled on restart, with unresolved conflicts kept visible.

**31 automated tests passed on Windows**, including real file moves and undo, changed-file rejection, name conflicts, interrupted-operation recovery, malformed model output, model failure and local HTTP access checks. The model run is recorded separately from tests that use explicit doubles.

## Why Does Open Innovation Matter?

For this workflow, the inputs can be the private things sitting on a person's computer. Running the model locally means a hosted provider does not have to receive the filenames or snippets to make a filing suggestion.

It also lets me change the prompt, category policy, validation and execution behavior together. The model proposes; code I control sets the limits. Another installed local model can be selected without replacing the whole application.

After the runtime and weights are installed, the workflow can operate without an internet connection. I verified local loopback inference; I have not yet measured a disconnected-network run. There is no hosted per-request model charge, though the computer, storage and electricity still cost money.

Ollama is open-source software. Llama 3.1 is **open-weight under Meta's Community License**, which is different from calling its weights OSI open source. The model is not bundled in the source package.

## The Lazy Payoff

The first six-file plan took **17.56 seconds**. All five filing choices and the Keep-here decision matched the intended sample purposes. A second recorded walkthrough run took **15.24 seconds**. After moving and undoing the receipt, all six originals matched their fixture SHA-256 hashes.

This is a small synthetic demonstration, not a measured claim about hours saved or general classification accuracy. It shows the interaction I wanted: let the machine read the small pile, review one clear plan, and go back to something more interesting.

The deliberate limit is twelve loose files per batch. This prototype has no background watcher, PDF extraction, OCR, automatic deletion, or unattended sorting. Slow and steady seemed like a good reason to make the scope small enough to understand.

*Built with AI coding assistance. Design references: [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs), [Llama 3.1 license](https://github.com/meta-llama/llama-models/blob/main/models/llama3_1/LICENSE). Community reading included [Jangwook Kim's structured-output walkthrough](https://dev.to/jangwook_kim_e31e7291ad98/ollama-structured-outputs-in-practice-getting-type-safe-json-from-local-llms-with-pydantic-m38) and [Neeraj Singhi's tool-boundary validation discussion](https://dev.to/neeraj_singhi_golang/prompt-injection-at-the-tool-boundary-sanitizing-llm-driven-function-calls-in-go-microservices-4emb). Comment retrieval was unavailable; these are individual references, not a claimed community consensus.*
