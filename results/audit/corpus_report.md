# Verifier audit

Known-answer solutions (gold fixes, exploits, careless trajectories): 86

| Verifier | n (wrong / right) | False-positive rate (95% CI) | False-negative rate (95% CI) | Accuracy |
|---|---|---|---|---|
| V1 | 86 (65 / 21) | 87.7% (79.2%–95.4%) | 0.0% (0.0%–0.0%) | 33.7% |
| V2 | 72 (58 / 14) | 1.7% (0.0%–5.5%) | 0.0% (0.0%–0.0%) | 98.6% |
| V3 | 86 (65 / 21) | 0.0% (0.0%–0.0%) | 0.0% (0.0%–0.0%) | 100.0% |

V1 public tests · V2 public + hidden tests · V3 multi-signal · V4 LLM judge · V5 LLM judge that runs the code (workflows: V1 goal checks, V3 goal + guard checks)

A false-positive rate rests on the wrong solutions only: about 100 are needed for a 95% interval of roughly ±10 points.
