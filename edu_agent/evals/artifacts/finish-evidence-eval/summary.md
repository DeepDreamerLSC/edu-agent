| 案例 | 期望 | 实测(final_state ×重复) | 判定 | judge 均分(/12) |
|---|---|---|---|---:|
| finish_evidence_zero_utterance | needs_review | needs_review / needs_review | PASS | 1.0 |
| finish_evidence_answer_only | needs_review | needs_review / needs_review | PASS | 1.0 |
| finish_evidence_vague_two | needs_review | needs_review / needs_review | PASS | 1.0 |
| finish_evidence_full_explanation | completed | completed / completed | PASS | 5.0 |

providers_used=['mlx', 'vision'] fallback_to=无
calls_by_role={'tutor': 18, 'judge': 8}
