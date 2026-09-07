import os
import re
from pathlib import Path

# Paths
BASE_DIR = Path(r"C:\Users\Misha\Documents\metacritic")
BRAIN_DIR = Path(r"C:\Users\Misha\.gemini\antigravity\brain")
AI_DIR = BASE_DIR / "ai"
AI_DIR.mkdir(exist_ok=True)

METACRITIC_STAGES = [
    ("stage_1_to_4", "0a71d54b-d452-4f4f-a184-b8916b331bc4"),
    ("stage_5", "f6507818-4114-4859-a9c8-4e51e9d3a393"),
    ("stage_6", "0c4d18da-1f99-4c40-b744-4ab881af4b6c"),
    ("stage_7", "a5fcc80c-c553-4f2b-b448-608e3fb8d5a8"),
]

# Extract secrets from .env if present
env_secrets = []
env_file = BASE_DIR / ".env"
if env_file.exists():
    for line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            v = v.strip().strip("'\"")
            if any(s in k.upper() for s in ["KEY", "TOKEN", "SECRET"]) and len(v) > 8:
                env_secrets.append(v)

# Sanitization regexes
SANITIZERS = [
    (re.compile(r"AIzaSy[A-Za-z0-9_-]{30,}"), "[REDACTED_YOUTUBE_API_KEY]"),
    (re.compile(r"sk-or-v1-[A-Za-z0-9]{30,}"), "[REDACTED_OPENROUTER_API_KEY]"),
    (re.compile(r"sk-[A-Za-z0-9]{30,}"), "[REDACTED_OPENAI_API_KEY]"),
    (re.compile(r"gho_[A-Za-z0-9]{25,}"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"Bearer\s+[A-Za-z0-9_.-]{20,}"), "Bearer [REDACTED_BEARER_TOKEN]"),
]

for sec in env_secrets:
    SANITIZERS.append((re.compile(re.escape(sec)), "[REDACTED_SECRET]"))

def sanitize(text: str) -> str:
    for pat, rep in SANITIZERS:
        text = pat.sub(rep, text)
    return text

unified_path = AI_DIR / "conversation.jsonl"
total_lines = 0

with open(unified_path, "w", encoding="utf-8") as out_unified:
    for label, conv_id in METACRITIC_STAGES:
        log_file = BRAIN_DIR / conv_id / ".system_generated" / "logs" / "transcript.jsonl"
        stage_file = AI_DIR / f"{label}_transcript.jsonl"

        if not log_file.exists():
            print(f"Warning: {log_file} not found, skipping")
            continue

        stage_lines = 0
        with open(log_file, "r", encoding="utf-8", errors="ignore") as in_f, open(
            stage_file, "w", encoding="utf-8"
        ) as out_stage:
            for line in in_f:
                clean_line = sanitize(line)
                out_stage.write(clean_line)
                out_unified.write(clean_line)
                stage_lines += 1
                total_lines += 1
        print(f"Exported {label}: {stage_lines} lines -> {stage_file.name}")

# Also extract the dedicated cover hotfix slice
stage7_log = BRAIN_DIR / "a5fcc80c-c553-4f2b-b448-608e3fb8d5a8" / ".system_generated" / "logs" / "transcript.jsonl"
hotfix_file = AI_DIR / "stage_7_cover_hotfix_transcript.jsonl"
if stage7_log.exists():
    hotfix_lines = 0
    with open(stage7_log, "r", encoding="utf-8", errors="ignore") as in_f, open(
        hotfix_file, "w", encoding="utf-8"
    ) as out_hf:
        for idx, line in enumerate(in_f, start=1):
            if idx >= 960:
                out_hf.write(sanitize(line))
                hotfix_lines += 1
    print(f"Exported cover hotfix slice: {hotfix_lines} lines -> {hotfix_file.name}")

print(f"Total unified lines written to {unified_path.name}: {total_lines}")

# Verification check
print("Running verification scan for unredacted secrets...")
forbidden = [
    re.compile(r"AIzaSy[A-Za-z0-9_-]{30,}"),
    re.compile(r"sk-or-v1-[A-Za-z0-9]{30,}"),
    re.compile(r"gho_[A-Za-z0-9]{25,}"),
]

for sec in env_secrets:
    forbidden.append(re.compile(re.escape(sec)))

violations = 0
for f in AI_DIR.glob("*.jsonl"):
    with open(f, "r", encoding="utf-8") as check_f:
        for idx, line in enumerate(check_f, start=1):
            for pat in forbidden:
                if pat.search(line):
                    print(f"VIOLATION in {f.name}:{idx} matches pattern {pat.pattern[:15]}...")
                    violations += 1

if violations == 0:
    print("SUCCESS: 0 secret leaks found across all exported transcripts!")
else:
    print(f"FAILED: {violations} secret violations found!")
