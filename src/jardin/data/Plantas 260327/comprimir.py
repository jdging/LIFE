import os
from PIL import Image
from pillow_heif import register_heif_opener

# Registrar el adaptador para archivos HEIC
register_heif_opener()

# Configuración de rutas
folder_path = r'G:\My Drive\15 - Sistemas\01 - LIFE\Plantas 260327'
target_quality = 30  # Calidad baja (1-100) para que pesen muy poco
max_width = 800      # Redimensionar ayuda mucho a bajar el peso para HTML

def compress_images(directory):
    if not os.path.exists(directory):
        print(f"La ruta no existe: {directory}")
        return

    for filename in os.listdir(directory):
        if filename.lower().endswith(".heic"):
            file_path = os.path.join(directory, filename)
            
            # Quitar la extensión original y poner .webp
            name_without_ext = os.path.splitext(filename)[0]
            output_path = os.path.join(directory, f"{name_without_ext}.webp")

            try:
                with Image.open(file_path) as img:
                    # Opcional: Redimensionar si la imagen es gigante (típico de móviles)
                    if img.width > max_width:
                        ratio = max_width / float(img.width)
                        new_height = int(float(img.height) * float(ratio))
                        img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)

                    # Guardar con compresión agresiva
                    img.save(output_path, "WEBP", quality=target_quality, optimize=True)
                    print(f"Procesado: {filename} -> {name_without_ext}.webp")
            except Exception as e:
                print(f"Error al procesar {filename}: {e}")

if __name__ == "__main__":
    compress_images(folder_path)