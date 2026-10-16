---
name: vibe-coding-sop
description: Execute the project-local Vibe Coding SOP when a repository has .sop/project.json or the user explicitly requests this workflow. Supports onboarding, staged implementation, evidence checks, and handover.
---

# Vibe Coding SOP

If `.sop/project.json` exists, read it and the project's agent entry file; run `python .sop/runtime/sop.py check`. Load `.sop/core/workflow.md` and only the documents relevant to the current task.

If initialization is requested, locate the distributed package containing `sop.py` and `profiles/`. Read its README and initialize the specified project with a suitable profile. If the package is unavailable, report that dependency rather than inventing an installation command.

Follow the workflow's stage routing into .sop/core/stages: each guide supplies steps, examples, completion criteria, and failure handling. Draft project-specific documents from observed code and user goals; ask only about material uncertainty or authority. Do not ask the user to fill every template before making progress. For a filled worked example, read .sop/runtime/examples/task-list/README.md.

Convert the change into observable acceptance conditions. Link each critical AC to a test or manual validation, define a reproducible Quickstart, and work in small vertical slices. Check direct and indirect regression impacts. Proceed within existing authorization. Record actual human decisions and their source; never infer approval from a generated template.

Inspect configured commands before executing `verify`. Read actual logs and update validation.md; a zero exit code does not establish assertion quality or business acceptance. Use `check --stage L4` for delivery readiness. Read `.sop/runtime/docs/protocol.md` when filling review records or diagnosing stale evidence. Report unverified items. Fill .sop/docs/handover.md with intent, reasons, evidence, restore limits, and next actions before generating the handover snapshot. Never fabricate test counts or approvals.
