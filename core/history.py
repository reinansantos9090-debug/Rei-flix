import json
import os

class HistoryManager:
    DATA_FILE = "/storage/emulated/0/Download/reiflix_history.json"

    @staticmethod
    def _load_data() -> dict:
        if os.path.exists(HistoryManager.DATA_FILE):
            try:
                with open(HistoryManager.DATA_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {"progress": {}, "durations": {}, "favorites": []}

    @staticmethod
    def _save_data(data: dict):
        try:
            with open(HistoryManager.DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception:
            pass

    @classmethod
    def save_position(cls, video_path: str, position_seconds: float, total_duration_seconds: float = 0):
        """Salva a posição atual e a duração total do vídeo"""
        data = cls._load_data()
        data["progress"][video_path] = position_seconds
        if total_duration_seconds > 0:
            data["durations"][video_path] = total_duration_seconds
        cls._save_data(data)

    @classmethod
    def get_progress_data(cls, video_path: str) -> dict:
        """Retorna os segundos assistidos, a duração total e a porcentagem (0.0 a 1.0)"""
        data = cls._load_data()
        pos = data["progress"].get(video_path, 0.0)
        dur = data["durations"].get(video_path, 0.0)
        
        ratio = (pos / dur) if dur > 0 else 0.0
        is_completed = ratio >= 0.9  # Considera visto se assistiu 90% ou mais

        return {
            "position": pos,
            "duration": dur,
            "ratio": min(ratio, 1.0),
            "completed": is_completed
        }

    @classmethod
    def toggle_favorite(cls, anime_folder: str) -> bool:
        data = cls._load_data()
        if anime_folder in data["favorites"]:
            data["favorites"].remove(anime_folder)
            is_fav = False
        else:
            data["favorites"].append(anime_folder)
            is_fav = True
        cls._save_data(data)
        return is_fav

    @classmethod
    def is_favorite(cls, anime_folder: str) -> bool:
        data = cls._load_data()
        return anime_folder in data["favorites"]
