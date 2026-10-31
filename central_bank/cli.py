import argparse
from decimal import Decimal
from central_bank.engine import Engine, BANK


class Cli:
    def __init__(self, path: str, get_time, check_user):
        self.engine = Engine(path, get_time, check_user)
        self.parser = create_parser()

    def run(self, user: str, args: list[str]) -> dict[str, str]:
        try:
            parsed_args = self.parser.parse_args(args)
            return parsed_args.func(parsed_args, self.engine, user)
        except Exception as e:
            return {user: str(e)}


def notify(actor: str, actor_message: str, *others: tuple[str, str]) -> dict[str, str]:
    messages = {actor: actor_message}
    for player, message in others:
        if player != actor:
            messages[player] = message
    return messages


def handle_send(args, engine: Engine, user: str):
    engine.send_currency(args.amount, user, args.recipient)
    return notify(
        user, f"Sent {args.amount} to {args.recipient}.",
        (args.recipient, f"{user} sent you {args.amount}."),
    )


def handle_repay(args, engine: Engine, user: str):
    owed = engine.repay_loan(args.amount, user, args.recipient)
    return notify(
        user, f"Repaid {owed} to {args.recipient}.",
        (args.recipient, f"{user} repaid {owed}."),
    )


def handle_borrow(args, engine: Engine, user: str):
    interest = args.interest / 100
    engine.request_borrow(args.amount, interest, user)
    if args.amount == 0:
        return {"*": f"{user} doesn't want to borrow anymore"}
    return {
        "*": f"{user} wants to borrow {args.amount} with {args.interest}% interest",
    }


def handle_lend(args, engine: Engine, user: str):
    request = engine.lend_currency(user, args.borrower)
    interest = request.interest * 100
    return notify(
        user, f"Lent {request.amount} to {args.borrower} at {interest}% interest.",
        (args.borrower,
         f"{user} lent you {request.amount} at {interest}% interest."),
    )


def handle_borrows(args, engine: Engine, user: str):
    lines = ["Borrows"]
    for name, request in engine.borrows.items():
        lines.append(
            f"{name} {request.amount} at {request.interest * 100}%")
    return {user: "\n".join(lines)}


def handle_issue(args, engine: Engine, user: str):
    if user != BANK:
        return {user: "You are not authorized to issue currency."}
    interest = args.interest / 100
    engine.issue_currency(args.amount, interest)
    return {user: f"Issued {args.amount} at {args.interest}% interest."}


def handle_send_loan(args, engine: Engine, user: str):
    interest = args.interest / 100
    engine.send_loan(args.amount, interest, user,
                     args.borrower, args.recipient)
    return notify(
        user,
        f"Sent {args.amount} to {args.recipient} from {args.borrower} at {args.interest}% interest.",
        (args.recipient,
         f"{user} sent you {args.amount} from {args.borrower} at {args.interest}% interest."),
        (args.borrower,
         f"{user} sent {args.amount} of your loan at {args.interest}% interest to {args.recipient}."),
    )


def format_amount(value: Decimal, width=10, decimals=2) -> str:
    return f"{value:{width}.{decimals}f}".replace(" ", ". ")


def format_interest(value: Decimal) -> str:
    return format_amount(value * 100, 4, 2) + "%"


def handle_ledger(args, engine: Engine, user: str):
    assets = engine.dal.list_assets(user)
    liabilities = engine.dal.list_liabilities(user)

    lines = ["Assets"]
    equity = 0
    for amount, borrower, type, interest in assets:
        lines.append(
            f"+ {format_amount(amount)} {type} {format_interest(interest)} {borrower}")
        equity += amount
    lines.append("Liabilities")
    for amount, holder, type, interest in liabilities:
        lines.append(
            f"- {format_amount(amount)} {type} {format_interest(interest)} {holder}")
        equity -= amount
    lines.append("Equity")
    lines.append(f"= {format_amount(equity)}")

    return {user: "\n".join(lines)}


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="bank", exit_on_error=False)
    sub = parser.add_subparsers(dest="command", required=True)

    ledger = sub.add_parser("ledger", exit_on_error=False)
    ledger.set_defaults(func=handle_ledger)

    send = sub.add_parser("send", exit_on_error=False)
    send.add_argument("recipient", type=str)
    send.add_argument("amount", type=int)
    send.set_defaults(func=handle_send)

    repay = sub.add_parser("repay", exit_on_error=False)
    repay.add_argument("recipient", type=str)
    repay.add_argument("amount", type=int)
    repay.set_defaults(func=handle_repay)

    borrow = sub.add_parser("borrow", exit_on_error=False)
    borrow.add_argument("amount", type=int)
    borrow.add_argument("interest", type=float)
    borrow.set_defaults(func=handle_borrow)

    borrows = sub.add_parser("borrows", exit_on_error=False)
    borrows.set_defaults(func=handle_borrows)

    lend = sub.add_parser("lend", exit_on_error=False)
    lend.add_argument("borrower", type=str)
    lend.set_defaults(func=handle_lend)

    issue = sub.add_parser("issue", exit_on_error=False)
    issue.add_argument("amount", type=int)
    issue.add_argument("interest", type=float)
    issue.set_defaults(func=handle_issue)

    send_loan = sub.add_parser("send_loan", exit_on_error=False)
    send_loan.add_argument("recipient", type=str)
    send_loan.add_argument("amount", type=int)
    send_loan.add_argument("interest", type=float)
    send_loan.add_argument("borrower", type=str)
    send_loan.set_defaults(func=handle_send_loan)

    return parser
