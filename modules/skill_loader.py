import os

SKILLS_DIR = os.path.join(os.path.dirname(__file__), "..", "skills")


def load_skill(skill_name: str) -> str:
    """Load a skill's SKILL.md content, stripping YAML frontmatter."""
    path = os.path.join(SKILLS_DIR, skill_name, "SKILL.md")
    with open(path) as f:
        raw = f.read()
    if raw.startswith("---"):
        raw = raw.split("---", 2)[2]
    return raw.strip()


def load_skills(*skill_names: str) -> str:
    """Load multiple skills and combine them into a single context block."""
    sections = []
    for name in skill_names:
        content = load_skill(name)
        sections.append(f"=== SKILL: {name.upper().replace('-', ' ')} ===\n\n{content}")
    return "\n\n".join(sections)
