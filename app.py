"""
利益計算アプリ - メインエントリーポイント
"""
from pathlib import Path
from flask import Flask, render_template, send_from_directory
from config.settings import AppConfig
from models.db import db

# Blueprints
from routes.api_1688 import bp as bp_1688
from routes.api_amazon import bp as bp_amazon
from routes.api_sale_monster import bp as bp_sm
from routes.api_customs import bp as bp_customs
from routes.api_pdf import bp as bp_pdf
from routes.api_profit import bp as bp_profit
from routes.api_research import bp as bp_research
from routes.api_oem import bp as bp_oem


def create_app() -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")

    # 設定
    app.config["SECRET_KEY"] = AppConfig.SECRET_KEY
    app.config["SQLALCHEMY_DATABASE_URI"] = AppConfig.DATABASE_URI
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["MAX_CONTENT_LENGTH"] = AppConfig.MAX_UPLOAD_BYTES
    app.config["UPLOAD_FOLDER"] = AppConfig.UPLOAD_FOLDER

    # DB初期化
    db.init_app(app)
    with app.app_context():
        db.create_all()

    # Blueprint登録
    app.register_blueprint(bp_1688)
    app.register_blueprint(bp_amazon)
    app.register_blueprint(bp_sm)
    app.register_blueprint(bp_customs)
    app.register_blueprint(bp_pdf)
    app.register_blueprint(bp_profit)
    app.register_blueprint(bp_research)
    app.register_blueprint(bp_oem)

    # メインページ
    @app.route("/")
    def index():
        return render_template("index.html", config={"TEST_MODE": AppConfig.TEST_MODE})

    # 一時画像の静的配信（Playwrightのスクリーンショット）
    @app.route("/static/img/tmp/<path:filename>")
    def tmp_image(filename):
        tmp_dir = Path(__file__).parent / "static" / "img" / "tmp"
        return send_from_directory(tmp_dir, filename)

    return app


if __name__ == "__main__":
    app = create_app()
    print("=" * 50)
    print("利益計算アプリ起動中...")
    print("ブラウザで http://localhost:5000 を開いてください")
    print("=" * 50)
    app.run(debug=AppConfig.DEBUG, host="0.0.0.0", port=5000)
