"""Small REPL with injectable terminal I/O for offline testing."""

import argparse
import json
from pathlib import Path

from conversation.environment import load_env
from conversation.interactive.session import InteractiveSession


QUOTA_WARNING = "Gemini mode enabled. Messages that require LLM may consume API quota."
HELP = """Commands:
  /state                 Show current state
  /reset                 New session; retain collected samples
  /provider [rule|mock|gemini|openai]
  /results [demo|path]    Show or load previous results (JSON array)
  /accept                Accept last AI prediction
  /reject                Reject last sample (does not undo state)
  /correct               Correct last update and rebuild state
  /history               Brief history of current session
  /save                  Retry save and show JSONL path
  /export                Export reviewed samples collected in this run
  /help
  /exit"""


def run_repl(session: InteractiveSession, read=input, write=print) -> None:
    def pretty(value):
        return json.dumps(session.logger.safe(value), ensure_ascii=False, indent=2, allow_nan=False)

    def provider_notice():
        write(f"Provider: {session.provider}")
        if session.provider == "gemini":
            write(QUOTA_WARNING)
        elif session.provider == "openai":
            write("OpenAI mode enabled. Messages that require LLM may consume API quota.")
        elif session.provider == "mock":
            write("Mock uses empty inference; it tests orchestration, not semantic quality.")

    write("AI 2 Interactive Tester")
    provider_notice()
    write("Session: " + str(session.logger.safe(session.session_id)))
    write(HELP)
    if not session.logger.enabled:
        write("--no-save: dataset persistence and export disabled.")
    try:
        while True:
            try:
                line = read("AI2 > ").strip()
                if not line:
                    continue
                if not line.startswith("/"):
                    record = session.process(line)
                    metadata = record["metadata"]
                    sections = [
                        ("MESSAGE", record["message"]),
                        ("RULE RESULT", record["rule_result"]),
                        ("LLM", {"provider": record["provider"], "called": record["llm_called"],
                                 "error": metadata["llm_error"],
                                 "external_llm_disabled": metadata["external_llm_disabled"],
                                 "partial_result": metadata["partial_result"]}),
                        ("SLM", {key: metadata["slm_" + key] for key in
                                 (("enabled", "called", "confidence", "fallback", "error")
                                  if metadata["slm_enabled"] else ("enabled", "called"))}),
                        ("PREFERENCE UPDATE", record["preference_update"]),
                        ("NEW STATE", record["new_state"]),
                        ("LATENCY", metadata["latency"]),
                        ("USAGE", {key: metadata["usage"].get(key) for key in
                                   ("input_tokens", "output_tokens", "total_tokens")}),
                    ]
                    write("-" * 50)
                    for title, value in sections:
                        write(title + "\n" + pretty(value))
                    write("-" * 50)
                else:
                    parts = line.split(maxsplit=1)
                    command, argument = parts[0], parts[1] if len(parts) > 1 else ""
                    if argument and command not in ("/provider", "/results"):
                        raise ValueError("Unexpected command argument.")
                    if command == "/exit":
                        break
                    elif command == "/help":
                        write(HELP)
                    elif command == "/state":
                        write(pretty(session.current_state.model_dump(mode="json")))
                    elif command == "/reset":
                        session.reset()
                        write("Session reset: " + session.session_id)
                    elif command == "/provider":
                        if argument:
                            session.set_provider(argument)
                        provider_notice()
                    elif command == "/results":
                        if argument:
                            session.results(argument)
                        write(pretty([item.model_dump(mode="json") for item in session.previous_results]))
                    elif command in ("/accept", "/reject"):
                        status = "accepted" if command == "/accept" else "rejected"
                        session.label(status)
                        write("Last sample: " + status)
                    elif command == "/correct":
                        session._last()
                        write("Paste corrected PreferenceUpdate JSON; finish with a line containing only END. Ctrl+C cancels.")
                        lines = []
                        while True:
                            part = read("... ")
                            if part.strip() == "END":
                                break
                            lines.append(part)
                        session.correct("\n".join(lines))
                        write("Last sample: corrected. Current state rebuilt:\n" +
                              pretty(session.current_state.model_dump(mode="json")))
                    elif command == "/history":
                        for index, record in enumerate(session.history, 1):
                            message = str(session.logger.safe(record["message"]))
                            preview = json.dumps(message[:100] + ("..." if len(message) > 100 else ""), ensure_ascii=False)
                            write(f"{index}. {preview}\n   provider={record['provider']}  {record['label_status']}")
                        if not session.history:
                            write("No messages in this session.")
                    elif command == "/save":
                        path = session.save()
                        write(str(path) if path else "Save disabled." if not session.logger.enabled else "Save pending.")
                    elif command == "/export":
                        write("Export: " + str(session.export()))
                    else:
                        write("Unknown command. Use /help.")
                if session.save_error:
                    write(session.save_error)
            except EOFError:
                break
            except KeyboardInterrupt:
                write("\nInput cancelled. Use /exit to quit.")
            except Exception:
                # Validation/SDK/filesystem exceptions can include credentials or input.
                write("Error: invalid input or operation failed. Check JSON/schema/path and use /help.")
    finally:
        path = session.save()
        if session.save_error:
            write(session.save_error)
        elif path:
            write("Saved: " + str(path))
        write("Goodbye.")


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Interactive AI 2 testing and reviewed data collection")
    parser.add_argument("--provider", choices=("rule", "mock", "gemini", "openai"))
    parser.add_argument("--session-id")
    parser.add_argument("--no-save", action="store_true")
    args = parser.parse_args(argv)
    # Match the smoke-test setup before the session snapshots ConversationConfig.
    load_env()
    try:
        session = InteractiveSession(provider=args.provider, session_id=args.session_id,
                                     no_save=args.no_save,
                                     directory=Path(__file__).resolve().parents[3] / "data" / "ai2_interactive")
    except ValueError:
        parser.error("Invalid session configuration.")
    run_repl(session)
