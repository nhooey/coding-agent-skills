## Your preferences

!`cat "${CLAUDE_SKILL_DIR}/../<skill-name>.preferences.md" "${CLAUDE_PROJECT_DIR}/.agents/skills/<skill-name>.preferences.md" 2>/dev/null || true`

If your agent doesn't run the line above, read these files yourself if they
exist: `<skill-name>.preferences.md` next to this skill's folder, then
`.agents/skills/<skill-name>.preferences.md` in the project. A project's
file overrides the user's, and the user's overrides this skill's defaults.
