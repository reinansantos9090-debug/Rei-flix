import json
import os

class AppStorage:
    CONFIG_FILE = "/storage/emulated/0/Download/reiflix_data.json" if os.path.exists("/storage/emulated/0/Download") else "reiflix_data.json"

    @staticmethod
    def load_data():
        if os.path.exists(AppStorage.CONFIG_FILE):
            try:
                with open(AppStorage.CONFIG_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {"watching": [], "favorites": [], "completed": []}

    @staticmethod
    def save_data(data):
        try:
            with open(AppStorage.CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception:
            pass

