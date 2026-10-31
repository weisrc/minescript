class BankException(Exception):
    pass


class InsufficientFundsException(BankException):
    def __init__(self, message="Insufficient funds for the transaction."):
        super().__init__(message)


class InvalidUserException(BankException):
    def __init__(self, name, message=None):
        super().__init__(message or f"{name} is not a valid user.")


class NoBorrowRequestException(BankException):
    def __init__(self, name, message=None):
        super().__init__(message or f"{name} has not requested a loan.")


class InvalidInterestRateException(BankException):
    def __init__(self, message="Interest rate must be between -10 and 10 (exclusive)."):
        super().__init__(message)


class InvalidAmountException(BankException):
    def __init__(self, message="Amount must be greater than zero."):
        super().__init__(message)
