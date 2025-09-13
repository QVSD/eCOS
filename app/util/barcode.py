def ean13_check_digit(body12: str) -> int:
    s_odd  = sum(int(d) for i, d in enumerate(body12, 1) if i % 2 == 1)
    s_even = sum(int(d) for i, d in enumerate(body12, 1) if i % 2 == 0)
    return (10 - ((s_odd + 3 * s_even) % 10)) % 10

def ean8_check_digit(body7: str) -> int:
    s_odd  = int(body7[0]) + int(body7[2]) + int(body7[4]) + int(body7[6])
    s_even = int(body7[1]) + int(body7[3]) + int(body7[5])
    return (10 - ((3 * s_odd + s_even) % 10)) % 10

def upca_check_digit(body11: str) -> int:
    s_odd  = sum(int(d) for i, d in enumerate(body11, 1) if i % 2 == 1)
    s_even = sum(int(d) for i, d in enumerate(body11, 1) if i % 2 == 0)
    return (10 - ((3 * s_odd + s_even) % 10)) % 10

def normalize_barcode(raw: str) -> str:
    code = raw.strip()
    if not code.isdigit():
        raise ValueError("Codul de bare trebuie să conțină doar cifre.")
    if len(set(code)) == 1:
        raise ValueError("Cod invalid (toate cifrele identice).")

    if len(code) == 13:
        if ean13_check_digit(code[:12]) != int(code[12]):
            raise ValueError("EAN-13 invalid (cifra de control).")
        return code
    if len(code) == 8:
        if ean8_check_digit(code[:7]) != int(code[7]):
            raise ValueError("EAN-8 invalid (cifra de control).")
        return code
    if len(code) == 12:  # UPC-A -> EAN-13 cu prefix 0
        if upca_check_digit(code[:11]) != int(code[11]):
            raise ValueError("UPC-A invalid (cifra de control).")
        ean13 = "0" + code
        if ean13_check_digit(ean13[:12]) != int(ean13[12]):
            raise ValueError("Conversie UPC-A→EAN-13 eșuată.")
        return ean13

    raise ValueError("Lungime cod invalidă (accept: 8, 12 sau 13 cifre).")
