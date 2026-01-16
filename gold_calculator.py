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

    net_gold_weight = round(gross_weight_gms - stone_weight_gms,2)
    pure_gold_weight = round(net_gold_weight * (purity_percentage / Decimal("100")),2)
    gross_amount = round(pure_gold_weight * gold_rate_per_gm,2)
    #net_amount = round(gross_amount - deductions,2)
    net_amount = round(gross_amount - (gross_amount * (deductions / Decimal("100"))),2)

    return {
        "net_gold_weight": net_gold_weight,
        "pure_weight": pure_gold_weight,
        "deductions": deductions,
        "gross_amount": gross_amount,
        "net_amount": net_amount

    }