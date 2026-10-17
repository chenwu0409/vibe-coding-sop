---
name: vibe-coding-sop
description: Execute the project-local Vibe Coding SOP when a repository has .sop/project.json or the user explicitly requests this workflow. Supports onboarding, staged implementation, evidence checks, and handover.
---

# Vibe Coding SOP

If `.sop/project.json` exists, read it and the project's agent entry file; run `python .sop/runtime/sop.py check` before inspecting implementation details or coding, confirm the project has a local Git baseline, and treat the output as the task's starting baseline. Load `.sop/core/workflow.md` and only the documents relevant to the current task.

If initialization is requested, locate the distributed package containing `sop.py` and `profiles/`. Read its README and initialize the specified project with a suitable profile. If the package is unavailable, report that dependency rather than inventing an installation command.

Follow the workflow's stage routing into .sop/core/stages: each guide supplies steps, examples, completion criteria, and failure handling. Draft project-specific documents from observed code and user goals; ask only about material uncertainty or authority. Do not ask the user to fill every template before making progress. For a filled worked example, read .sop/runtime/examples/task-list/README.md.

For projects targeting a platform runtime (mini-program, browser, mobile, desktop, plugin, game engine, or similar), identify the platform configuration, actual source root, scan/package rules, reserved names, and real compile/package entry during design (write it in design.md for M/L or plan.md for S). Execute that platform check after test/build when the tool is available; if it is unavailable, record the exact ENV blocker and mark the result unverified. Node/Python tests, syntax checks, or mocks do not establish platform compilation.

Convert the change into observable acceptance conditions. Link each critical AC to a test or manual validation, define a reproducible Quickstart, and work in small vertical slices. Maintain `.sop/tasks.json` as the machine-readable task ledger: every task links ACs, code, tests, evidence, and implementation/verification status. After every task or stage, update the ledger and affected plan/development/validation/risk documents, run `python .sop/runtime/sop.py sync`, run the current-stage check, and create a named local Git commit. A task is not done until its tests and evidence exist and its verification status is `passed`. Check direct and indirect regression impacts. Proceed within existing authorization. Record actual human decisions and their source; never infer approval from a generated template.

Before closing L3/L4 work, run `python .sop/runtime/sop.py audit --stage <stage>` to catch missing ACs or declared code/test paths and, when enabled, incomplete platform verification records. Audit is a consistency check, not a test or approval.

When requirements, acceptance conditions, constitution, design, plan, platform boundary, project configuration, shared contract, source, or task status changes, rerun `check` immediately; the sync record also becomes stale until `sync` is run after the affected materials are updated. The tool's `scope_sha256` is the freshness boundary: affected approvals are stale until the real reviewer re-confirms the new scope. Independent exploration may continue while approval is pending, but dependent implementation is not delivery-ready. For UI, gestures, defaults, and other interaction semantics, record the behavior in AC/design and add a real manual or platform-level check; pure logic tests cover only the logic seam.

Reassess risk whenever the task touches health, financial, identity, child, or location data; permissions; cloud sync or external APIs; notifications/payments/bulk deletion; irreversible migrations; or real-user release. Local-only storage is not by itself a reason to mark sensitive data normal. Before delivery, synchronize plan/development/validation with the current source, advance `state.json.target_stage` to L4, preserve a local Git recovery baseline, and complete handover.md.

Inspect configured commands before executing `verify`. Read actual logs and update validation.md; a zero exit code does not establish assertion quality or business acceptance. For delivery, execute `verify`, perform the real target-platform compile/package/import check when applicable, update `.sop/tasks.json`, run `audit --stage L4`, then run `sync` and `check --stage L4` as the final gate. Read `.sop/runtime/docs/protocol.md` when filling review records or diagnosing stale evidence. Report unverified items. Fill .sop/docs/handover.md with intent, reasons, evidence, restore limits, and next actions before generating the handover snapshot. Never fabricate test counts or approvals.
