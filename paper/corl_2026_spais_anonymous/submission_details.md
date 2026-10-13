# HumanRLI 2026 Submission Details

Checked against the public OpenReview submission invitation on October 13, 2026.
Nothing has been submitted by this preparation step.

Submission portal: https://openreview.net/group?id=robot-learning.org/CoRL/2026/Workshop/HumanRLI

Deadline: October 13, 2026, 2:59 p.m. Riyadh time. This is the invitation's
due date, not its later expiration/grace timestamp.

PDF: `main.pdf` in this directory. Anonymous, seven pages total; the main text
is within the eight-page limit excluding references and appendix.

## Title

Failure Containment and Executable Actions in Language-Based Multi-UAV Planning

## Keywords

physical AI safety, robot planning, failure containment, evaluation

## TL;DR

Frozen validation pipelines contain failures without executable planning; a repaired controller executes six valid variants and stops four invalid variants on two inspected development missions.

## Abstract

Language-based robot planners can produce fluent plans despite missing evidence or conflicting resources. We compare four validation-pipeline configurations on 1,420 controlled derivatives of 284 held-out MultiUAV-Plat tasks using frozen Qwen2.5-3B and 7B checkpoints. Stage-wise validation eliminated unsupported continuation on all 568 non-executable cases, but failed every one of 852 executable cases. A zero-call policy that always blocks achieved 20.0% strict success, exceeding the 7B stage-wise configuration's 16.1%, showing that containment alone does not establish useful discrimination. A post-hoc audit also found that the frozen validator rejected 43 of 249 fully instantiated upstream reference plans. A paired replay that held prompts, generations, validators, and call count fixed found no placement-only change in containment, false non-execution, or static plan fidelity. The study is therefore a negative result for the frozen pipelines: changing enforcement order alone did not recover executable planning. A separate repaired, observation-grounded closed-loop controller completed six of 15 training-split development missions under the upstream official task checker. Three missions ended with false checks, five exhausted GPU memory, and one was interrupted. A later compact-context controller with visible-request admission completed all six executable variants of two previously inspected training missions, while clarifying both missing-evidence variants and blocking both fleet-conflict variants without commands. An infrastructure-interrupted attempt was retained and restarted separately. This demonstrates paired execution and refusal in a small constructed diagnostic, not held-out competence, a causal placement advantage, or physical safety. The original failures remain reported.

## Authors And Consent

- Select the actual authors' OpenReview profiles, in the agreed order. All authors
  need profiles. Do not put "Anonymous Authors" in the form; anonymity applies
  to the uploaded manuscript.
- The required email-sharing choice says: "We authorize the sharing of all
  author emails with Program Chairs."
- The required data-release choice says: "We authorize the release of our
  submission and author names to the public in the event of acceptance."
- Confirm these choices only with the authors' authorization. The data-release
  field concerns the submission and names, not a claim that research datasets
  or code have already been released.
- Supplementary material is optional. Do not attach identifying or private
  artifacts without checking anonymity, consent and redistribution rights.
- Confirm the other venue's concurrent-submission policy before submission.

## Checks

- PDF author metadata: Anonymous Submission.
- CoRL 2026 style, anonymous review mode, HumanRLI submission footer.
- Original M1-M4 results remain unchanged.
- Paired outcomes describe two inspected training source missions, not ten
  independent missions or a held-out accuracy result.
- The a33 infrastructure interruption and a34 fresh restart remain disclosed.
- TL;DR stays within the form's 250-character limit.

Sources: https://hc-robot-learning.github.io/ and
https://api2.openreview.net/invitations?id=robot-learning.org%2FCoRL%2F2026%2FWorkshop%2FHumanRLI%2F-%2FSubmission
