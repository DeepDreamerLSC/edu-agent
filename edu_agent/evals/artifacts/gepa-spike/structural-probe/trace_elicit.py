#!/usr/bin/env python3
"""Trace where elicit template appears in conversation."""

import sys
sys.path.insert(0, ".")

from edu_agent.evals.gepa import ElicitSubject
from edu_agent.gateway import Gateway, load_registry
from edu_agent.evals.image_teaching import load_scenarios
from pathlib import Path

# Load gateway
registry = load_registry(Path("configs/models.yaml"))
gateway = Gateway(registry)

# Load one case
cases = load_scenarios(Path("edu_agent/evals/datasets/small_lecturer_image_teaching_v1.json"))
case = cases[0]

# Run with parent template
parent_template = "我们从头把思路串一遍——先说说你第一步算了什么、为什么这样算。"
subject = ElicitSubject(parent_template, gateway)
transcript = subject.run_case(case)

print("=== PARENT TEMPLATE ===")
print(f"Template: {parent_template}")
print(f"Number of turns: {len(transcript['turns'])}")
print()
for i, turn in enumerate(transcript['turns']):
    student_text = turn['student'][:50] if turn['student'] else '(empty)'
    print(f"Turn {i}:")
    print(f"  Student: {student_text}...")
    print(f"  Tutor: {turn['tutor'][:100]}...")
    if parent_template in turn['tutor']:
        print(f"  *** PARENT TEMPLATE FOUND IN THIS TURN ***")
    print()

# Run with variant template
variant_template = "这道题里有一个最关键的步骤——别的步骤错了都还能补救,就它错了整道题就歪了。你觉得是哪一步?为什么是它?如果这一步换一种做法,答案会怎么变?"
subject2 = ElicitSubject(variant_template, gateway)
transcript2 = subject2.run_case(case)

print("\n=== VARIANT TEMPLATE ===")
print(f"Template: {variant_template}")
print(f"Number of turns: {len(transcript2['turns'])}")
print()
for i, turn in enumerate(transcript2['turns']):
    student_text = turn['student'][:50] if turn['student'] else '(empty)'
    print(f"Turn {i}:")
    print(f"  Student: {student_text}...")
    print(f"  Tutor: {turn['tutor'][:100]}...")
    if variant_template in turn['tutor']:
        print(f"  *** VARIANT TEMPLATE FOUND IN THIS TURN ***")
    print()
