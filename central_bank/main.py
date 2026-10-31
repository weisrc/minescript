import sys
from decimal import Decimal
from central_bank.engine import BANK
from central_bank.cli import Cli
import re
import shlex
import system.lib.minescript as m


msg_re = re.compile(r"^<([a-zA-Z0-9_]{3,16})>\s(.*)")
whisper_re = re.compile(
    r"^([a-zA-Z0-9_]{3,16})\swhispers\sto\syou:\s(.*)", re.IGNORECASE)


ADMIN = ("weisway",)


def command_user(sender: str, central_on: bool) -> str:
    if central_on and sender in ADMIN:
        return BANK
    return sender


def user_online(name: str) -> bool:
    return len(m.players(name=f"^{re.escape(name)}$")) > 0


def main():
    file = sys.argv[1] if len(sys.argv) > 1 else ":memory:"
    cli = Cli(
        file,
        lambda: Decimal(m.world_info().game_ticks) / 72000,
        user_online,
    )
    is_central_on = False
    m.chat(f"Bank is running using {file}. Type $help.")

    with m.EventQueue() as events:
        events.register_chat_listener()

        while True:
            event = events.get()

            if event.type != m.EventType.CHAT:
                continue

            parsed = parse_message(event.message)
            if parsed is None:
                continue

            user, message = parsed

            if not message.startswith("$"):
                continue

            message = message[1:].strip()

            if user in ADMIN:
                if message == "bank on":
                    tell_user(user, "You are now the bank.")
                    is_central_on = True
                    continue

                if message == "bank off":
                    tell_user(user, "You are no longer the bank.")
                    is_central_on = False
                    continue

            actor = command_user(user, is_central_on)
            replies = cli.run(actor, shlex.split(message))

            for player, reply in replies.items():
                if player == "*":
                    for line in reply.splitlines():
                        m.chat(line)
                    continue
                if player == BANK:
                    targets = ADMIN
                elif player == actor:
                    targets = (user,)
                else:
                    targets = (player,)
                for line in reply.splitlines():
                    for target in targets:
                        tell_user(target, line)


def tell_user(user: str, message: str):
    if m.player().name == user:
        print(message)
    else:
        m.execute(f"/w {user} {message}")


def parse_message(message: str) -> tuple[str, str] | None:
    match = msg_re.match(message)
    if match:
        return match.group(1), match.group(2)

    match = whisper_re.match(message)
    if match:
        return match.group(1), match.group(2)

    return None


if __name__ == "__main__":
    main()
