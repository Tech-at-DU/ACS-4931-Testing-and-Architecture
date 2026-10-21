"""
Invoice Bug Hunt: a debugging drill for VS Code's Python debugger.

THE TICKET
----------
Finance pinged the on-call channel: "This month's invoices are wrong for
all three customers." Your job: find out why using the debugger, not print().

Run it first (F5 or `python invoice_bug_hunt.py`) and look at the
PASS/FAIL report at the bottom. Then hunt.

SETUP (one time)
----------------
1. Install the "Python" and "Python Debugger" extensions in VS Code.
2. Open this file, hit F5, pick "Python Debugger: Current File".
   Or add this to .vscode/launch.json:

   {
     "version": "0.2.0",
     "configurations": [
       {
         "name": "Invoice Bug Hunt",
         "type": "debugpy",
         "request": "launch",
         "program": "${file}",
         "console": "integratedTerminal",
         "justMyCode": true
       }
     ]
   }

DEBUGGER MOVES TO PRACTICE
--------------------------
F9   toggle breakpoint        F10  step over
F11  step into                Shift+F11  step out
F5   continue                 Shift+F5   stop

Look for the "DEBUG:" comments. Each one points at a move worth trying:
  - plain breakpoint, conditional breakpoint, logpoint
  - Watch panel, Variables panel, Debug Console
  - Call Stack (recursion), Raised Exceptions breakpoint

There are 3 bugs. Each customer's invoice is wrong for a different reason.
"""

import math

# Raw usage export from the metering service.
USAGE_CSV = """customer,units
acme,250
acme,N/A
globex,1200
initech,100
acme,50
"""

# Promo codes each customer typed at checkout.
PROMO_CODES = {
    "acme": "LAUNCH20",
    "globex": "LAUNCH20",
    "initech": "welcome10",
}

DISCOUNTS = {
    "LAUNCH20": 20,   # percent off
    "WELCOME10": 10,
}

# Pricing tiers: (units in this tier, price per unit). None = everything else.
TIERS = [
    (100, 0.10),
    (900, 0.08),
    (None, 0.05),
]

# What finance says each invoice should be.
EXPECTED = {
    "acme": 20.80,
    "globex": 73.60,
    "initech": 9.00,
}


def parse_usage(csv_text):
    """Turn the raw export into {customer: total_units}."""
    lines = csv_text.strip().splitlines()
    totals = {}

    # DEBUG: Breakpoint here. Add `len(lines)` and `i` to the Watch panel,
    # then step with F10 and count how many rows you actually visit.
    for i in range(1, len(lines) - 1):
        customer, raw_units = lines[i].split(",")

        # DEBUG: Right-click the gutter > Add Logpoint, message:
        #   row {i}: {customer} -> {raw_units}
        # It logs to the Debug Console without pausing.
        try:
            units = int(raw_units)
        except ValueError:
            # DEBUG: In the Breakpoints panel, tick "Raised Exceptions".
            # The debugger stops on the bad row even though we catch it.
            # Skipping bad rows is on purpose here; this one is not a bug.
            continue

        totals[customer] = totals.get(customer, 0) + units

    return totals


def tiered_price(units, tier=0):
    """Price usage across tiers. Recursive on purpose."""
    size, rate = TIERS[tier]

    # DEBUG: Breakpoint here, then F11 into each recursive call and
    # watch the Call Stack panel grow. Shift+F11 climbs back out.
    if size is None or units <= size:
        return units * rate

    return size * rate + tiered_price(units - size, tier + 1)


def apply_discount(customer, total, code, used_codes=[]):
    """Apply a one-time promo code. Each customer can use a code once."""
    # DEBUG: Watch `used_codes` and `id(used_codes)` here. Is it the
    # list you think it is on every call?
    if code in used_codes:
        print(f"  {customer}: code {code} already used, no discount")
        return total

    # DEBUG: Conditional breakpoint (right-click > Add Conditional Breakpoint):
    #   customer == "initech"
    # Then hover over `code` and check DISCOUNTS in the Variables panel.
    percent = DISCOUNTS.get(code, 0)
    used_codes.append(code)
    return total - total * percent / 100


def build_invoices():
    usage = parse_usage(USAGE_CSV)
    invoices = {}

    for customer in sorted(PROMO_CODES):
        units = usage.get(customer, 0)
        subtotal = tiered_price(units)
        total = apply_discount(customer, subtotal, PROMO_CODES[customer])

        # DEBUG: Pause here and open the Debug Console. Try:
        #   tiered_price(300)
        #   usage
        #   DISCOUNTS.get("welcome10")
        invoices[customer] = round(total, 2)

    return invoices


def report(invoices):
    print("\nInvoice check")
    print("-" * 40)
    failures = 0
    for customer, expected in EXPECTED.items():
        actual = invoices.get(customer)
        ok = actual is not None and math.isclose(actual, expected)
        failures += not ok
        status = "PASS" if ok else "FAIL"
        print(f"{status}  {customer:<8} expected ${expected:>6.2f}  got ${actual:>6.2f}")
    print("-" * 40)
    print("All invoices correct. Ship it." if failures == 0
          else f"{failures} invoice(s) wrong. Keep hunting.")


if __name__ == "__main__":
    report(build_invoices())
