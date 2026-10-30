"""Hook PreToolUse (.claude/settings.json): todo comando que suba, copie o borre en el blob pide el OK del humano.

Solo biblioteca estándar. Entrada por stdin: {"tool_name": ..., "tool_input": {"command": ...}}.
Si el comando es peligroso responde "ask"; si no, no responde nada (SPEC RF-03).
"""
import json
import re
import sys

PELIGROSOS = re.compile(
    r"src\.main\s+subir|--si\b|upload_blob|delete_blob|start_copy_from_url|set_blob|"
    r"az\s+storage\s+(blob\s+)?(upload|delete|copy|sync)|azcopy\s+(copy|sync|remove|rm)",
    re.IGNORECASE,
)


def main() -> None:
    try:
        comando = json.load(sys.stdin).get("tool_input", {}).get("command", "")
    except ValueError:
        return
    if PELIGROSOS.search(comando):
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": "El comando escribe, copia o borra en el blob: necesita el OK del humano.",
        }}))


if __name__ == "__main__":
    main()
