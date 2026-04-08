import os
from pathlib import Path
from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename
from services.pdf_parser import parse_invoice

bp = Blueprint("api_pdf", __name__, url_prefix="/api/pdf")

ALLOWED_EXTENSIONS = {"pdf"}


def _allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@bp.route("/parse", methods=["POST"])
def parse():
    """
    PDF請求書を解析して単位費用を返す。

    Form data:
        file: PDFファイル
        invoice_type: "sellerbank" or "ebi"
        quantity: 数量（sellerbank用、整数）
    """
    if "file" not in request.files:
        return jsonify({"error": "ファイルが選択されていません"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "ファイルが選択されていません"}), 400

    if not _allowed_file(file.filename):
        return jsonify({"error": "PDFファイルのみ対応しています"}), 400

    # ファイルサイズチェック
    file.seek(0, 2)
    file_size = file.tell()
    file.seek(0)
    max_size = current_app.config.get("MAX_CONTENT_LENGTH", 10 * 1024 * 1024)
    if file_size > max_size:
        return jsonify({"error": "ファイルサイズが大きすぎます（最大10MB）"}), 400

    invoice_type = request.form.get("invoice_type", "sellerbank")
    if invoice_type not in ("sellerbank", "ebi"):
        return jsonify({"error": "invoice_typeは 'sellerbank' または 'ebi' を指定してください"}), 400

    quantity = int(request.form.get("quantity", 1))
    if quantity < 1:
        quantity = 1

    # ファイル保存
    upload_dir = Path(current_app.config["UPLOAD_FOLDER"])
    upload_dir.mkdir(parents=True, exist_ok=True)
    filename = secure_filename(file.filename)
    save_path = upload_dir / filename
    file.save(str(save_path))

    try:
        result = parse_invoice(str(save_path), invoice_type, quantity)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": f"PDF解析に失敗しました: {str(e)}"}), 500
    finally:
        # アップロードファイルを削除（プライバシー保護）
        try:
            os.remove(str(save_path))
        except Exception:
            pass
