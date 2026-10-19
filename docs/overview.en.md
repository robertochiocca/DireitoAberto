# DireitoAberto — technical overview (English)

DireitoAberto helps Brazilian citizens understand their rights: it answers plain-language questions
with the applicable legal provisions, reads court case files, and tracks changes in official law
texts. The goal is a **verifiable** legal-information system rather than a chatbot: every claim points
to its source, the system says when it does not know, and nothing it shows depends on trusting a
language model.

This page summarizes the engineering. The full documentation is in Portuguese in this folder.

## Components

| Component | What it does | How it earns trust |
|---|---|---|
| Legal RAG (`backend/app/retrieval.py`, `llm.py`) | BM25 with citizen-vocabulary synonyms over a curated corpus of 79 provisions; optional LLM generation; extractive fallback | Retrieval compared against semantic and hybrid search with 586 manual relevance labels; the corpus carries per-provision validity (in force, not yet in force, repealed, unconstitutional), recomputed on the query date in Brasília time |
| Answer validation (`validacao.py`) | Each answer gets a validation state: verified source and version, sufficient evidence, source found, human review recommended, source conflict, outdated source, insufficient evidence | Deterministic checks only (evidence strength vs. a calibrated threshold, official source, text checked against the official version, validity, review flags, conflicting versions, citations in generated text). Below the threshold the API abstains |
| Case-file reader (`leitor/`) | Reads a lawsuit PDF page by page: parties, filings, timeline, allegations, requests, rulings, obligations, deadlines, appeals, missing pages | No LLM. Every item is a verbatim sentence with PDF page and court sheet number, checked against the page before it is shown, and labelled by nature (party allegation ≠ registered fact ≠ judicial decision). Unreadable pages and missing sheets are reported, never guessed |
| Legislative monitor (`monitor/`) | Fetches official pages, hashes the normalized in-force text, diffs article by article, classifies changes, maps impact to corpus entries, writes a report, queues human review | Struck-through (repealed) text excluded; a missing article is never treated as a repeal; suspicious fetches produce no changes; only low-risk changes are auto-accepted; full history and rollback |
| Evaluation (`avaliacao.py`, `scripts/avaliar.py`) | Recall@k, MRR, nDCG, precision, abstention, temporal-trap benchmark, reader vs. gold standard, corpus fidelity, latency | Calibration/validation split; versioned baseline; a test fails if any tracked metric regresses |

## Selected results (validation split, see `docs/avaliacao/relatorio.md`)

- Retrieval: Recall@3 100%, MRR@10 94.0%, nDCG@4 89.0% (75 held-out questions).
- Abstention: 8 of 13 out-of-scope questions correctly abstained; 3 of 75 legitimate questions wrongly
  abstained. The remaining 5 out-of-scope questions still get unrelated provisions — a known limit.
- Reader (synthetic case file): 39/39 gold items found, 79/79 citations verified, 0 forbidden claims.
- Corpus fidelity against the official in-force text: of 46 checked provisions, 8 are verbatim and 15
  are paraphrases or explanations — a data-quality issue the audit surfaced and the roadmap addresses.

## Engineering practices

- Audit first: `docs/security-audit.md` and `docs/legal-data-sources.md` record what was confirmed,
  what is a potential risk and what was not verified.
- Security fixes with regression tests that fail on the previous code: session expiry and revocation,
  rate limiting, restricted CORS, bounded uploads, data minimization (anonymous questions are not
  stored), document ownership (IDOR tests), prompt-injection delimiting, XSS.
- CI on Python 3.10 and 3.13 (ruff, mypy, pytest including a headless-browser test and the evaluation
  gate) and a Next.js type check and build.

## Known limits

Gold standards, relevance labels and the out-of-scope set were written by the project and have not
been reviewed by a legal professional. The reader was measured on a synthetic case file and does no
OCR. LLM output quality was not measured (no API key in the development environment). User
comprehension was not measured. This is legal information, not legal advice.
