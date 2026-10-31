from dataclasses import dataclass
from decimal import Decimal
from central_bank.dal import Dal
from central_bank.exceptions import (
    InsufficientFundsException,
    InvalidAmountException,
    InvalidInterestRateException,
    InvalidUserException,
    NoBorrowRequestException,
)


BANK = "Bank"
CASH = "CASH"
LOAN = "LOAN"


@dataclass
class Borrow:
    amount: Decimal
    interest: Decimal


class Engine:
    def __init__(self, path: str, get_time, check_user):
        self.dal = Dal(path, get_time)
        self.check_user = check_user
        self.borrows: dict[str, Borrow] = {}

    def require_user(self, name: str) -> bool:
        if name == BANK or self.check_user(name) or self.known_user(name):
            return True
        raise InvalidUserException(name)

    def known_user(self, name: str) -> bool:
        sql = "select 1 from assets where holder=? or borrower=? limit 1"
        return self.dal.conn.execute(sql, (name, name)).fetchone() is not None

    def send_currency(self, amount: Decimal, sender: str, receiver: str):
        check_amount(amount)
        self.require_user(receiver)
        with self.dal.conn:
            self.send_currency_inner(amount, sender, receiver)

    def send_currency_inner(self, amount: Decimal, sender: str, receiver: str):
        check_amount(amount)
        deficit = self.dal.transfer_amount(
            amount, sender, BANK, CASH, None, receiver)

        if deficit > 0:
            raise InsufficientFundsException()

    def repay_loan(self, amount: Decimal, sender: str, receiver: str) -> Decimal:
        check_amount(amount)
        self.require_user(receiver)
        with self.dal.conn:
            deficit = self.dal.subtract_amount(
                amount, receiver, sender, LOAN, highest_first=True)
            owed = amount - deficit
            if owed > 0:
                currency_deficit = self.dal.transfer_amount(
                    owed, sender, BANK, CASH, None, receiver)
                if currency_deficit > 0:
                    raise InsufficientFundsException()
            return owed

    def request_borrow(self, amount: Decimal, interest: Decimal, borrower: str):
        if amount == 0:
            self.borrows.pop(borrower, None)
            return
        check_amount(amount)
        check_interest(interest)
        self.borrows[borrower] = Borrow(amount, interest)

    def lend_currency(self, lender: str, borrower: str) -> Borrow:
        request = self.borrows.get(borrower)
        if request is None:
            raise NoBorrowRequestException(borrower)
        check_interest(request.interest)
        self.require_user(borrower)
        with self.dal.conn:
            self.send_currency_inner(request.amount, lender, borrower)
            self.dal.add_amount(
                request.amount, lender, borrower, LOAN, request.interest)
        del self.borrows[borrower]
        return request

    def send_loan(self, amount: Decimal, interest: Decimal, lender: str, borrower: str, receiver: str):
        check_amount(amount)
        check_interest(interest)
        self.require_user(borrower)
        self.require_user(receiver)
        with self.dal.conn:
            deficit = self.dal.transfer_amount(
                amount, lender, borrower, LOAN, interest, receiver)

            if deficit > 0:
                raise InsufficientFundsException()

    def issue_currency(self, amount: Decimal, interest: Decimal):
        check_amount(amount)
        check_interest(interest)
        with self.dal.conn:
            self.dal.add_amount(amount, BANK, BANK, CASH, interest)

def check_amount(amount: Decimal):
    if amount > 0:
        return
    raise InvalidAmountException()


def check_interest(interest: Decimal):
    if -0.1 < interest < 0.1:
        return
    raise InvalidInterestRateException()
