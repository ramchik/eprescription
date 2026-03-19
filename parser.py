"""
Georgian prescription text parser.

Parses numbered medication lists in the format:
  1. კარდიომაგნილი - 75 მგ. 1-ტაბ, 1-ჯერ დღეში, ჭამის შემდგომ. ხანგრძლივად.
  2. ლიპრიმარი - 40 მგ. ...
"""

import re
from dataclasses import dataclass, field


@dataclass
class Medication:
    number: int
    name: str
    dosage: str
    instructions: str
    raw: str

    def __str__(self):
        return f"{self.number}. {self.name} - {self.dosage}. {self.instructions}"


def parse_prescription(text: str) -> list[Medication]:
    """
    Parse a numbered Georgian prescription text into a list of Medication objects.

    The expected format is:
        1. DrugName - Dosage. Instructions.
        2. DrugName - Dosage. Instructions.
        ...
    """
    text = text.strip()
    # Split on numbered items: match lines starting with a digit followed by a dot
    # Uses a lookahead so we keep the delimiter on each item
    pattern = r"(?=\d+\.)"
    parts = re.split(pattern, text)
    parts = [p.strip() for p in parts if p.strip()]

    medications = []
    for part in parts:
        med = _parse_single(part)
        if med:
            medications.append(med)

    return medications


def _parse_single(text: str) -> Medication | None:
    """Parse a single medication entry."""
    m = re.match(r"^(\d+)\.\s*(.+)", text, re.DOTALL)
    if not m:
        return None

    number = int(m.group(1))
    rest = m.group(2).strip()

    if " - " in rest:
        # Format: "DrugName - Dosage. Instructions."
        name_part, remainder = rest.split(" - ", 1)
        name = name_part.strip()
    else:
        # Format: "DrugName Dosage. Instructions."
        # Dosage starts at the first occurrence of a numeric dosage pattern
        # e.g. "40 მგ", "0,4მგ", "10/1,5/10"
        dosage_start = re.search(
            r"\s+\d[\d,./]*\s*(?:მგ|გ|მლ|ტაბ|კაფ|IU|ME|%|მკგ)?(?:\s|\.|$)|"
            r"\s+\d[\d/,]+(?:\s|\.|$)",
            rest,
        )
        if dosage_start:
            name = rest[: dosage_start.start()].strip()
            remainder = rest[dosage_start.start():].strip()
        else:
            # Fallback: everything before the first period is the name
            parts = rest.split(".", 1)
            name = parts[0].strip()
            remainder = parts[1].strip() if len(parts) > 1 else ""

    # Split remainder on first "." to separate dosage from instructions
    if "." in remainder:
        dosage_part, instructions_part = remainder.split(".", 1)
        dosage = dosage_part.strip()
        instructions = instructions_part.strip()
    else:
        dosage = remainder.strip()
        instructions = ""

    return Medication(
        number=number,
        name=name,
        dosage=dosage,
        instructions=instructions,
        raw=text.strip(),
    )


if __name__ == "__main__":
    sample = """1. კარდიომაგნილი - 75 მგ. 1-ტაბ, 1-ჯერ დღეში, ჭამის შემდგომ. ხანგრძლივად.
2. ლიპრიმარი - 40 მგ. 1-ტაბ, 1-ჯერ დღეში. ვახშმის  შემდგომ. ხანგრძლივად (პრეპრატის მიღებიდან  2 - თვის შემდეგ ლიპიდური სპექტრის და ღვიძლის ფერმენტების ALT/AST კონტროლი).
3. პლავიქსი - 75 მგ. 1-ტაბ, 1-ჯერ დღეში, ჭამის შემდგომ.  6 თვე+.
4. ნექსიუმი 40 მგ. 1-ტაბ 1-ჯერ დღეში, დილით უზმოდ, ჭამამდე 30 წუთით ადრე. (3 კვირა).
5. ტრიპლიქსამი 10/1,5/10 1ტაბ. 1-ჯერ, დილით, ჭამის შემდეგ.
6. ფიზიოტენზი 0,4მგ. 1ტაბ. 1-ჯერ, საღამო 21სთ."""

    meds = parse_prescription(sample)
    for med in meds:
        print(f"[{med.number}] Name: {med.name!r}")
        print(f"     Dosage: {med.dosage!r}")
        print(f"     Instructions: {med.instructions!r}")
        print()
