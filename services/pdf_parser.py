"""
PDF請求書パーサー。
- sellerbank: セラーバンク（猫の手/国際送料請求書） → 合計金額 ÷ 数量 = 単位送料
- ebi: 就労支援施設エビ（検品費用請求書） → 1商品あたり費用
"""
import re
import pdfplumber
from pathlib import Path
from config.settings import AppConfig


def parse_invoice(pdf_path: str, invoice_type: str, quantity: int = 1) -> dict:
    """
    PDF請求書を解析して単位費用を返す。

    Args:
        pdf_path: PDFファイルのパス
        invoice_type: "sellerbank" or "ebi"
        quantity: 商品数量（sellerbank用）

    Returns:
        {
            "type": str,
            "total_amount": float,
            "quantity": int,
            "unit_cost": float,
            "currency": str,
            "raw_text": str,  # デバッグ用
        }
    """
    if AppConfig.TEST_MODE:
        if invoice_type == "sellerbank":
            total = 45000.0
            unit = round(total / quantity, 2)
            return {
                "type": "sellerbank",
                "total_amount": total,
                "quantity": quantity,
                "unit_cost": unit,
                "currency": "JPY",
                "raw_text": "（テストモード）",
            }
        else:
            return {
                "type": "ebi",
                "total_amount": None,
                "quantity": None,
                "unit_cost": 30.0,
                "currency": "JPY",
                "raw_text": "（テストモード）",
            }

    pdf_path = str(pdf_path)
    with pdfplumber.open(pdf_path) as pdf:
        full_text = "\n".join(
            page.extract_text() or "" for page in pdf.pages
        )

    if invoice_type == "sellerbank":
        return _parse_sellerbank(full_text, quantity)
    elif invoice_type == "ebi":
        return _parse_ebi(full_text)
    else:
        raise ValueError(f"不明な請求書タイプ: {invoice_type}")


def _parse_sellerbank(text: str, quantity: int) -> dict:
    """
    セラーバンク（国際送料）請求書のパース。
    合計金額を数量で割って単位送料を算出。
    """
    total = _extract_total_amount(text)
    unit_cost = total / quantity if quantity > 0 else 0.0

    return {
        "type": "sellerbank",
        "total_amount": total,
        "quantity": quantity,
        "unit_cost": round(unit_cost, 2),
        "currency": "JPY",
        "raw_text": text[:500],
    }


def _parse_ebi(text: str) -> dict:
    """
    就労支援施設エビ（検品費用）請求書のパース。
    1商品あたりの費用を抽出。
    """
    # まず「単価」「1個あたり」などのパターンを探す
    unit_patterns = [
        r"単価[：:\s]*[¥￥]?\s*([\d,]+)",
        r"1個[あたり当り]*[：:\s]*[¥￥]?\s*([\d,]+)",
        r"per\s*item[：:\s]*[¥￥]?\s*([\d,]+)",
        r"検品単価[：:\s]*[¥￥]?\s*([\d,]+)",
    ]
    for pattern in unit_patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            unit_cost = float(m.group(1).replace(",", ""))
            return {
                "type": "ebi",
                "total_amount": None,
                "quantity": None,
                "unit_cost": unit_cost,
                "currency": "JPY",
                "raw_text": text[:500],
            }

    # 単価が見つからなければ合計÷数量で試みる
    total = _extract_total_amount(text)
    qty = _extract_quantity(text)
    unit_cost = total / qty if qty and qty > 0 else total

    return {
        "type": "ebi",
        "total_amount": total,
        "quantity": qty,
        "unit_cost": round(unit_cost, 2),
        "currency": "JPY",
        "raw_text": text[:500],
    }


def _extract_total_amount(text: str) -> float:
    """テキストから合計金額を抽出する。"""
    patterns = [
        r"合計[金額]*[：:\s]*[¥￥]?\s*([\d,]+)",
        r"総合計[：:\s]*[¥￥]?\s*([\d,]+)",
        r"請求金額[：:\s]*[¥￥]?\s*([\d,]+)",
        r"[Tt]otal[：:\s]*[¥￥]?\s*([\d,]+)",
        r"TOTAL[：:\s]*[¥￥]?\s*([\d,]+)",
        r"Amount[：:\s]*[¥￥]?\s*([\d,]+)",
        # 最終手段：最大の数値
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            return float(m.group(1).replace(",", ""))

    # 数値をすべて抽出して最大値を合計金額と推定
    numbers = re.findall(r"[\d,]{3,}", text)
    if numbers:
        values = [float(n.replace(",", "")) for n in numbers]
        return max(values)
    return 0.0


def _extract_quantity(text: str) -> int | None:
    """テキストから数量を抽出する。"""
    patterns = [
        r"数量[：:\s]*([\d,]+)\s*[個点件]",
        r"([\d,]+)\s*[個点件]\s*[×x]",
        r"[Qq]uantity[：:\s]*([\d,]+)",
        r"[Qq]ty[：:\s]*([\d,]+)",
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            return int(m.group(1).replace(",", ""))
    return None
