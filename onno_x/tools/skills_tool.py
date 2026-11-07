from onno_x.skills import list_skills


def search_skills(query: str = "") -> str:
    """Search for skills matching a keyword or category."""
    skills = list_skills()
    if not skills:
        return "No skills currently installed."
    q = query.lower().strip()
    if not q:
        sample = list(skills.keys())[:25]
        return f"{len(skills)} skills available. Samples: " + ", ".join(sample) + " (use search_skills with keyword)"

    matches = []
    for k, v in skills.items():
        if q in k.lower() or q in v.description.lower():
            desc = v.description.strip().replace("\n", " ")
            if len(desc) > 90:
                desc = desc[:87] + "..."
            matches.append(f"- {k}: {desc}")

    if not matches:
        return f"No skills found matching '{query}'."
    return f"Found {len(matches)} skill(s):\n" + "\n".join(matches[:15])


def load_skill(skill_name: str) -> str:
    """Load instructions and workflow defined inside a skill."""
    skills = list_skills()
    if skill_name not in skills:
        matches = [s for s in skills if skill_name.lower() in s.lower()][:10]
        suggest = ", ".join(matches) if matches else f"{len(skills)} total skills available"
        return f"Error: Skill '{skill_name}' not found. Closest matches: {suggest}"

    skill = skills[skill_name]
    return f"--- Skill: {skill.name} [{skill.scope}] ---\n{skill.content}"
