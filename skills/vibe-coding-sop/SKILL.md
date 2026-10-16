---
name: vibe-coding-sop
description: Execute the project-local Vibe Coding SOP when a repository has .sop/project.json or the user explicitly requests this workflow. Supports onboarding, staged implementation, evidence checks, and handover.
---

# Vibe Coding SOP

If `.sop/project.json` exists, read it and the project's agent entry file; run `python .sop/runtime/sop.py check`. Load `.sop/core/workflow.md` and only the documents relevant to the current task.

If initialization is requested, locate the distributed package containing `sop.py` and `profiles/`. Read its README and initialize the specified project with a suitable profile. If the package is unavailable, report that dependency rather than inventing an installation command.

Convert the change into observable acceptance conditions. Work in small vertical slices, maintaining interfaces and regression checks. Proceed within existing authorization. Record actual human decisions and their source; never infer approval from a generated template.

Inspect configured commands before executing `verify`. Use `check --stage L4` for delivery readiness. Read `.sop/runtime/docs/protocol.md` when filling review records or diagnosing stale evidence. Report unverified items. Generate a handover snapshot and add design reasons and next actions.
