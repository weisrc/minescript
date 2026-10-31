from decimal import Decimal
import shlex

from central_bank.cli import Cli, format_amount, format_interest
from central_bank.engine import BANK, CASH, LOAN

ALICE = "alice"
BOB = "bob"
CAROL = "carol"


class Clock:
    def __init__(self):
        self.t = Decimal(0)

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += Decimal(dt)


def new_bank(check_user=lambda _name: True):
    clock = Clock()
    return Cli(":memory:", clock, check_user), clock


def run(cli: Cli, cmd: str, user: str = "user") -> dict[str, str]:
    print(f"{user}> {cmd}")
    result = cli.run(user, shlex.split(cmd))
    for player, message in result.items():
        print(f"{player}: {message}")
    print("-----")
    return result


def expect(result: dict[str, str], text: str):
    combined = "\n".join(result.values())
    if text not in combined:
        raise SystemExit(f"expected {text!r} in:\n{result}")


def expect_text(result: str, text: str):
    if text not in result:
        raise SystemExit(f"expected {text!r} in:\n{result}")


def balance(cli: Cli, holder: str, borrower: str, type: str, interest: float) -> float:
    for amount, row_borrower, row_type, row_interest in cli.engine.dal.list_assets(holder):
        if row_borrower == borrower and row_type == type and abs(float(row_interest) - interest) < 1e-9:
            return float(amount)
    return 0.0


def expect_balance(cli: Cli, holder: str, borrower: str, type: str, interest: float, amount: float):
    got = balance(cli, holder, borrower, type, interest)
    if abs(got - amount) > 1e-4:
        raise SystemExit(
            f"{holder} -> {borrower} {type} at {interest}: expected {amount}, got {got}"
        )


def test_issue_and_send():
    cli, _ = new_bank()
    expect(run(cli, "issue 1000 2", BANK), "Issued 1000 at 2.0% interest.")
    expect(run(cli, "ledger", BANK), "CASH")
    expect(run(cli, f"send {ALICE} 100", BANK), f"Sent 100 to {ALICE}.")
    expect_balance(cli, BANK, BANK, CASH, 0.02, 900)
    expect_balance(cli, ALICE, BANK, CASH, 0.02, 100)


def test_rejects_offline_user():
    cli, _ = new_bank(lambda name: name == ALICE)
    run(cli, "issue 100 1", BANK)
    expect(run(cli, f"send {BOB} 10", BANK), f"{BOB} is not a valid user.")
    expect_balance(cli, BANK, BANK, CASH, 0.01, 100)
    expect(run(cli, f"send {ALICE} 10", BANK), f"Sent 10 to {ALICE}.")
    expect(run(cli, f"send {BANK} 5", ALICE), f"Sent 5 to {BANK}.")

    offline = set()
    cli, _ = new_bank(lambda name: name not in offline)
    run(cli, "issue 100 1", BANK)
    run(cli, f"send {BOB} 20", BANK)
    offline.add(BOB)
    offline.add(CAROL)
    expect(run(cli, f"send {BOB} 5", BANK), f"Sent 5 to {BOB}.")
    if cli.engine.require_user(BOB) is not True:
        raise SystemExit("an existing holder should be valid while offline")

    cli.engine.dal.add_amount(10, ALICE, CAROL, LOAN, 0)
    if cli.engine.require_user(CAROL) is not True:
        raise SystemExit("an existing borrower should be valid while offline")


def test_only_central_can_issue():
    cli, _ = new_bank()
    expect(run(cli, "issue 1000 2", ALICE), "You are not authorized to issue currency.")
    expect_balance(cli, BANK, BANK, CASH, 0.02, 0)


def test_interest_bounds():
    cli, _ = new_bank()
    expect(run(cli, "issue 100 1", BANK), "Issued 100 at 1.0% interest.")
    expect(run(cli, "issue 100 9", BANK), "Issued 100 at 9.0% interest.")
    expect(run(cli, "issue 100 0", BANK), "Issued 100 at 0.0% interest.")
    expect(run(cli, "issue 100 -1", BANK), "Issued 100 at -1.0% interest.")
    expect(run(cli, "issue 100 -9", BANK), "Issued 100 at -9.0% interest.")
    expect(run(cli, "issue 100 10", BANK), "Interest rate must be between -10 and 10")
    expect(run(cli, "issue 100 -10", BANK), "Interest rate must be between -10 and 10")
    expect_balance(cli, BANK, BANK, CASH, 0.01, 100)
    expect_balance(cli, BANK, BANK, CASH, 0.09, 100)
    expect_balance(cli, BANK, BANK, CASH, 0, 100)
    expect_balance(cli, BANK, BANK, CASH, -0.01, 100)
    expect_balance(cli, BANK, BANK, CASH, -0.09, 100)


def test_insufficient_funds_leaves_balances():
    cli, _ = new_bank()
    run(cli, "issue 100 1", BANK)
    run(cli, f"send {ALICE} 100", BANK)
    expect(run(cli, f"send {BOB} 101", ALICE), "Insufficient funds")
    expect_balance(cli, ALICE, BANK, CASH, 0.01, 100)
    expect_balance(cli, BOB, BANK, CASH, 0.01, 0)


def test_spend_lowest_interest_first():
    cli, _ = new_bank()
    run(cli, "issue 100 1", BANK)
    run(cli, "issue 100 9", BANK)
    expect(run(cli, f"send {ALICE} 150", BANK), f"Sent 150 to {ALICE}.")
    expect_balance(cli, BANK, BANK, CASH, 0.01, 0)
    expect_balance(cli, BANK, BANK, CASH, 0.09, 50)
    expect_balance(cli, ALICE, BANK, CASH, 0.01, 100)
    expect_balance(cli, ALICE, BANK, CASH, 0.09, 50)


def test_same_rate_issues_stack():
    cli, _ = new_bank()
    run(cli, "issue 100 5", BANK)
    run(cli, "issue 40 5", BANK)
    expect_balance(cli, BANK, BANK, CASH, 0.05, 140)


def test_borrow_requests():
    cli, _ = new_bank()
    run(cli, "issue 100 1", BANK)
    run(cli, f"send {ALICE} 100", BANK)
    expect(run(cli, f"lend {BOB}", ALICE), f"{BOB} has not requested a loan.")

    requested = run(cli, "borrow 40 5", BOB)
    expect(requested, f"{BOB} wants to borrow 40 with 5.0% interest")
    if set(requested) != {"*"}:
        raise SystemExit(f"borrow should notify everyone:\n{requested}")
    expect(run(cli, "borrow 15 8", CAROL), f"{CAROL} wants to borrow 15 with 8.0% interest")
    listed = run(cli, "borrows", ALICE)
    if set(listed) != {ALICE}:
        raise SystemExit(f"borrows should be sent only to the caller:\n{listed}")
    expect(listed, f"{BOB} 40 at 5.0%")
    expect(listed, f"{CAROL} 15 at 8.0%")

    expect(run(cli, f"lend {BOB}", ALICE), f"Lent 40 to {BOB} at 5.0% interest.")
    listed = run(cli, "borrows", ALICE)
    expect(listed, f"{CAROL} 15 at 8.0%")
    if BOB in listed[ALICE]:
        raise SystemExit(f"fulfilled borrow should be removed:\n{listed}")

    cleared = run(cli, "borrow 0 0", CAROL)
    expect(cleared, f"{CAROL} doesn't want to borrow anymore")
    if set(cleared) != {"*"}:
        raise SystemExit(f"clearing a borrow should be sent to everyone:\n{cleared}")
    listed = run(cli, "borrows", ALICE)
    if CAROL in listed[ALICE]:
        raise SystemExit(f"zero borrow should clear the request:\n{listed}")
    expect(run(cli, f"lend {CAROL}", ALICE), f"{CAROL} has not requested a loan.")


def test_lend_and_repay():
    cli, _ = new_bank()
    run(cli, "issue 100 1", BANK)
    run(cli, f"send {ALICE} 100", BANK)
    run(cli, "borrow 40 5", BOB)
    expect(run(cli, f"lend {BOB}", ALICE), f"Lent 40 to {BOB} at 5.0% interest.")
    expect_balance(cli, ALICE, BANK, CASH, 0.01, 60)
    expect_balance(cli, BOB, BANK, CASH, 0.01, 40)
    expect_balance(cli, ALICE, BOB, LOAN, 0.05, 40)

    expect(run(cli, f"send {ALICE} 15", BOB), f"Sent 15 to {ALICE}.")
    expect_balance(cli, ALICE, BOB, LOAN, 0.05, 40)
    expect_balance(cli, ALICE, BANK, CASH, 0.01, 75)
    expect_balance(cli, BOB, BANK, CASH, 0.01, 25)

    expect(run(cli, f"repay {ALICE} 15", BOB), f"Repaid 15")
    expect_balance(cli, ALICE, BOB, LOAN, 0.05, 25)
    expect_balance(cli, ALICE, BANK, CASH, 0.01, 90)
    expect_balance(cli, BOB, BANK, CASH, 0.01, 10)

    expect(run(cli, f"repay {ALICE} 100", BOB), "Insufficient funds")
    expect_balance(cli, ALICE, BOB, LOAN, 0.05, 25)
    expect_balance(cli, BOB, BANK, CASH, 0.01, 10)

    expect(run(cli, f"repay {ALICE} 10", BOB), "Repaid 10")
    expect_balance(cli, ALICE, BOB, LOAN, 0.05, 15)
    expect_balance(cli, BOB, BANK, CASH, 0.01, 0)

    run(cli, f"send {BOB} 30", ALICE)
    expect(run(cli, f"repay {ALICE} 100", BOB), "Repaid 15")
    expect_balance(cli, ALICE, BOB, LOAN, 0.05, 0)
    expect_balance(cli, BOB, BANK, CASH, 0.01, 15)
    expect_balance(cli, ALICE, BANK, CASH, 0.01, 85)


def test_lend_without_funds():
    cli, _ = new_bank()
    run(cli, "issue 100 1", BANK)
    run(cli, f"send {ALICE} 100", BANK)
    run(cli, "borrow 500 5", BOB)
    expect(run(cli, f"lend {BOB}", ALICE), "Insufficient funds")
    expect_balance(cli, ALICE, BANK, CASH, 0.01, 100)
    expect_balance(cli, ALICE, BOB, LOAN, 0.05, 0)


def test_send_loan():
    cli, _ = new_bank()
    run(cli, "issue 100 1", BANK)
    run(cli, f"send {ALICE} 100", BANK)
    run(cli, "borrow 40 5", BOB)
    run(cli, f"lend {BOB}", ALICE)
    run(cli, "borrow 10 8", BOB)
    run(cli, f"lend {BOB}", ALICE)

    expect(
        run(cli, f"send_loan {CAROL} 10 5 {BOB}", ALICE),
        f"Sent 10 to {CAROL} from {BOB} at 5.0% interest.",
    )
    expect_balance(cli, ALICE, BOB, LOAN, 0.05, 30)
    expect_balance(cli, CAROL, BOB, LOAN, 0.05, 10)
    expect_balance(cli, ALICE, BOB, LOAN, 0.08, 10)

    expect(run(cli, f"send_loan {CAROL} 10 9 {BOB}", ALICE), "Insufficient funds")
    expect(run(cli, f"send_loan {CAROL} 50 5 {BOB}", ALICE), "Insufficient funds")
    expect_balance(cli, ALICE, BOB, LOAN, 0.05, 30)
    expect_balance(cli, CAROL, BOB, LOAN, 0.05, 10)


def test_central_bank_sees_every_currency_liability():
    cli, _ = new_bank()
    run(cli, "issue 1000 1", BANK)
    run(cli, f"send {ALICE} 300", BANK)
    run(cli, f"send {BOB} 200", BANK)
    run(cli, "borrow 50 5", BOB)
    run(cli, f"lend {BOB}", ALICE)

    central = run(cli, "ledger", BANK)[BANK]
    expect_text(central, f"+ {format_amount(500)} CASH {format_interest(0.01)} {BANK}")
    expect_text(central, f"- {format_amount(500)} CASH {format_interest(0.01)} {BANK}")
    expect_text(central, f"- {format_amount(250)} CASH {format_interest(0.01)} {ALICE}")
    expect_text(central, f"- {format_amount(250)} CASH {format_interest(0.01)} {BOB}")
    expect_text(central, f"= {format_amount(-500)}")

    alice = run(cli, "ledger", ALICE)[ALICE]
    expect_text(alice, f"+ {format_amount(250)} CASH {format_interest(0.01)} {BANK}")
    expect_text(alice, f"+ {format_amount(50)} LOAN {format_interest(0.05)} {BOB}")
    expect_text(alice, f"= {format_amount(300)}")
    if any(line.startswith("- ") for line in alice.split("Liabilities", 1)[1].splitlines()):
        raise SystemExit(f"alice should have no liabilities:\n{alice}")

    bob = run(cli, "ledger", BOB)[BOB]
    expect_text(bob, f"+ {format_amount(250)} CASH {format_interest(0.01)} {BANK}")
    expect_text(bob, f"- {format_amount(50)} LOAN {format_interest(0.05)} {ALICE}")
    expect_text(bob, f"= {format_amount(200)}")
    if any(line.startswith("- ") and BANK in line for line in bob.splitlines()):
        raise SystemExit(f"bob's liabilities list the central bank:\n{bob}")


def test_repay_highest_interest_first():
    cli, _ = new_bank()
    run(cli, "issue 100 1", BANK)
    run(cli, f"send {ALICE} 100", BANK)
    run(cli, "borrow 30 5", BOB)
    run(cli, f"lend {BOB}", ALICE)
    run(cli, "borrow 20 8", BOB)
    run(cli, f"lend {BOB}", ALICE)

    expect(run(cli, f"repay {ALICE} 25", BOB), "Repaid 25")
    expect_balance(cli, ALICE, BOB, LOAN, 0.08, 0)
    expect_balance(cli, ALICE, BOB, LOAN, 0.05, 25)
    expect_balance(cli, BOB, BANK, CASH, 0.01, 25)


def test_interest_accrues_with_time():
    cli, clock = new_bank()
    run(cli, "issue 100 5", BANK)
    clock.advance(2)
    expect_balance(cli, BANK, BANK, CASH, 0.05, 110.25)
    expect(run(cli, f"send {ALICE} 110", BANK), f"Sent 110 to {ALICE}.")
    expect_balance(cli, BANK, BANK, CASH, 0.05, 0.25)
    expect_balance(cli, ALICE, BANK, CASH, 0.05, 110)
    clock.advance(1)
    expect_balance(cli, ALICE, BANK, CASH, 0.05, 115.5)


def test_invalid_amount():
    cli, _ = new_bank()
    run(cli, "issue 100 1", BANK)
    run(cli, f"send {ALICE} 100", BANK)
    for command, user in (
        ("issue 0 1", BANK),
        ("issue -5 1", BANK),
        (f"send {BOB} 0", ALICE),
        (f"send {BOB} -1", ALICE),
        (f"repay {ALICE} 0", BOB),
        (f"repay {ALICE} -1", BOB),
        ("borrow -10 5", BOB),
        (f"send_loan {CAROL} 0 5 {BOB}", ALICE),
        (f"send_loan {CAROL} -1 5 {BOB}", ALICE),
    ):
        expect(run(cli, command, user), "Amount must be greater than zero.")
    expect_balance(cli, ALICE, BANK, CASH, 0.01, 100)
    expect(run(cli, "borrow 0 0", BOB), f"{BOB} doesn't want to borrow anymore")


if __name__ == "__main__":
    test_issue_and_send()
    test_rejects_offline_user()
    test_only_central_can_issue()
    test_interest_bounds()
    test_invalid_amount()
    test_insufficient_funds_leaves_balances()
    test_spend_lowest_interest_first()
    test_same_rate_issues_stack()
    test_borrow_requests()
    test_lend_and_repay()
    test_repay_highest_interest_first()
    test_lend_without_funds()
    test_send_loan()
    test_central_bank_sees_every_currency_liability()
    test_interest_accrues_with_time()
    print("all tests passed")
