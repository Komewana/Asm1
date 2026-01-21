from app import create_app
from app.config import APP_TITLE, HOST, PORT, MODEL_PATH, INPUT_DIR, OUTPUT_DIR

app = create_app()

if __name__ == "__main__":
    print(f"== {APP_TITLE} ==")
    print("Model:", MODEL_PATH)
    print("Input:", INPUT_DIR)
    print("Output:", OUTPUT_DIR)
    print(f"Run: http://127.0.0.1:{PORT}")
    app.run(host=HOST, port=PORT, debug=True, threaded=True)
