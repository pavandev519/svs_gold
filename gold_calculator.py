from decimal import Decimal, ROUND_HALF_UP

def calculate_gold_estimation(
    gross_weight_gms: Decimal,
    stone_weight_gms: Decimal,
    purity_percentage: Decimal,
    gold_rate_per_gm: Decimal,
    deductions: Decimal
):
    if stone_weight_gms > gross_weight_gms:
        raise ValueError("Stone weight cannot exceed gross weight")

    purity_percentage = purity_percentage.quantize(Decimal('1'), rounding='ROUND_FLOOR')
    deductions = deductions.quantize(Decimal('0.01'), rounding='ROUND_DOWN')
    gross_weight_gms = gross_weight_gms.quantize(Decimal('0.01'), rounding='ROUND_DOWN')
    stone_weight_gms = stone_weight_gms.quantize(Decimal('0.01'), rounding='ROUND_DOWN')

    net_gold_weight = gross_weight_gms - stone_weight_gms
    pure_gold_weight = net_gold_weight * (purity_percentage / Decimal("100"))
    gross_amount = pure_gold_weight * gold_rate_per_gm
    net_amount = gross_amount - (gross_amount * (deductions / Decimal("100")))

    return {
        "net_gold_weight": net_gold_weight,
        "pure_weight": pure_gold_weight,
        "deductions": deductions,
        "gross_amount": gross_amount,
        "net_amount": net_amount
    }

    return {
        "net_gold_weight": net_gold_weight,
        "pure_weight": pure_gold_weight,
        "deductions": deductions,
        "gross_amount": gross_amount,
        "net_amount": net_amount
    }
