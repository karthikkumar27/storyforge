import os
from flask import Flask, jsonify
from dotenv import load_dotenv
from orchestrator import run_pipeline

load_dotenv()

app = Flask(__name__)


@app.route("/run", methods=["POST"])
def run():
    try:
        result = run_pipeline()
        return jsonify(result), 200
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
