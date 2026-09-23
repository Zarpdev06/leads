#!/usr/bin/env python
"""Generate a messy CSV that mimics a real public-contacts export.

    python scripts/seed_test_data.py --rows 5000 --out data/public_contacts.csv

Column names are deliberately inconsistent (extra spaces, unusual names, a
couple of unnamed columns) so the auto-mapper has real work to do.
"""
from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path

CITIES = [("Chicago", "Illinois"), ("Dallas", "Texas"), ("Phoenix", "Arizona"),
          ("Atlanta", "Georgia"), ("Denver", "Colorado"), ("Miami", "Florida"),
          ("Seattle", "Washington"), ("Boston", "Massachusetts")]
NICHES = ["Auto Detailing", "Auto Repair", "Chiropractors", "Restaurants", "Salons",
          "Plumbing", "HVAC Services", "Real Estate Agents", "Accountants", "Gyms"]
FIRST = ["James", "Maria", "Robert", "Linda", "Michael", "Ana", "David", "Priya"]
LAST = ["Smith", "Garcia", "Johnson", "Nguyen", "Brown", "Patel", "Davis", "Kim"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=2000)
    parser.add_argument("--out", default="data/public_contacts.csv")
    args = parser.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    random.seed(42)

    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "Business Name", "  Contact Person ", "First Name", "Corporate Email",
            "Website URL", "Phone", "Phone Type", "Street Address", "Zip Code",
            "State", "City", "Number of Employees", "Internal Ref",
        ])
        for index in range(args.rows):
            niche = random.choice(NICHES)
            city, state = random.choice(CITIES)
            company = f"{random.choice(LAST)} {niche} {index}"
            slug = company.replace(" ", "").lower()
            # ~12% of rows have no email at all, ~6% have a broken one.
            roll = random.random()
            email = f"owner{index}@{slug}.com"
            if roll < 0.12:
                email = ""
            elif roll < 0.18:
                email = f"owner{index}@"
            writer.writerow([
                company,
                f"{random.choice(FIRST)} {random.choice(LAST)}",
                random.choice(FIRST),
                email,
                f"www.{slug}.com/?utm_source=google" if random.random() > 0.2 else "",
                f"({random.randint(200, 989)}) 555-{index % 10000:04d}",
                random.choice(["Mobile", "Landline", ""]),
                f"{100 + index} Main St" if random.random() > 0.3 else "",
                f"{70000 + (index % 20000)}",
                random.choice([state, state[:2].upper()]),
                random.choice([city, city.lower(), city.upper()]),
                random.choice(["", "1-10", "11-50", "51-200"]),
                f"REF-{index}",
            ])
    print(f"wrote {args.rows} rows to {out}")


if __name__ == "__main__":
    main()
