import os
import re

class LocalScanner:
    BASE_DIR = "/storage/emulated/0/Download/Animes"

    @staticmethod
    def _clean_base_title(folder_name: str) -> str:
        """Extrai o nome principal do anime removendo marcadores de temporada/parte"""
        # Remove sufixos como Season 1, 2nd Season, Part 2, Dublado, OVA, etc.
        patterns = [
            r'(?i)\s+season\s+\d+.*',
            r'(?i)\s+\d+nd\s+season.*',
            r'(?i)\s+\d+rd\s+season.*',
            r'(?i)\s+\d+th\s+season.*',
            r'(?i)\s+part\s+\d+.*',
            r'(?i)\s+dublado.*',
            r'(?i)\s+ova.*'
        ]
        clean_name = folder_name
        for pattern in patterns:
            clean_name = re.sub(pattern, '', clean_name)
        return clean_name.strip()

    @staticmethod
    def get_local_animes_grouped():
        """Agrupa pastas relacionadas (temporadas/OVAs) sob o mesmo anime principal"""
        if not os.path.exists(LocalScanner.BASE_DIR):
            return []

        grouped_animes = {}
        video_extensions = ('.mp4', '.mkv', '.avi', '.webm')

        try:
            folders = [f for f in os.listdir(LocalScanner.BASE_DIR) if os.path.isdir(os.path.join(LocalScanner.BASE_DIR, f))]

            for folder_name in folders:
                folder_path = os.path.join(LocalScanner.BASE_DIR, folder_name)
                episodes = []

                for root, _, files in os.walk(folder_path):
                    for file in sorted(files):
                        if file.lower().endswith(video_extensions):
                            episodes.append({
                                'title': os.path.splitext(file)[0],
                                'path': os.path.join(root, file)
                            })

                if not episodes:
                    continue

                main_title = LocalScanner._clean_base_title(folder_name)

                # Identifica se é uma temporada específica, parte ou OVA
                season_label = folder_name.replace(main_title, '').strip()
                if not season_label:
                    season_label = "Temporada 1"

                season_data = {
                    'season_name': season_label,
                    'folder_path': folder_path,
                    'episodes': episodes
                }

                if main_title in grouped_animes:
                    grouped_animes[main_title]['seasons'].append(season_data)
                else:
                    grouped_animes[main_title] = {
                        'main_title': main_title,
                        'seasons': [season_data]
                    }

        except Exception as e:
            print(f"Erro ao agrupar animes: {e}")

        return list(grouped_animes.values())
