from PIL import Image
import io
import base64

def get_image_format(image_bytes):
    try:
        img = Image.open(io.BytesIO(image_bytes))
        return img.format.lower()
    except:
        return None

# Ejemplo de uso:
if __name__ == "__main__":
    with open("ruta/a/tu/imagen.jpg", "rb") as f:
        formato = get_image_format(f.read())
        print(f"Formato detectado: {formato}")






