from pathlib import Path
from urllib.request import urlretrieve

CARPETA = Path(__file__).parent / "modelos"
CARPETA.mkdir(exist_ok=True)

MODELOS = {
    "face_detection_yunet_2023mar.onnx":
        "https://huggingface.co/opencv/face_detection_yunet/resolve/main/face_detection_yunet_2023mar.onnx",
    "face_recognition_sface_2021dec.onnx":
        "https://huggingface.co/opencv/face_recognition_sface/resolve/main/face_recognition_sface_2021dec.onnx",
}

for nombre, url in MODELOS.items():
    destino = CARPETA / nombre
    if destino.exists():
        print("Ya existe:", nombre)
        continue
    print("Descargando", nombre, "...")
    urlretrieve(url, destino)
print("Listo.")