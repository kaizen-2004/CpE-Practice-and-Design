# Session Bootstrap (For New AI Sessions)

Use this when starting a new coding session so the agent loads context quickly.

## Required Read Order

1. `AGENTS.md`
2. `docs/README.md`
3. `docs/context/CURRENT_STATUS.md`
4. `README.md`

If the task is firmware/sensor transport, then also read:

5. `docs/instructions/transport/mqtt_quick_start.md`
6. `docs/instructions/transport/mqtt_deployment.md`

## Copy/Paste Prompt

```text
Read AGENTS.md first, then docs/README.md and docs/context/CURRENT_STATUS.md. Use docs/ as the primary implementation context and treat docs/archive as historical reference only. Then continue the task.
```

## Notes

- `thesis_context_pack/` is excluded from codebase reorganization and remains intact.
- The thesis objective/specific objectives/keywords in `AGENTS.md` must remain unchanged unless explicitly requested by the user.
