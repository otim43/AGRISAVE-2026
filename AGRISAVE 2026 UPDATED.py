import os
import re
import getpass
from datetime import datetime

# Admin fixed credentials
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"
MAX_LOGIN_ATTEMPTS = 3

# Constants and business rules
DATA_FILE = "tukolere_members.txt"
TRANSACTION_LOG_FILE = "tukolere_loan_transactions.txt"
MEMBER_ID_PATTERN = re.compile(r"^TW\d{3}$")
PHONE_PATTERN = re.compile(r"^(077|078|070|075|076|074|079|073)\d{7}$")
NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z .'-]*$")
ENTERPRISES = ["Coffee", "Maize", "Cocoa", "Dairy", "Poultry", "Bananas"]
MIN_SAVINGS_FOR_LOAN = 100000   # UGX (strictly required savings >= 100,000)
LOAN_MULTIPLIER = 2              # Maximum loan principal limit = 2 x savings
INTEREST_RATE = 0.10             # Fixed 10% interest rate on all loans
FIELDS = ["member_id", "name", "phone", "village", "enterprise",
           "savings", "loan_balance"]

# Program state (in-memory storage)
members = []             # list of dictionaries, one per member
loan_transactions = []   # list of transaction dictionaries
unsaved_changes = False  # tracks whether memory differs from files

# Formatting helpers
def ugx(amount):
    """Format a number as UGX with thousands separators."""
    if float(amount).is_integer():
        return f"UGX {int(amount):,}"
    return f"UGX {amount:,.2f}"

def parse_amount(text):
    """Convert text to a number; return an int when it is a whole value."""
    value = float(text.replace(",", "").strip())
    return int(value) if value.is_integer() else value

def line(char="=", width=88):
    print(char * width)

# Validation functions
def validate_member_id(member_id):
    """Return an error message, or None when the ID is valid and unique."""
    if not MEMBER_ID_PATTERN.match(member_id):
        return "Member ID must be 'TW' followed by exactly 3 digits (e.g. TW001)."
    if find_by_id(member_id) is not None:
        return f"Member ID {member_id} already exists."
    return None

def validate_name(name):
    if not name:
        return "Full name must not be empty."
    if not NAME_PATTERN.match(name):
        return "Name may contain only letters, spaces, apostrophes, dots and hyphens."
    if sum(ch.isalpha() for ch in name) < 3:
        return "Name must contain at least 3 alphabetic characters."
    return None

def validate_phone(phone):
    if not PHONE_PATTERN.match(phone):
        return ("Phone must be exactly 10 digits starting with 077, 078, 070, "
                "075, 076, 079, 073 or 074.")
    return None

def validate_village(village):
    if not village:
        return "Village / Cell must not be empty."
    if "," in village:
        return "Village / Cell must not contain commas (file uses CSV format)."
    return None

def validate_enterprise(enterprise):
    if enterprise.title() not in ENTERPRISES:
        return "Enterprise must be one of: " + ", ".join(ENTERPRISES) + "."
    return None

def validate_amount(text):
    """Return (value, error). Value is None when the input is invalid."""
    try:
        value = parse_amount(text)
    except ValueError:
        return None, "Please enter a valid number (e.g. 250000)."
    if value < 0:
        return None, "Amount cannot be negative."
    return value, None

# Input helpers
def prompt_text(label, validator, transform=lambda s: s):
    while True:
        raw = transform(input(f"{label}: ").strip())
        error = validator(raw)
        if error is None:
            return raw
        print(f"  [!] {error}")

def prompt_amount(label):
    while True:
        value, error = validate_amount(input(f"{label} (UGX): "))
        if error is None:
            return value
        print(f"  [!] {error}")

def confirm(question):
    while True:
        answer = input(f"{question} (y/n): ").strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("  [!] Please answer y or n.")

# Lookup helpers
def find_by_id(member_id):
    for member in members:
        if member["member_id"].upper() == member_id.upper():
            return member
    return None

def search_members(term):
    """Case-insensitive partial match on Member ID or Full Name."""
    term = term.lower()
    return [m for m in members
            if term in m["member_id"].lower() or term in m["name"].lower()]

# Table display
def print_table(records):
    header = (f"{'ID':<7}{'Full Name':<22}{'Phone':<13}{'Village':<14}"
              f"{'Enterprise':<11}{'Savings (UGX)':>14}{'Loan Debt (UGX)':>16}")
    line()
    print(header)
    line("-")
    for m in records:
        print(f"{m['member_id']:<7}{m['name'][:21]:<22}{m['phone']:<13}"
              f"{m['village'][:13]:<14}{m['enterprise'][:11]}"
              f"{m['savings']:>14,.0f}{m['loan_balance']:>16,.0f}")
    line()
    print(f"Total records shown: {len(records)}")

# Transaction Logging Helper
def log_loan_transaction(member_id, name, tx_type, amount, balance_after):
    """Record a timestamped loan transaction (DISBURSEMENT, REPAYMENT, WRITE_OFF)."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tx_record = {
        "timestamp": timestamp,
        "member_id": member_id,
        "name": name,
        "type": tx_type,
        "amount": amount,
        "balance_after": balance_after
    }
    loan_transactions.append(tx_record)
    return timestamp

# Member Registration
def add_member():
    global unsaved_changes
    print("\n--- Member Enrolment ---")
    member_id = prompt_text("Member ID (e.g. TW001)", validate_member_id,
                            transform=str.upper)
    name = prompt_text("Full Name", validate_name)
    phone = prompt_text("Phone Number (10 digits)", validate_phone)
    village = prompt_text("Village / Cell", validate_village)
    enterprise = prompt_text(
        f"Main Enterprise ({'/'.join(ENTERPRISES)})", validate_enterprise
    ).title()
    
    members.append({
        "member_id": member_id,
        "name": name,
        "phone": phone,
        "village": village,
        "enterprise": enterprise,
        "savings": 0,
        "loan_balance": 0
    })
    unsaved_changes = True
    print(f"\n[OK] Member {member_id} ({name}) enrolled successfully with UGX 0 initial savings balance.")

# Savings Deposit Module
def deposit_savings():
    """Allows admin to process a savings deposit and prints a timestamped transaction receipt."""
    global unsaved_changes
    print("\n--- Savings & Deposit Operations ---")
    member_id = input("Enter Member ID: ").strip().upper()
    member = find_by_id(member_id)
    if member is None:
        print(f"[!] No member found with ID {member_id}.")
        return

    print(f"\nMember Account Identified: {member['member_id']} - {member['name']}")
    print(f"Current Cumulative Savings: {ugx(member['savings'])}")

    deposit_amount = prompt_amount("Enter deposit savings amount")
    if deposit_amount <= 0:
        print("  [!] Deposit amount must be greater than zero.")
        return

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    member["savings"] += deposit_amount
    unsaved_changes = True

    print("\n" + "=" * 55)
    print("           OFFICIAL SAVINGS DEPOSIT RECEIPT")
    print("=" * 55)
    print(f"  Transaction Timestamp : {timestamp}")
    print(f"  Member ID             : {member['member_id']}")
    print(f"  Account Name          : {member['name']}")
    print(f"  Amount Deposited      : {ugx(deposit_amount)}")
    print(f"  Updated Savings Total : {ugx(member['savings'])}")
    print("=" * 55)
    print("[OK] Savings deposit transaction recorded successfully.")

# Display records
def display_members():
    print("\n--- Member Account Registry ---")
    if not members:
        print("No member records found in database. Enroll members or import database file.")
        return
    print_table(sorted(members, key=lambda m: m["member_id"]))

# Search
def search_member():
    print("\n--- Search Member Directory ---")
    term = input("Enter Member ID or Full Name (partial allowed): ").strip()
    if not term:
        print("[!] Search term cannot be empty.")
        return
    results = search_members(term)
    if results:
        print_table(results)
    else:
        print(f"No member matches found for term '{term}'.")

# Delete member
def delete_member():
    global unsaved_changes
    print("\n--- Terminate Member Account ---")
    member_id = input("Enter Member ID to terminate: ").strip().upper()
    member = find_by_id(member_id)
    if member is None:
        print(f"[!] No member found with ID {member_id}.")
        return
    print_table([member])
    if confirm("Are you sure you want to permanently purge this member record?"):
        members.remove(member)
        unsaved_changes = True
        print(f"[OK] Member account {member_id} permanently removed from system memory.")
    else:
        print("Account termination cancelled.")

# Member Account Directory Sub-Menu
MEMBER_MENU = """
=================== MEMBER ACCOUNT DIRECTORY ===================
  1. Register New Member
  2. View Full Member Directory
  3. Search Member Account
  4. Terminate Member Account
  5. Return to Main Dashboard
---------------------------------------------------------------"""

def member_records_menu():
    while True:
        print(MEMBER_MENU)
        choice = input("Select an option (1-5): ").strip()
        if choice == "1":
            add_member()
        elif choice == "2":
            display_members()
        elif choice == "3":
            search_member()
        elif choice == "4":
            delete_member()
        elif choice == "5":
            break
        else:
            print("[!] Invalid selection. Please enter a choice between 1 and 5.")

def max_loan_limit(savings):
    return LOAN_MULTIPLIER * savings

def check_eligibility(member):
    """Strictly enforce credit policy: savings >= 100,000 UGX and zero unpaid loans."""
    reasons = []
    if member["savings"] < MIN_SAVINGS_FOR_LOAN:
        reasons.append(
            f"Savings balance ({ugx(member['savings'])}) is below the required minimum "
            f"threshold of {ugx(MIN_SAVINGS_FOR_LOAN)}."
        )
    if member["loan_balance"] > 0:
        reasons.append(
            f"Existing unpaid loan balance of {ugx(member['loan_balance'])} must be fully settled."
        )
    return (len(reasons) == 0), reasons

# Integrated Credit Processing (Loan Origination with 10% Interest Rate)
def process_loan():
    """Evaluate credit qualification and disburse loans under institutional guidelines + 10% interest."""
    global unsaved_changes
    print("\n--- Loan Processing & Credit Origination ---")
    member_id = input("Enter Member ID: ").strip().upper()
    member = find_by_id(member_id)
    if member is None:
        print(f"[!] No member found with ID {member_id}.")
        return

    eligible, reasons = check_eligibility(member)
    max_principal = max_loan_limit(member["savings"])

    line("-", 60)
    print(f"Member ID             : {member['member_id']}")
    print(f"Member Name           : {member['name']}")
    print(f"Cumulative Savings    : {ugx(member['savings'])}")
    print(f"Min Threshold Reqd    : {ugx(MIN_SAVINGS_FOR_LOAN)}")
    print(f"Outstanding Debt      : {ugx(member['loan_balance'])}")
    print(f"Max Borrowing Principal: {ugx(max_principal)} (2 x total savings)")
    print(f"Fixed Interest Rate   : {int(INTEREST_RATE * 100)}%")
    line("-", 60)

    if not eligible:
        print("Application Status: REJECTED (Non-compliant with Credit Policy)")
        for reason in reasons:
            print(f"  [!] {reason}")
        line("-", 60)
        return

    print("Application Status: APPROVED FOR CREDIT EVALUATION")
    
    while True:
        requested_principal = prompt_amount("Enter requested loan principal amount")
        if requested_principal <= 0:
            print("  [!] Requested principal amount must exceed zero.")
            continue
        if requested_principal > max_principal:
            print(f"  [!] Principal exceeds maximum approved borrowing limit of {ugx(max_principal)}.")
            continue
        break

    interest_amount = requested_principal * INTEREST_RATE
    total_repayable = requested_principal + interest_amount

    print(f"\nLoan Origination Summary:")
    print(f"  Member Account      : {member['member_id']}")
    print(f"  Applicant Name      : {member['name']}")
    print(f"  Disbursed Principal : {ugx(requested_principal)}")
    print(f"  Interest (10%)      : {ugx(interest_amount)}")
    print(f"  Total Repayable Sum : {ugx(total_repayable)}")

    if confirm("Authorize and disburse loan funds?"):
        member["loan_balance"] += total_repayable
        timestamp = log_loan_transaction(
            member["member_id"], member["name"], "DISBURSEMENT", total_repayable, member["loan_balance"]
        )
        unsaved_changes = True
        
        print("\n" + "=" * 55)
        print("          OFFICIAL LOAN DISBURSEMENT RECEIPT")
        print("=" * 55)
        print(f"  Transaction Timestamp : {timestamp}")
        print(f"  Member ID             : {member['member_id']}")
        print(f"  Account Name          : {member['name']}")
        print(f"  Disbursed Principal   : {ugx(requested_principal)}")
        print(f"  Interest Charge (10%) : {ugx(interest_amount)}")
        print(f"  Total Repayable Debt  : {ugx(total_repayable)}")
        print(f"  Total Outstanding Debt: {ugx(member['loan_balance'])}")
        print("=" * 55)
        print(f"[OK] Principal of {ugx(requested_principal)} (+ {ugx(interest_amount)} interest) successfully disbursed.")
    else:
        print("\nLoan origination transaction cancelled.")

# Loan Repayment Processor
def repay_loan():
    """Process a loan repayment transaction and print an official receipt."""
    global unsaved_changes
    print("\n--- Loan Repayment & Settlement ---")
    member_id = input("Enter Member ID: ").strip().upper()
    member = find_by_id(member_id)
    if member is None:
        print(f"[!] No member found with ID {member_id}.")
        return

    print(f"\nMember Account Identified: {member['member_id']} - {member['name']}")
    print(f"Total Outstanding Debt   : {ugx(member['loan_balance'])} (Includes 10% interest)")

    if member["loan_balance"] <= 0:
        print("  [i] Member has no outstanding loan balance to repay.")
        return

    repayment_amount = prompt_amount("Enter loan repayment amount")
    if repayment_amount <= 0:
        print("  [!] Repayment amount must be greater than zero.")
        return
    if repayment_amount > member["loan_balance"]:
        print(f"  [!] Repayment amount exceeds outstanding debt balance of {ugx(member['loan_balance'])}.")
        return

    member["loan_balance"] -= repayment_amount
    timestamp = log_loan_transaction(
        member["member_id"], member["name"], "REPAYMENT", repayment_amount, member["loan_balance"]
    )
    unsaved_changes = True

    print("\n" + "=" * 55)
    print("           OFFICIAL LOAN REPAYMENT RECEIPT")
    print("=" * 55)
    print(f"  Transaction Timestamp : {timestamp}")
    print(f"  Member ID             : {member['member_id']}")
    print(f"  Account Name          : {member['name']}")
    print(f"  Amount Paid           : {ugx(repayment_amount)}")
    print(f"  Remaining Debt Balance: {ugx(member['loan_balance'])}")
    print("=" * 55)
    print("[OK] Loan repayment transaction recorded successfully.")

# Loan Write-Off Processor
def write_off_loan():
    """Process a loan write-off for bad or default debt."""
    global unsaved_changes
    print("\n--- Bad Debt Loan Write-Off Module ---")
    member_id = input("Enter Member ID: ").strip().upper()
    member = find_by_id(member_id)
    if member is None:
        print(f"[!] No member found with ID {member_id}.")
        return

    print(f"\nMember Account Identified: {member['member_id']} - {member['name']}")
    print(f"Current Outstanding Debt : {ugx(member['loan_balance'])}")

    if member["loan_balance"] <= 0:
        print("  [i] Member has no active debt balance to write off.")
        return

    write_off_amount = prompt_amount("Enter write-off amount")
    if write_off_amount <= 0:
        print("  [!] Write-off amount must be greater than zero.")
        return
    if write_off_amount > member["loan_balance"]:
        print(f"  [!] Write-off amount cannot exceed active loan balance of {ugx(member['loan_balance'])}.")
        return

    print(f"\n[WARNING] You are writing off {ugx(write_off_amount)} of unrecoverable debt for {member['name']}.")
    if confirm("Authorize bad debt write-off execution?"):
        member["loan_balance"] -= write_off_amount
        timestamp = log_loan_transaction(
            member["member_id"], member["name"], "WRITE_OFF", write_off_amount, member["loan_balance"]
        )
        unsaved_changes = True

        print("\n" + "=" * 55)
        print("        OFFICIAL BAD DEBT WRITE-OFF VOUCHER")
        print("=" * 55)
        print(f"  Transaction Timestamp : {timestamp}")
        print(f"  Member ID             : {member['member_id']}")
        print(f"  Account Name          : {member['name']}")
        print(f"  Amount Written Off    : {ugx(write_off_amount)}")
        print(f"  Adjusted Debt Balance : {ugx(member['loan_balance'])}")
        print("=" * 55)
        print("[OK] Loan write-off processed and logged successfully.")
    else:
        print("Loan write-off operation cancelled.")

# Credit Origination & Loan Processing Sub-Menu
LOAN_MENU = """
================ CREDIT ORIGINATION & LOAN PROCESSING ================
  1. Issue / Disburse Loan (At 10% Interest Rate)
  2. Settle / Repay Loan
  3. Write-Off Bad Debt
  4. Return to Main Dashboard
---------------------------------------------------------------"""

def credit_management_menu():
    while True:
        print(LOAN_MENU)
        choice = input("Select an option (1-4): ").strip()
        if choice == "1":
            process_loan()
        elif choice == "2":
            repay_loan()
        elif choice == "3":
            write_off_loan()
        elif choice == "4":
            break
        else:
            print("[!] Invalid selection. Please enter a choice between 1 and 4.")

# Detailed Loan Status Report & Audit Trail Generator
def generate_loan_report():
    """Display comprehensive report of all member loan statuses and timestamped audit logs."""
    print("\n=================== CUMULATIVE LOAN STATUS REPORT ===================")
    if not members:
        print("No member records found in database.")
        return

    # Aggregate stats per member from transaction logs
    member_tx_stats = {m["member_id"]: {"disbursed": 0, "repaid": 0, "written_off": 0} for m in members}
    for tx in loan_transactions:
        mid = tx["member_id"]
        if mid in member_tx_stats:
            if tx["type"] == "DISBURSEMENT":
                member_tx_stats[mid]["disbursed"] += tx["amount"]
            elif tx["type"] == "REPAYMENT":
                member_tx_stats[mid]["repaid"] += tx["amount"]
            elif tx["type"] == "WRITE_OFF":
                member_tx_stats[mid]["written_off"] += tx["amount"]

    header = (f"{'ID':<7}{'Member Name':<20}{'Disbursed+10%':>15}"
              f"{'Repaid':>13}{'Written Off':>13}{'Active Debt':>13}{'Status':>16}")
    line("=", 99)
    print(header)
    line("-", 99)

    total_disbursed = sum(s["disbursed"] for s in member_tx_stats.values())
    total_repaid = sum(s["repaid"] for s in member_tx_stats.values())
    total_written_off = sum(s["written_off"] for s in member_tx_stats.values())
    total_active_debt = sum(m["loan_balance"] for m in members)

    for m in sorted(members, key=lambda x: x["member_id"]):
        mid = m["member_id"]
        stats = member_tx_stats[mid]
        
        # Determine status
        if m["loan_balance"] > 0:
            status = "ACTIVE DEBT"
        elif stats["written_off"] > 0:
            status = "WRITTEN OFF"
        elif stats["disbursed"] > 0 and m["loan_balance"] == 0:
            status = "FULLY SETTLED"
        else:
            status = "NO LOAN"

        print(f"{m['member_id']:<7}{m['name'][:19]:<20}"
              f"{stats['disbursed']:>15,.0f}{stats['repaid']:>13,.0f}"
              f"{stats['written_off']:>13,.0f}{m['loan_balance']:>13,.0f}"
              f"{status:>16}")

    line("-", 99)
    print(f"{'PORTFOLIO TOTALS':<27}{total_disbursed:>15,.0f}{total_repaid:>13,.0f}"
          f"{total_written_off:>13,.0f}{total_active_debt:>13,.0f}")
    line("=", 99)

    if loan_transactions:
        print("\n--- TIMESTAMPED LOAN TRANSACTION AUDIT LOG ---")
        log_header = f"{'Timestamp':<21}{'ID':<7}{'Name':<20}{'Type':<14}{'Amount (UGX)':>14}{'Balance After':>15}"
        line("-", 93)
        print(log_header)
        line("-", 93)
        for tx in loan_transactions:
            print(f"{tx['timestamp']:<21}{tx['member_id']:<7}{tx['name'][:19]:<20}"
                  f"{tx['type']:<14}{tx['amount']:>14,.0f}{tx['balance_after']:>15,.0f}")
        line("-", 93)
        print(f"Total Audit Trail Entries Logged: {len(loan_transactions)}")
    else:
        print("\n[i] No timestamped loan transactions recorded yet.")

# Simplified Portfolio Overview & Financial Reports
def calculate_total_savings():
    """Generates a clean, simple, and comprehensive SACCO financial portfolio report."""
    print("\n" + "=" * 88)
    print("         AGRISAVE SACCO - PORTFOLIO OVERVIEW & FINANCIAL REPORT")
    print("=" * 88)
    
    if not members:
        print("No active member accounts found in the database.")
        return

    # Calculate financial key figures
    total_savings = sum(m["savings"] for m in members)
    total_active_loans = sum(m["loan_balance"] for m in members)
    
    total_disbursed = sum(tx["amount"] for tx in loan_transactions if tx["type"] == "DISBURSEMENT")
    total_repaid = sum(tx["amount"] for tx in loan_transactions if tx["type"] == "REPAYMENT")
    total_written_off = sum(tx["amount"] for tx in loan_transactions if tx["type"] == "WRITE_OFF")
    net_liquidity = total_savings - total_active_loans

    # Financial Summary Table
    print("\n--- INSTITUTIONAL FINANCIAL SUMMARY ---")
    line("-", 55)
    print(f"  Fixed Interest Rate Policy     : {int(INTEREST_RATE * 100)}%")
    print(f"  Total Enrolled Members        : {len(members)}")
    print(f"  Cumulative Savings Reserve    : {ugx(total_savings)}")
    print(f"  Total Loans Disbursed (+10%)   : {ugx(total_disbursed)}")
    print(f"  Total Loan Repayments Collected: {ugx(total_repaid)}")
    print(f"  Total Bad Debt Written Off    : {ugx(total_written_off)}")
    print(f"  Current Active Outstanding Debt: {ugx(total_active_loans)}")
    print(f"  Net SACCO Liquidity Balance   : {ugx(net_liquidity)}")
    line("-", 55)

    # Member Portfolio Breakdown
    print("\n--- MEMBER SAVINGS & CREDIT REGISTER ---")
    header = f"{'ID':<7}{'Full Name':<22}{'Enterprise':<12}{'Savings':>14}{'Outstanding Debt':>18}{'Max Principal':>15}"
    line("-", 88)
    print(header)
    line("-", 88)

    for m in sorted(members, key=lambda x: x["member_id"]):
        max_p = max_loan_limit(m["savings"])
        print(f"{m['member_id']:<7}{m['name'][:21]:<22}{m['enterprise'][:11]:<12}"
              f"{m['savings']:>14,.0f}{m['loan_balance']:>18,.0f}{max_p:>15,.0f}")

    line("=", 88)

# Save data file
def save_records(silent=False):
    global unsaved_changes
    try:
        # Save members master file
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            for m in members:
                f.write(",".join(str(m[field]) for field in FIELDS) + "\n")
        
        # Save loan transactions log file
        with open(TRANSACTION_LOG_FILE, "w", encoding="utf-8") as f:
            for tx in loan_transactions:
                f.write(f"{tx['timestamp']},{tx['member_id']},{tx['name']},{tx['type']},{tx['amount']},{tx['balance_after']}\n")
    except OSError as err:
        print(f"[!] Data commit failed: {err}")
        return False
    
    unsaved_changes = False
    if not silent:
        print(f"[OK] System changes ({len(members)} members, {len(loan_transactions)} audit logs) committed successfully.")
    return True

# Load data file
def parse_record(raw_line):
    """Convert one CSV record to a member dict, or raise ValueError."""
    parts = [p.strip() for p in raw_line.split(",")]
    if len(parts) != len(FIELDS):
        raise ValueError(f"expected {len(FIELDS)} fields, found {len(parts)}")
    member = dict(zip(FIELDS, parts))
    member["member_id"] = member["member_id"].upper()
    member["enterprise"] = member["enterprise"].title()
    if not MEMBER_ID_PATTERN.match(member["member_id"]):
        raise ValueError("invalid member ID")
    if validate_phone(member["phone"]):
        raise ValueError("invalid phone number")
    member["savings"] = parse_amount(member["savings"])
    member["loan_balance"] = parse_amount(member["loan_balance"])
    if member["savings"] < 0 or member["loan_balance"] < 0:
        raise ValueError("negative financial value")
    return member

def load_records(announce=True):
    """Replace in-memory database with contents of external data file."""
    global members, loan_transactions, unsaved_changes
    if not os.path.exists(DATA_FILE):
        if announce:
            print(f"[i] System storage file {DATA_FILE} not detected. Initializing empty database.")
        return
    
    loaded, skipped, seen_ids = [], 0, set()
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            for number, raw in enumerate(f, start=1):
                if not raw.strip():
                    continue
                try:
                    record = parse_record(raw.strip())
                    if record["member_id"] in seen_ids:
                        raise ValueError("duplicate member ID")
                    seen_ids.add(record["member_id"])
                    loaded.append(record)
                except ValueError as err:
                    skipped += 1
                    print(f"  [!] Skipped line {number}: {err}")
    except OSError as err:
        print(f"[!] Data read error: {err}")
        return
    
    members = loaded

    # Load transactions log if available
    loaded_tx = []
    if os.path.exists(TRANSACTION_LOG_FILE):
        try:
            with open(TRANSACTION_LOG_FILE, "r", encoding="utf-8") as f:
                for line_str in f:
                    parts = [p.strip() for p in line_str.split(",")]
                    if len(parts) == 6:
                        loaded_tx.append({
                            "timestamp": parts[0],
                            "member_id": parts[1],
                            "name": parts[2],
                            "type": parts[3],
                            "amount": parse_amount(parts[4]),
                            "balance_after": parse_amount(parts[5])
                        })
        except OSError:
            pass
    loan_transactions = loaded_tx

    unsaved_changes = False
    if announce:
        print(f"[OK] Imported {len(loaded)} account records & {len(loan_transactions)} loan audit entries."
              + (f" ({skipped} corrupted line(s) skipped)" if skipped else ""))

def reload_records():
    """Import records from file with unsaved work warnings."""
    print("\n--- Sync Data from Storage File ---")
    if unsaved_changes and not confirm(
            "Uncommitted changes in memory will be overwritten. Proceed?"):
        print("Data synchronization cancelled.")
        return
    load_records()

# Safe exit
def exit_system():
    """Return True when system should shutdown securely."""
    if unsaved_changes:
        print("\nUncommitted system state detected.")
        if confirm("Commit changes to storage before exiting?"):
            if not save_records():
                print("Exit cancelled due to failed data commit.")
                return False
        elif not confirm("Exit WITHOUT saving? All uncommitted changes will be lost"):
            return False
    print("\nThank you for using AgriSave SACCO Management System. Goodbye!")
    return True

# Admin Login Interface
def admin_login():
    """Authenticate administrator credentials."""
    print("\n" + "=" * 55)
    print("      AGRISAVE SACCO SYSTEM - ADMINISTRATIVE LOGIN")
    print("=" * 55)
    
    attempts = 0
    while attempts < MAX_LOGIN_ATTEMPTS:
        username = input("Username: ").strip()
        try:
            password = getpass.getpass("Password: ").strip()
        except Exception:
            password = input("Password: ").strip()

        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            print("\n[OK] Administrator authenticated successfully! Access granted.\n")
            return True
        else:
            attempts += 1
            remaining = MAX_LOGIN_ATTEMPTS - attempts
            if remaining > 0:
                print(f"  [!] Invalid credentials provided. ({remaining} attempt(s) remaining)\n")
            else:
                print("\n[!] Security threshold exceeded. System access denied.")
                return False

# Main Navigation Menu
MENU = """
=========================== AGRISAVE - 2026 © ===========================
         Tukolere Wamu Agri Farmers SACCO - Mukono 
================================================================
  1. Member Account Directory
  2. Savings & Deposit Operations
  3. Credit Origination & Loan Processing
  4. Loan Status Report & Audit Trail
  5. Financial Reports & Overview 
  6. Commit System Changes (Save Data)
  7. Synchronize Database (Reload Data)
  8. Exit System
----------------------------------------------------------------"""

ACTIONS = {
    "1": member_records_menu,
    "2": deposit_savings,
    "3": credit_management_menu,
    "4": generate_loan_report,
    "5": calculate_total_savings,
    "6": save_records,
    "7": reload_records,
}

def main():
    print("Initializing AgriSave Management Core...")
    
    if not admin_login():
        return

    load_records()
    while True:
        print(MENU)
        if unsaved_changes:
            print("  (* uncommitted changes pending in memory)")
        choice = input("Select an option (1-8): ").strip()
        if choice == "8":
            if exit_system():
                break
        elif choice in ACTIONS:
            try:
                ACTIONS[choice]()
            except (KeyboardInterrupt, EOFError):
                print("\n[!] Transaction aborted by operator.")
            except Exception as err:
                print(f"[!] System error: {err}")
        else:
            print("[!] Invalid selection. Please enter a choice between 1 and 8.")

if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\n\nSystem session interrupted.")
        if unsaved_changes:
            print("Warning: Uncommitted memory changes were not written to storage.")