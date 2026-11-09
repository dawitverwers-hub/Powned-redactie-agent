#!/usr/bin/env python3
"""
PowNed Redactie — Gebruikersbeheer
Gebruik:
  python3 manage_users.py add naam email@example.com [wachtwoord]
  python3 manage_users.py remove email@example.com
  python3 manage_users.py list
  python3 manage_users.py reset-password email@example.com nieuw_wachtwoord
"""
import json, hashlib, sys, secrets, string, os
from pathlib import Path

USERS_FILE = Path(__file__).parent / "config" / "users.json"
SALT       = os.environ.get("POWNED_SALT") or sys.exit("Set POWNED_SALT first (same value as in your .env)")
def hash_pw(pw: str) -> str:
    return hashlib.sha256(f"{SALT}{pw}".encode()).hexdigest()

def load() -> dict:
    return json.loads(USERS_FILE.read_text())

def save(cfg: dict):
    USERS_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False))

def generate_password(length=12) -> str:
    chars = string.ascii_letters + string.digits + "!@#"
    return ''.join(secrets.choice(chars) for _ in range(length))

def cmd_list():
    cfg = load()
    users = cfg.get("users", [])
    print(f"\n{'Email':<30} {'Naam':<20} {'Rol':<12}")
    print("-" * 64)
    for u in users:
        print(f"{u['email']:<30} {u['name']:<20} {u.get('role','redacteur'):<12}")
    print(f"\nTotaal: {len(users)} gebruikers")
    print(f"Toegestane domeinen: {', '.join(cfg.get('allowed_domains', []))}\n")

def cmd_add(name: str, email: str, password: str = None):
    cfg = load()
    if any(u["email"].lower() == email.lower() for u in cfg["users"]):
        print(f"⚠ {email} bestaat al.")
        return
    domain = email.split("@")[-1].lower()
    if domain not in cfg.get("allowed_domains", []):
        print(f"⚠ Domein '{domain}' is niet toegestaan.")
        print(f"  Toegestane domeinen: {cfg.get('allowed_domains')}")
        answer = input("  Toch toevoegen? Voeg domein toe aan allowed_domains? (j/n): ")
        if answer.lower() == 'j':
            cfg["allowed_domains"].append(domain)
        else:
            return
    if not password:
        password = generate_password()
        print(f"  Gegenereerd wachtwoord: {password}")
    cfg["users"].append({
        "email":         email,
        "name":          name,
        "password_hash": hash_pw(password),
        "role":          "redacteur",
    })
    save(cfg)
    print(f"✓ {name} ({email}) toegevoegd.")
    print(f"  Wachtwoord: {password}")
    print(f"  Inloggen op: https://redactie.example.com/login")

def cmd_remove(email: str):
    cfg = load()
    before = len(cfg["users"])
    cfg["users"] = [u for u in cfg["users"] if u["email"].lower() != email.lower()]
    if len(cfg["users"]) == before:
        print(f"⚠ {email} niet gevonden.")
        return
    save(cfg)
    print(f"✓ {email} verwijderd.")

def cmd_reset(email: str, new_password: str):
    cfg = load()
    for u in cfg["users"]:
        if u["email"].lower() == email.lower():
            u["password_hash"] = hash_pw(new_password)
            save(cfg)
            print(f"✓ Wachtwoord van {email} bijgewerkt.")
            return
    print(f"⚠ {email} niet gevonden.")

if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] == "list":
        cmd_list()
    elif args[0] == "add" and len(args) >= 3:
        cmd_add(args[1], args[2], args[3] if len(args) > 3 else None)
    elif args[0] == "remove" and len(args) >= 2:
        cmd_remove(args[1])
    elif args[0] == "reset-password" and len(args) >= 3:
        cmd_reset(args[1], args[2])
    else:
        print(__doc__)
