"""Decrypt and verify an exported audit archive using its separate passphrase."""
import argparse
from getpass import getpass
from app.audit_archive import decrypt_archive

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive')
    parser.add_argument('output', help='New JSONL path; existing files are never overwritten')
    args = parser.parse_args()
    summary = decrypt_archive(args.archive, args.output, getpass('Archive passphrase: '))
    print(f"Verified {summary['record_count']} records; retain until {summary['retain_until']}")
