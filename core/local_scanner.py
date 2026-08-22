import os

class LocalScanner:
    BASE_DIR = "/storage/emulated/0/Download/Animes"

    @staticmethod
    def get_local_animes():
        """Retorna uma lista de animes encontrados nas pastas locais do celular"""
        if not os.path.exists(LocalScanner.BASE_DIR):
            return []

        animes = []
        video_extensions = ('.mp4', '.mkv', '.avi', '.webm')

        try:
            # Lista todas as pastas dentro de /Download/Animes
            folders = [f for f in os.listdir(LocalScanner.BASE_DIR) if os.path.isdir(os.path.join(LocalScanner.BASE_DIR, f))]

            for folder_name in folders:
                folder_path = os.path.join(LocalScanner.BASE_DIR, folder_name)
                episodes = []

                # Procura os arquivos de vídeo dentro da pasta do anime
                for root, _, files in os.walk(folder_path):
                    for file in sorted(files):
                        if file.lower().endswith(video_extensions):
                            episodes.append({
                                'title': os.path.splitext(file)[0],
                                'path': os.path.join(root, file)
                            })

                animes.append({
                    'title': folder_name,
                    'folder_path': folder_path,
                    'episodes': episodes,
                    'total_episodes': len(episodes)
                })
        except Exception as e:
            print(f"Erro ao ler diretório: {e}")

        return animes
