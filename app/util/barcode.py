# app/util/barcode.py
def ean13_checksum(d12: str) -> str:
    if len(d12) != 12 or not d12.isdigit():
        raise ValueError("EAN-13 body must be 12 digits")
    s_odd  = sum(int(d12[i]) for i in range(0, 12, 2))
    s_even = sum(int(d12[i]) for i in range(1, 12, 2))
    c = (10 - ((s_odd + 3*s_even) % 10)) % 10
    return str(c)

def is_valid_ean13(code: str) -> bool:
    return len(code) == 13 and code.isdigit() and ean13_checksum(code[:12]) == code[-1]

def next_internal_ean(get_next_number: callable, prefix: str = "299") -> str:
    """
    prefix '299' pentru uz intern (nu oficial GS1, dar scannabil).
    get_next_number(): funcție care întoarce un int incremental (vezi sequences).
    """
    n = get_next_number()              # ex: 123456
    body = f"{prefix}{n:09d}"          # 3 + 9 = 12 cifre
    return body + ean13_checksum(body)
