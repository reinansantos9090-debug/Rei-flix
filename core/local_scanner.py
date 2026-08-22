import os

class LocalScanner:
    @staticmethod
    def get_local_videos():
        """Varre pastas comuns do Android em busca de vídeos"""
        video_extensions = ('.mp4', '.mkv', '.avi', '.webm')
        found_videos = []
        
        # Diretórios comuns de armazenamento no Android
        search_paths = [
            "/storage/emulated/0/Download",
            "/storage/emulated/0/Movies",
            "/storage/emulated/0/Pictures",
            "/sdcard/Download",
            "/sdcard/Movies"
        ]
        
        for path in search_paths:
            if os.path.exists(path):
                try:
                    for root, dirs, files in os.walk(path):
                        for file in files:
                            if file.lower().endswith(video_extensions):
                                full_path = os.path.join(root, file)
                                # Limpa o nome do arquivo para facilitar a busca da capa
                                clean_name = os.path.splitext(file)[0].replace('_', ' ').replace('.', ' ')
                                found_videos.append({
                                    'title': clean_name,
                                    'filename': file,
                                    'path': full_path
                               ভেরid': abs(hash(full_path)) # ID único para o arquivo
                                })
                except Exception:
                    pass
                    
        return found_videos

