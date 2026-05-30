#!/usr/bin/env python3
"""
Batch copy files from V1 and Legacy Source to V2.
Run this once to set up V2 project structure.
"""
import shutil, os

V2 = r"D:\工作相关\自动化\Research\V2"
V1 = r"D:\工作相关\自动化\Research\V1"
SOURCE_LEGACY = r"D:\AI\Research 2.0\YMOS\YMOS"

def copy_tree(src, dst):
    os.makedirs(dst, exist_ok=True)
    for item in os.listdir(src):
        s = os.path.join(src, item)
        d = os.path.join(dst, item)
        if os.path.isdir(s):
            copy_tree(s, d)
        else:
            shutil.copy2(s, d)
    print(f"  ✅ {src} -> {dst}")

copies = [
    # YMOS Skills (P1-P15)
    (os.path.join(SOURCE_LEGACY, "YM-TIB-SKILL", "SKILL.md"), os.path.join(V2, "Skills", "SKILL.md")),
    # V1 Memory Layer
    (os.path.join(V1, "Memory_Layer", "Investment_Persona.md"), os.path.join(V2, "Memory_Layer", "Investment_Persona.md")),
    (os.path.join(V1, "Memory_Layer", "Workflow_Rules.md"), os.path.join(V2, "Memory_Layer", "Workflow_Rules.md")),
    # V1 Feedback Loop
    (os.path.join(V1, "Feedback_Loop", "Counter_Argument.md"), os.path.join(V2, "Feedback_Loop", "Counter_Argument.md")),
]

trees = [
    # Core references
    (os.path.join(SOURCE_LEGACY, "YM-TIB-SKILL", "references"), os.path.join(V2, "Skills", "references")),
    # V1 Templates
    (os.path.join(V1, "Workflow_Layer", "Templates"), os.path.join(V2, "Templates")),
    # V1 Memory scripts
    (os.path.join(V1, "Memory_Layer", "scripts"), os.path.join(V2, "Memory_Layer", "scripts")),
    # V1 Knowledge Base
    (os.path.join(V1, "Memory_Layer", "Knowledge_Base"), os.path.join(V2, "Memory_Layer", "Knowledge_Base")),
    # V1 Reference Styles
    (os.path.join(V1, "Memory_Layer", "Reference_Styles"), os.path.join(V2, "Memory_Layer", "Reference_Styles")),
    # Core Config (Portfolio/Status/Preferences)
    (os.path.join(SOURCE_LEGACY, "OpenClaw", " 我的持仓与关注点和投资偏好"), os.path.join(V2, "Config")),
]

print("=== Copying individual files ===")
for src, dst in copies:
    if os.path.exists(src):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        print(f"  ✅ {os.path.basename(src)}")
    else:
        print(f"  ❌ Not found: {src}")

print("\n=== Copying directory trees ===")
for src, dst in trees:
    if os.path.exists(src):
        copy_tree(src, dst)
    else:
        print(f"  ❌ Not found: {src}")

print("\n=== Done! ===")
