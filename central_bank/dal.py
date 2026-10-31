from decimal import Decimal
import sqlite3


class Dal:
    def __init__(self, path: str, get_time):
        sqlite3.register_adapter(Decimal, lambda val: str(val))
        sqlite3.register_converter(
            "DECIMAL", lambda val: Decimal(val.decode("utf-8")))

        self.get_time = get_time
        self.conn = sqlite3.connect(path, detect_types=sqlite3.PARSE_DECLTYPES)

        self.conn.execute("""
        create table if not exists assets(
            amount numeric not null,
            holder text not null,
            borrower text not null,
            type text not null,
            interest numeric not null,
            accrual_time numeric not null,
            primary key(holder, borrower, type, interest)
        )
        """)

    def list_assets(self, holder: str) -> list[tuple[Decimal, str, str, Decimal]]:
        sql = """
        select amount * power(1 + interest, ? - accrual_time), borrower, type, interest from assets
        where holder=? and amount > 0
        order by 1 desc
        """
        return list(self.conn.execute(sql, (self.get_time(), holder)))

    def list_liabilities(self, borrower: str) -> list[tuple[Decimal, str, str, Decimal]]:
        sql = """
        select amount * power(1 + interest, ? - accrual_time), holder, type, interest from assets
        where borrower=? and amount > 0
        order by 1 desc
        """
        return list(self.conn.execute(sql, (self.get_time(), borrower)))

    def add_amount(self, amount: Decimal,
                   holder: str, borrower: str,
                   type: str, interest: Decimal):
        sql = """
        insert into assets(amount,
            holder, borrower, 
            type, interest,
            accrual_time)
        values(?, ?, ?, ?, ?, ?)
        on conflict(holder, borrower, type, interest)
        do update set amount=excluded.amount
        + assets.amount
        * power(1 + assets.interest, excluded.accrual_time - assets.accrual_time)
        """

        self.conn.execute(sql, (amount, holder, borrower,
                                type, interest, self.get_time()))

    def subtract_amount(self, amount: Decimal,
                        holder: str, borrower: str,
                        type: str, interest: Decimal = None,
                        highest_first: bool = False) -> Decimal:
        return self.transfer_amount(
            amount, holder, borrower, type, interest, highest_first=highest_first)

    def transfer_amount(self, amount: Decimal, holder: str, borrower: str,
                        type: str, interest: Decimal = None, receiver: str = None,
                        highest_first: bool = False) -> Decimal:

        direction = "desc" if highest_first else "asc"
        sql = f"""
        select amount * power(1 + interest, ? - accrual_time), interest from assets
        where holder=? and borrower=? and type=?
        and (? is null or interest=?)
        order by interest {direction}
        """

        current_time = self.get_time()
        params = (current_time, holder, borrower, type, interest, interest)
        rows = list(self.conn.execute(sql, params))

        for row_amount, row_interest in rows:
            delta = min(row_amount, amount)
            amount -= delta
            row_amount -= delta

            sql = """
            update assets set amount=?, accrual_time=?
            where holder=? and borrower=? and type=? and interest=?
            """

            self.conn.execute(
                sql, (row_amount, current_time, holder, borrower, type, row_interest))
            if receiver is not None:
                self.add_amount(delta, receiver, borrower,
                                type, row_interest)

        return amount
