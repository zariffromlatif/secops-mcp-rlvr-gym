# Verifier audit

Known-answer solutions (gold fixes, exploits, careless trajectories): 122

Every exploit and careless trajectory is checked to be rejected by V3 when it is added, so V3's rates on these solutions are 0 by construction. They show what the other verifiers miss; V3's own error rate needs human labels or new attacks (audit/hacker.py).

| Verifier | n (wrong / right) | False-positive rate (95% CI) | False-negative rate (95% CI) | Accuracy |
|---|---|---|---|---|
| V1 | 122 (97 / 25) | 80.4% (71.9%–88.2%) | 0.0% (0.0%–0.0%) | 36.1% |
| V2 | 94 (77 / 17) | 1.3% (0.0%–4.1%) | 0.0% (0.0%–0.0%) | 98.9% |
| V3 | 122 (97 / 25) | 0.0% (0.0%–0.0%) | 0.0% (0.0%–0.0%) | 100.0% |

V1 public tests · V2 public + hidden tests · V3 multi-signal · V4 LLM judge · V5 LLM judge that runs the code (workflows: V1 goal checks, V3 goal + guard checks)

A false-positive rate rests on the wrong solutions only: about 100 are needed for a 95% interval of roughly ±10 points.
