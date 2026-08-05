"""Your ledger. This is the whole assignment.

`client.py` handles the network and hands you one event at a time. You return
the journal legs it produced. Some events correctly produce none: return an
empty list, not None-as-an-accident.

One event type is implemented as a worked example. The rest raise, with the rule
from PROTOCOL.md quoted in the message, so a practice run tells you exactly what
is left rather than silently scoring zero.

Two things to get right before anything else:

  * Use `Decimal`, never `float`. Money here does not always divide evenly, and
    a float implementation will disagree with us by a cent in places you will
    struggle to find.
  * Key balances by (customer, account), not by account. At least one event
    moves money between two customers on the same account, and an
    account-level book shows nothing wrong at all.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

D = Decimal
ZERO = D("0.00")
BPS = D("0.0001")

TARIFFS = {
    "BRK-A": {
        "asset_classes": {"equity", "etf"},
        "brokerage_bps": D("20"),
        "custody_bps": D("4"),
        "broker_cost_bps": D("9"),
        "custody_cost_bps": D("2"),
        "min_fee": D("1.00"),
        "ticket": D("0.35"),
        "payable_account": "2411",
    },
    "BRK-B": {
        "asset_classes": {"equity", "bond"},
        "brokerage_bps": D("15"),
        "custody_bps": D("5"),
        "broker_cost_bps": D("8"),
        "custody_cost_bps": D("3"),
        "min_fee": D("2.50"),
        "ticket": D("3.00"),
        "payable_account": "2412",
    },
    "BRK-C": {
        "asset_classes": {"etf", "bond"},
        "brokerage_bps": D("25"),
        "custody_bps": D("3"),
        "broker_cost_bps": D("12"),
        "custody_cost_bps": D("1"),
        "min_fee": D("0.50"),
        "ticket": D("0.20"),
        "payable_account": "2413",
    },
}


def money(x: Decimal) -> Decimal:
    """2 decimal places, half away from zero. Not round(), which is half-even."""
    return x.quantize(D("0.01"), rounding=ROUND_HALF_UP)


def leg(account: str, customer_id: str, debit=ZERO, credit=ZERO) -> dict:
    return {"account": account, "customer_id": customer_id,
            "debit": str(money(D(debit))), "credit": str(money(D(credit)))}


class Book:
    def __init__(self) -> None:
        # balances[(customer_id, account)] = debit-positive balance
        self.balances: dict[tuple[str, str], Decimal] = defaultdict(lambda: ZERO)
        self.seen: set[str] = set()
        # What you have not written yet. An unimplemented handler must not stop
        # the run: the client keeps consuming and tells you the list at the end.
        self.todo: dict[str, int] = defaultdict(int)
        self.events: dict[str, dict] = {}
        self.refunded_fees: set[str] = set()
        self.withdrawals: dict[str, dict] = {}
        self.orders: dict[str, dict] = {}
        self.lots: dict[tuple[str, str], list[dict]] = defaultdict(list)

    # -----------------------------------------------------------------------
    def apply(self, ev: dict) -> list[dict]:
        """Post one event and return its legs.

        The same event_id can arrive more than once, and the server will
        deliberately re-send several hundred events partway through the run.
        Posting twice is the single most expensive mistake available here.
        """
        eid = ev["event_id"]
        if eid in self.seen:
            return []                      # already posted; nothing new happens
        self.seen.add(eid)

        handler = getattr(self, "on_" + ev["type"], None)
        if handler is None:
            self.todo[ev["type"]] += 1
            return []
        try:
            legs = handler(ev["payload"], ev) or []
        except NotImplementedError:
            # Not written yet. Submit nothing for it and carry on, so one
            # missing handler costs you that event rather than the whole run.
            self.todo[ev["type"]] += 1
            return []
        except Rejected:
            # An event you refuse still gets a submission, with no legs, and it
            # must leave your book exactly as it was.
            return []
        self._post(legs)
        self.events[eid] = ev
        return legs

    def _post(self, legs: list[dict]) -> None:
        dr = sum((D(l["debit"]) for l in legs), ZERO)
        cr = sum((D(l["credit"]) for l in legs), ZERO)

        if money(dr) != money(cr):
            raise AssertionError(f"unbalanced: dr {dr} cr {cr}")
        
        for l in legs:
            self.balances[(l["customer_id"], l["account"])] += (
                D(l["debit"]) - D(l["credit"]))

    # -- worked example -----------------------------------------------------
    def on_deposit(self, p: dict, ev: dict) -> list[dict]:
        """Cash arrives, and the firm owes the customer more.

            Dr 1100 amount        Cr 2010 amount
        """
        amount = money(D(p["amount"]))
        cid = p["customer_id"]
        return [leg("1100", cid, debit=amount),
                leg("2010", cid, credit=amount)]

    # -- yours --------------------------------------------------------------
    def on_fee_charged(self, p, ev):
        amount = money(D(p["amount"]))
        cid = p["customer_id"]

        return [
            leg("2010", cid, debit=amount),
            leg("1100", cid, credit=amount),
        ]

    def on_fee_refund(self, p, ev):
        source_id = p["refunds_source_id"]
        cid = p["customer_id"]

        source = self.events.get(source_id)

        if source is None or source.get("type") != "fee_charged":
            raise Rejected()

        if source_id in self.refunded_fees:
            raise Rejected()

        source_payload = source["payload"]

        if source_payload["customer_id"] != cid:
            raise Rejected()

        amount = money(D(source_payload["amount"]))

        self.refunded_fees.add(source_id)

        return [
            leg("1100", cid, debit=amount),
            leg("2010", cid, credit=amount),
        ]

    def on_interest_credited(self, p, ev):
        cid = p["customer_id"]

        gross = money(D(p["gross_amount"]))
        customer_share = money(D(p["customer_share"]))
        firm_share = money(gross - customer_share)

        return [
            leg("1100", cid, debit=gross),
            leg("2010", cid, credit=customer_share),
            leg("4200", cid, credit=firm_share),
        ]

    def on_transfer_between_customers(self, p, ev):
        from_cid = p["from_customer_id"]
        to_cid = p["to_customer_id"]
        amount = money(D(p["amount"]))

        return [
            leg("2010", from_cid, debit=amount),
            leg("2010", to_cid, credit=amount),
        ]

    def on_fx_deposit(self, p, ev):
        cid = p["customer_id"]

        market_rate = D(p["market_rate"])
        customer_rate = D(p["customer_rate"])

        if customer_rate > market_rate:
            raise Rejected()

        usd_market = money(D(p["usd_at_market_rate"]))
        usd_customer = money(D(p["usd_at_customer_rate"]))
        spread = money(usd_market - usd_customer)

        return [
            leg("1100", cid, debit=usd_market),
            leg("2010", cid, credit=usd_customer),
            leg("4100", cid, credit=spread),
        ]

    def on_withdrawal_requested(self, p, ev):
        withdrawal_id = p["withdrawal_id"]
        cid = p["customer_id"]
        amount = money(D(p["amount"]))

        if withdrawal_id in self.withdrawals:
            raise Rejected()

        self.withdrawals[withdrawal_id] = {
            "customer_id": cid,
            "amount": amount,
            "status": "requested",
        }

        return [
            leg("2010", cid, debit=amount),
            leg("2300", cid, credit=amount),
        ]

    def on_withdrawal_settled(self, p, ev):
        withdrawal_id = p["withdrawal_id"]

        withdrawal = self.withdrawals.get(withdrawal_id)

        if withdrawal is None:
            raise Rejected()

        if withdrawal["status"] != "requested":
            raise Rejected()

        cid = withdrawal["customer_id"]
        amount = withdrawal["amount"]

        withdrawal["status"] = "settled"

        return [
            leg("2300", cid, debit=amount),
            leg("1100", cid, credit=amount),
        ]

    def on_withdrawal_rejected(self, p, ev):
        withdrawal_id = p["withdrawal_id"]

        withdrawal = self.withdrawals.get(withdrawal_id)

        if withdrawal is None:
            raise Rejected()

        if withdrawal["status"] != "requested":
            raise Rejected()

        cid = withdrawal["customer_id"]
        amount = withdrawal["amount"]

        withdrawal["status"] = "rejected"

        return [
            leg("2300", cid, debit=amount),
            leg("2010", cid, credit=amount),
        ]

    def _trade_fees(self, principal, broker, partner_rate):
        principal = money(D(principal))
        partner_rate = D(partner_rate)

        tariff = TARIFFS.get(broker)

        if tariff is None:
            raise Rejected()

        brokerage = money(
            max(
                principal * tariff["brokerage_bps"] * BPS,
                tariff["min_fee"],
            )
        )

        custody = money(
            principal * tariff["custody_bps"] * BPS
        )

        regulatory = money(
            principal * D("8") * BPS
        )

        broker_cost = money(
            principal * tariff["broker_cost_bps"] * BPS
            + tariff["ticket"]
        )

        custody_cost = money(
            principal * tariff["custody_cost_bps"] * BPS
        )

        margin = brokerage + custody - broker_cost - custody_cost

        partner_share = money(
            partner_rate * max(margin, ZERO)
        )

        return {
            "brokerage": brokerage,
            "custody": custody,
            "regulatory": regulatory,
            "broker_cost": broker_cost,
            "custody_cost": custody_cost,
            "partner_share": partner_share,
            "broker_payable_account": tariff["payable_account"],
        }

    def _owned_quantity(self, customer_id, symbol):
        quantity = ZERO

        for lot in self.lots.get((customer_id, symbol), []):
            quantity += lot["quantity"]

        return quantity


    def _share_hold(self, customer_id, symbol):
        held = ZERO

        for order in self.orders.values():
            if (
                order["customer_id"] == customer_id
                and order["side"] == "sell"
                and order["symbol"] == symbol
                and order["status"] == "open"
            ):
                held += order["remaining_quantity"]

        return held

    def on_order_placed(self, p, ev):
        order_id = p["order_id"]

        if order_id in self.orders:
            raise Rejected()

        cid = p["customer_id"]
        side = p["side"]
        symbol = p["symbol"]
        quantity = D(p["quantity"])
        limit_price = D(p["limit_price"])
        asset_class = p["asset_class"]
        est_charges = money(D(p["est_charges"]))

        if side not in ("buy", "sell"):
            raise Rejected()

        cash_hold = ZERO

        if side == "buy":
            cash_hold = money(
                quantity * limit_price + est_charges
            )

        if side == "sell":
            owned = self._owned_quantity(cid, symbol)
            held = self._share_hold(cid, symbol)
            available = owned - held

            if quantity > available:
                raise Rejected()

        self.orders[order_id] = {
            "order_id": order_id,
            "customer_id": cid,
            "side": side,
            "symbol": symbol,
            "quantity": quantity,
            "remaining_quantity": quantity,
            "limit_price": limit_price,
            "asset_class": asset_class,
            "est_charges": est_charges,
            "original_cash_hold": cash_hold,
            "remaining_cash_hold": cash_hold,
            "status": "open",
        }

        return []

    def _consume_fifo(self, customer_id, symbol, quantity):
        quantity = D(quantity)

        if quantity <= ZERO:
            raise Rejected()

        lots = self.lots.get((customer_id, symbol), [])

        total_available = sum(
            (lot["quantity"] for lot in lots),
            ZERO,
        )

        if quantity > total_available:
            raise Rejected()

        remaining_to_sell = quantity
        cost_relieved = ZERO

        while remaining_to_sell > ZERO:
            lot = lots[0]

            lot_quantity = lot["quantity"]
            lot_cost = lot["cost"]

            consumed_quantity = min(
                remaining_to_sell,
                lot_quantity,
            )

            if consumed_quantity == lot_quantity:
                consumed_cost = lot_cost
            else:
                consumed_cost = money(
                    lot_cost
                    * consumed_quantity
                    / lot_quantity
                )

            cost_relieved += consumed_cost

            lot["quantity"] -= consumed_quantity
            lot["cost"] = money(
                lot_cost - consumed_cost
            )

            remaining_to_sell -= consumed_quantity

            if lot["quantity"] == ZERO:
                lots.pop(0)

        return money(cost_relieved)

    def _add_buy_lot(self, p, ev):
        cid = p["customer_id"]
        symbol = p["symbol"]
        quantity = D(p["quantity"])
        cost = money(D(p["principal"]))

        if quantity <= ZERO:
            raise Rejected()

        self.lots[(cid, symbol)].append({
            "event_id": ev["event_id"],
            "trade_id": p["trade_id"],
            "quantity": quantity,
            "cost": cost,
        })

    def _buy_fill_legs(self, p):
        cid = p["customer_id"]
        principal = money(D(p["principal"]))

        fees = self._trade_fees(
            principal,
            p["broker"],
            p["partner_rate"],
        )

        brokerage = fees["brokerage"]
        custody = fees["custody"]
        regulatory = fees["regulatory"]
        broker_cost = fees["broker_cost"]
        custody_cost = fees["custody_cost"]
        partner_share = fees["partner_share"]

        customer_total = money(
            principal + brokerage + custody + regulatory
        )

        return [
            leg("2010", cid, debit=customer_total),
            leg("2350", cid, credit=principal),

            leg("1200", cid, debit=principal),
            leg("2100", cid, credit=principal),

            leg("5000", cid, debit=broker_cost),
            leg("4000", cid, credit=brokerage),

            leg("5010", cid, debit=custody_cost),
            leg("4010", cid, credit=custody),

            leg("5100", cid, debit=partner_share),
            leg("2400", cid, credit=regulatory),

            leg(
                fees["broker_payable_account"],
                cid,
                credit=broker_cost,
            ),
            leg("2420", cid, credit=custody_cost),
            leg("2430", cid, credit=partner_share),
        ]

    def _sell_fill_legs(self, p, fifo_cost):
        cid = p["customer_id"]
        principal = money(D(p["principal"]))
        fifo_cost = money(fifo_cost)

        fees = self._trade_fees(
            principal,
            p["broker"],
            p["partner_rate"],
        )

        brokerage = fees["brokerage"]
        custody = fees["custody"]
        regulatory = fees["regulatory"]
        broker_cost = fees["broker_cost"]
        custody_cost = fees["custody_cost"]
        partner_share = fees["partner_share"]

        customer_net = money(
            principal - brokerage - custody - regulatory
        )

        return [
            # Sale proceeds become broker receivable.
            leg("1150", cid, debit=principal),

            # Customer receives net sale proceeds.
            leg("2010", cid, credit=customer_net),

            # Remove securities at FIFO cost.
            leg("2100", cid, debit=fifo_cost),
            leg("1200", cid, credit=fifo_cost),

            # Revenue / costs / payables.
            leg("5000", cid, debit=broker_cost),
            leg("4000", cid, credit=brokerage),

            leg("5010", cid, debit=custody_cost),
            leg("4010", cid, credit=custody),

            leg("5100", cid, debit=partner_share),
            leg("2400", cid, credit=regulatory),

            leg(
                fees["broker_payable_account"],
                cid,
                credit=broker_cost,
            ),
            leg("2420", cid, credit=custody_cost),
            leg("2430", cid, credit=partner_share),
        ]

    def on_order_partially_filled(self, p, ev):
        order = self.orders.get(p["order_id"])

        if order is None:
            raise Rejected()

        if order["status"] != "open":
            raise Rejected()

        if p["side"] != order["side"]:
            raise Rejected()

        fill_quantity = D(p["quantity"])

        if fill_quantity <= ZERO:
            raise Rejected()

        if fill_quantity >= order["remaining_quantity"]:
            raise Rejected()

        if p["side"] == "buy":
            remaining_before = order["remaining_quantity"]
            hold_before = order["remaining_cash_hold"]

            release = money(
                hold_before * fill_quantity / remaining_before
            )

            order["remaining_quantity"] -= fill_quantity
            order["remaining_cash_hold"] = money(
                hold_before - release
            )

            self._add_buy_lot(p, ev)
            return self._buy_fill_legs(p)

        if p["side"] == "sell":
            fifo_cost = self._consume_fifo(
                p["customer_id"],
                p["symbol"],
                fill_quantity,
            )

            order["remaining_quantity"] -= fill_quantity

            return self._sell_fill_legs(
                p,
                fifo_cost,
            )

        raise Rejected()


    def on_order_filled(self, p, ev):
        order = self.orders.get(p["order_id"])

        if order is None:
            raise Rejected()

        if order["status"] != "open":
            raise Rejected()

        if p["side"] != order["side"]:
            raise Rejected()

        fill_quantity = D(p["quantity"])

        if fill_quantity <= ZERO:
            raise Rejected()

        if fill_quantity != order["remaining_quantity"]:
            raise Rejected()

        if p["side"] == "buy":
            order["remaining_quantity"] = ZERO
            order["remaining_cash_hold"] = ZERO
            order["status"] = "filled"

            self._add_buy_lot(p, ev)

            return self._buy_fill_legs(p)

        if p["side"] == "sell":
            fifo_cost = self._consume_fifo(
                p["customer_id"],
                p["symbol"],
                fill_quantity,
            )

            order["remaining_quantity"] = ZERO
            order["status"] = "filled"

            return self._sell_fill_legs(
                p,
                fifo_cost,
            )

        raise Rejected()

    def on_trade_settled(self, p, ev):
        raise NotImplementedError(
            "buy: Dr 2350 / Cr 1100.  sell: Dr 1100 / Cr 1150")

    def on_order_cancelled(self, p, ev):
        order_id = p["order_id"]

        order = self.orders.get(order_id)

        if order is None:
            raise Rejected()

        if order["status"] != "open":
            raise Rejected()

        order["remaining_cash_hold"] = ZERO
        order["status"] = "cancelled"

        return []

    def on_order_rejected(self, p, ev):
        return self.on_order_cancelled(p, ev)

    def on_dividend_cash(self, p, ev):
        raise NotImplementedError(
            "Dr 1100 net / Cr 2010 net. Tax is withheld at source, so raise no "
            "payable")

    def on_dividend_reinvested(self, p, ev):
        raise NotImplementedError(
            "Dr 1200 net / Cr 2100 net, and add a lot. Cash is not involved")

    def on_stock_split(self, p, ev):
        raise NotImplementedError(
            "No legs. Quantity scales; total cost does not change")

    def on_symbol_change(self, p, ev):
        raise NotImplementedError("No legs. Re-key the holding")

    def on_reversal(self, p, ev):
        raise NotImplementedError(
            "Post the exact inverse of the original's legs, and undo its effect "
            "on your LOT BOOK too. A reversed buy whose lot you leave behind "
            "balances perfectly and corrupts every later cost basis")

    def _positions_for_customer(self, customer_id):
        positions = {}

        for (cid, symbol), lots in self.lots.items():
            if cid != customer_id:
                continue

            quantity = ZERO
            cost_basis = ZERO

            for lot in lots:
                quantity += lot["quantity"]
                cost_basis += lot["cost"]

            if quantity != ZERO:
                positions[symbol] = {
                    "quantity": str(quantity),
                    "cost_basis": str(money(cost_basis)),
                }

        return {
            symbol: positions[symbol]
            for symbol in sorted(positions)
        }

    # -- reporting ----------------------------------------------------------
    def snapshot(self) -> dict:
        """What a checkpoint_request wants: your whole state, right now.

        Report every account you have ever posted to, including any that have
        netted back to zero. Trial balance values are debit-positive, so
        liabilities carry a negative sign.
        """
        tb: dict[str, Decimal] = defaultdict(lambda: ZERO)

        for (_cid, acct), bal in self.balances.items():
            tb[acct] += bal

        # A customer can exist because of either ledger activity or an open order.
        customer_ids = {cid for cid, _acct in self.balances.keys()}
        customer_ids.update(
            order["customer_id"] for order in self.orders.values()
        )
        customer_ids.update(
            cid for cid, _symbol in self.lots.keys()
        )

        # Calculate active BUY cash holds.
        cash_holds: dict[str, Decimal] = defaultdict(lambda: ZERO)

        for order in self.orders.values():
            if order["side"] == "buy" and order["status"] == "open":
                cash_holds[order["customer_id"]] += order["remaining_cash_hold"]

        customers: dict[str, dict] = {}

        for cid in customer_ids:
            wallet_cash = ZERO

            for (balance_cid, acct), bal in self.balances.items():
                if balance_cid == cid and acct == "2010":
                    wallet_cash += -bal

            customers[cid] = {
                "wallet_cash": str(money(wallet_cash)),
                "cash_hold": str(money(cash_holds[cid])),
                "positions": self._positions_for_customer(cid),
            }

        return {
            "trial_balance": {
                acct: str(money(value))
                for acct, value in sorted(tb.items())
            },
            "customers": {
                cid: customers[cid]
                for cid in sorted(customers)
            },
        }


class Rejected(Exception):
    """Raise from a handler for an event you refuse to post.

    An oversell, a reversal of something you never received, a payload that
    will not parse. Rejecting one event and carrying on beats stopping: a
    server that stalls misses everything after it.
    """
