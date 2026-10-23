# DireitoAberto — technical overview (English)

DireitoAberto helps Brazilian citizens understand their rights: it answers plain-language questions
with the applicable legal provisions, reads court case files, and tracks changes in official law
texts. The goal is a **verifiable** legal-information system rather than a chatbot: every claim points
to its source, the system says when it does not know, and nothing it shows depends on trusting a
language model.

This page summarizes the engineering. The full documentation is in Portuguese in this folder.

## Components (round 9.0, 22 Oct 2026)

| Component | What it does | How it earns trust |
|---|---|---|
| Provenance (`backend/app/corpus/`, `scripts/corpus.py`) | Each provision carries official excerpts extracted from the monitored official page (141 excerpts, with hash, source version and date), the nature of the curated text (consolidated official text, explanatory summary, legal interpretation, unchecked), declared gaps, and a sealed history | Excerpts are re-extracted and checked in CI; any word not on the page fails the check; every change has an owner and a reason; rollback. A paraphrase is never shown as a transcription |
| Temporal retrieval (`temporal.py`, `consulta.py`, `retrieval.py`) | Detects the intent (current, historical, change, repeal, legal basis) and the reference date; returns the version applicable on that date first; BM25 with synonyms and an adaptive cut-off chosen by grouped cross-validation | Unknown validity is an explicit `nao_verificada` state, never "in force"; uncertainty becomes a warning, not a guess |
| Answer policy and verification (`validacao.py`, `verificador.py`, `politica.py`) | Five response modes (answer, answer with caveats, ask for clarification, not verified, refer to a professional); generated text checked against the sources | Deterministic rules only — the model's self-reported confidence is never used. Generated text that fails verification is discarded in favour of the extractive answer |
| Case-file reader (`leitor/`) | Reads a lawsuit PDF/TXT page by page: filings, rulings (including appellate decisions), deadlines, inconsistencies, unread pages | No LLM. Every item is a verbatim sentence with its page, checked before it is shown, and labelled by nature; no deadline date is ever computed; text inside documents is data, never instructions |
| Legislative monitor (`monitor/`) | 34 official pages: fetch with retries, struck-text-aware reading, article diff, typed legal events, dependency index, alerts and exit codes, simulation mode, human review, controlled publication into the corpus | A failed, blocked or truncated fetch is never a change, and a missing article is never a repeal; only low-risk changes are auto-accepted; the corpus changes only through a human-approved publish step with regression checks |
| Feedback (`feedback.py`) | Users flag a problem on a cited provision; a person triages it | Feedback never changes the corpus, validity or confidence parameters by itself; personal data in comments is masked |
| Evaluation (`avaliacao.py`, `scripts/avaliar.py`) | Retrieval, abstention, temporal benchmark v2, answer policy, reader (synthetic and adversarial sets), provenance integrity, corpus fidelity | Versioned baseline; CI fails if a tracked metric regresses |

## Selected results (see `docs/avaliacao/README.md`)

- Precision of returned provisions: 46.5% → 57.6% relevant (61.4% estimated out of sample), with the gold
  provision kept in the top 3 in 100% of the 86 questions.
- Temporal benchmark v2: correct version first 60.9% → 100% (current questions) and 52.2% → 95.7%
  (questions about 2006; 100% counting declared uncertainty).
- Out-of-scope questions protected by abstention or a caveat: 16/26 → 23/26.
- Reader adversarial set: 29/104 → 182/182 checks over 31 synthetic documents (14 added from an independent
  adversarial review); a dense 300-page PDF analysed in 3.5 s (was 18.6 s); small hostile uploads no longer
  exhaust CPU or memory.
- Monitor: real-page simulation over the 34 sources shows no spurious change; two genuinely repealed
  laws are flagged as total repeal with the correct repealing statute.
- Accessibility: 0 WCAG 2.1 A/AA violations in automated (axe) checks across all pages and both themes.

## Engineering practices

- Audit first, then fixes with regression tests and before/after measurements; an independent
  adversarial review of each cycle (16 monitor and 14 reader findings, all fixed).
- Security and privacy: login lockout per account and network, PBKDF2 600k with rehash, audit trail
  without personal data, request-body limit, automatic retention, data export, CSP. Technical controls
  are not a claim of LGPD compliance.
- CI on Python 3.10 and 3.13 (ruff, mypy, pytest, evaluation gate, corpus integrity, pip-audit) and a
  Next.js type check and build. The monitor workflow runs on weekdays (enabled by the maintainer on
  23 Oct 2026) on an ephemeral runner; results come back as artifacts for human review.

## Known limits

No human legal review yet (28 content reviews are pending). Official text comes from the Planalto
consolidated pages, not the Official Gazette. Gold standards and test sets were written by the project;
policy rules were tuned on the same sets they are measured on. The reader was not validated on real
case files and does no OCR. LLM output quality and user comprehension were not measured. This is legal
information, not legal advice, and not a substitute for a lawyer or the Public Defender's Office.
