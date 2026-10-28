# Usage

## The three-column layout

**Left** — model and sampling. **Centre** — the prompt and the output.
**Right** — history, saved prompts, stats. On a phone it stacks in that order.

## Picking a model

The dropdown lists ten open-weight models. The card underneath shows family,
parameter count, context window and licence — the things that actually decide
whether a model fits your machine.

Context window is the number to watch. A 131k model on a laptop with 8GB of RAM
will not run at full context; the window is a capability, not a promise.

## Sampling, briefly

**Temperature** — 0 is deterministic, 0.7 is a good default, above 1.2 gets
strange. For extraction and classification, use 0.

**Top-p** — nucleus sampling. 0.95 is standard. Lower it to 0.8 when you want the
model to stay on the rails.

**Max tokens** — the ceiling on the reply. It's *reserved* from the context
window whether or not the model uses it, which is why the budget meter counts it.

## The budget meter

Updates as you type. Four numbers:

- **Prompt** — estimated tokens in your system + user prompt
- **Reserved** — max tokens held back for the reply
- **Window** — the model's context limit
- **Used** — prompt + reserved

The bar turns amber past 75% and red past 95%. If it goes over, the note tells you
by how much and what to do about it.

The estimate is a word/character blend, not a real tokenizer. It's within about
10% for English prose and deliberately conservative for code. Treat it as a
guardrail, not an invoice.

## The template inspector

Click **Show template**. You get the exact string the model receives, with the
special tokens in place, plus the stop sequences that template requires.

This is the single most useful button in the app. If a model is answering badly,
check the template first — a wrong wrapper produces plausible-looking garbage
rather than an error.

## Running

**Run** — one request, full response, persisted to history.

**Stream** — same request over SSE, tokens as they arrive. The run is saved when
the stream closes.

**Compare two** — the current model plus the next one in the catalog, same
prompt, run sequentially. Sequential on purpose: two models in parallel on one
GPU just make each other slower as they swap weights in and out of VRAM.

**Ctrl/Cmd + Enter** runs the prompt from anywhere in the editor.

## Reading the output

The header line under **Output** tells you what produced the text:

```
Llama 3.1 8B Instruct · ollama · 1840 ms · 312 tokens
```

If it says `inspector`, no model was called — you're looking at prompt analysis,
not generated text. The output itself says so in its first two lines.

## History

Every run is stored with its backend, latency, token count and cost. Click any
entry to load that prompt and its output back into the editor — useful when you
want to tweak one word and re-run.

## Saved prompts

**Save** stores the current system + user prompt under a name. Click a saved
prompt to load it. This is what makes the playground usable day to day: the
prompt you got right on Monday is still there on Friday.

## Stats

Four numbers at the top of the right column: total runs, average latency, total
tokens, and your most-used model. They're per-account, not global.

## Keyboard

| Key | Action |
|---|---|
| `Ctrl`/`Cmd` + `Enter` | Run the prompt |
| `Esc` | Close a dialog |
