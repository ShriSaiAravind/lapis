def run_ui_mode():
    try:
        from ui.server import run_ui
    except ImportError:
        print("Error: Flask isn't installed. Run: pip install flask")
        return
    print("Starting Lapis UI at http://127.0.0.1:5000 ...")
    run_ui()