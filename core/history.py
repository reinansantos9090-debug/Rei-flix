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
        return {"progress": {}, "favorites": [], "completed": []}

    @staticmethod
    def _save_data(data: dict):
        try:
            with open(HistoryManager.DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception:
            pass

    @classmethod
    def save_position(cls, video_path: str, position_seconds: float):
        """Salva a posição exata em segundos de um arquivo de vídeo"""
        data = cls._load_data()
        data["progress"][video_path] = position_seconds
        cls._save_data(data)

    @classmethod
    def get_position(cls, video_path: str) -> float:
        """Retorna os segundos onde o usuário parou no vídeo"""
        data = cls._load_data()
        return data["progress"].get(video_path, 0.0)

    @classmethod
    def toggle_favorite(cls, anime_folder: str) -> bool:
        """Adiciona ou remove um anime da lista de favoritos"""
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

