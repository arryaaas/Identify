import io
import os
import re
import cv2
import json
import tempfile
import functions_framework
from flask import make_response
from itertools import groupby
from google.cloud import vision
from werkzeug.utils import secure_filename

# Setting the environment variable
# - Uncomment the code below (line 16) when testing is done locally
# - Comment the code below (line 16) when deployed in Google Cloud Functions
# os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "./serviceAccountKey.json"

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg"}

PATTERN = "|".join([
    "\u039d\u0399\u039a", "nik", "nama", "tempat / tgl lahir", "tempat", 
    "tgl", "lahir", "jenis kelamin", "jenis", "kelamin", "gol . darah", 
    "gol darah", "gol", "darah", "alamat", "rt / rw", "rt", "rw", "bt", 
    "bw", "kel / desa", "kev / desa", "kel", "desa", "kecamatan", "agama", 
    "status perkawinan", "status", "perkawinan", "pekerjaan", "pekeriaan", 
    "pekenaan", "kewarganegaraan", "berlaku hingga", "berlaku", "hingga"
])

# Function to check if the uploaded file extension is included in the 
# list of allowed file extensions
def allowed_file(file_name):
    return "." in file_name and \
        file_name.split(".", 1)[1].lower() in ALLOWED_EXTENSIONS

# Function to get the path of a file that is in a temporary directory
def get_file_path(file_name):
    file_name = secure_filename(file_name)
    return os.path.join(tempfile.gettempdir(), file_name)

# Function to apply grayscale and threshold methods to images (E-KTP)
def preprocessing(file_path):
    img = cv2.imread(file_path)
    grayscale = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(grayscale, 127, 255, cv2.THRESH_TRUNC)
    cv2.imwrite(file_path, thresh)

# Function to detect all the text in the image (E-KTP) using the Google 
# Cloud Vision API with the Optical Character Recognition method
def detect_text(file_path):
    # Read the images in the temporary directory
    with io.open(file_path, "rb") as image_file:
        content = image_file.read()

    image = vision.Image(content=content)

    # Detect text on image using Google Cloud Vision API
    client = vision.ImageAnnotatorClient()
    response = client.text_detection(image=image)
    annotations = response.text_annotations

    # Create a new array that stores the labels and coordinates (x, y) 
    # of the bottom left vertex in the bounding box
    annotations = list(map(
        lambda z: {
            "label": z.description,
            "x": z.bounding_poly.vertices[3].x,
            "y": int(z.bounding_poly.vertices[3].y / 10),
        },
        annotations[1:]
    ))

    # Sort array by y coordinate
    annotations = sorted(annotations, key=lambda z: z["y"])

    # Equalizes y coordinates for easy grouping
    reference = 0
    for annotation in annotations:
        vertices_y = [reference-1, reference, reference+1]
        if annotation["y"] not in vertices_y:
            reference = annotation["y"]
        annotation["y"] = reference

    # Group array by y coordinate, then sort it by x coordinate
    groups = []
    for _, group in groupby(annotations, key=lambda z: z["y"]):
        group = sorted(group, key=lambda z: z["x"])
        groups.append((list(group)))

    # Move the array group that has only 1 item to the previous 
    # array group, then delete it
    for i in range(len(groups)):
        if len(groups[i]) == 1:
            groups[i-1].append(groups[i][0])

    groups = list(filter(lambda z: len(z) != 1, groups))

    # Clear text to retrieve important information on E-KTP
    texts = []
    for group in groups:
        text = " ".join(map(lambda z: z["label"], group))
        text = re.sub(PATTERN, "", text, flags=re.IGNORECASE)
        text = text.replace(" , ", ", ").strip()
        text = text.replace(" - ", "-").strip()
        text = text.replace(" / ", "/").strip()
        text = text.replace(":", "").strip()
        texts.append(text.strip())

    return texts

# Function to extract E-KTP data
def extract_data(texts):
    # Assign a value to each attribute in E-KTP
    data = {
        "province": texts[0],
        "district": texts[1],
        "id_number": texts[2],
        "name": texts[3],
        "place_date_of_birth": texts[4],
        "gender": texts[5],
        "blood_type": "-",
        "address": texts[6],
        "neighborhood": texts[7],
        "village": texts[8],
        "subdistrict": texts[9],
        "religion": texts[10],
        "marital_status": texts[11],
        "occupation": texts[12],
        "nationality": "WNI",
        "valid_thru": texts[14],
    }

    # Extract data on marital status attribute
    if "BELUM" in texts[11] and "KAWIN" in texts[11]:
        data["marital_status"] = "BELUM KAWIN"
    elif "CERAI" in texts[11] and "HIDUP" in texts[11]:
        data["marital_status"] = "CERAI HIDUP"
    elif "CERAI" in texts[11] and "MATI" in texts[11]:
        data["marital_status"] = "CERAI MATI"
    else:
        data["marital_status"] = "KAWIN"

    # Extract data on occupation attribute
    if "PELAJAR/MAHASISWA" in texts[12]:
        data["occupation"] = "PELAJAR/MAHASISWA"
    elif "KARYAWAN SWASTA" in texts[12]:
        data["occupation"] = "KARYAWAN SWASTA"
    elif "PEGAWAI NEGERI" in texts[12]:
        data["occupation"] = "PEGAWAI NEGERI"
    elif "WIRASWASTA" in texts[12]:
        data["occupation"] = "WIRASWASTA"
    else:
        data["occupation"] = texts[12]

    # Extract data on valid thru attribute
    if "SEUMUR HIDUP" in texts[14]:
        data["valid_thru"] = "SEUMUR HIDUP"
    else:
        data["valid_thru"] = re.sub(
            r"[a-z]", "", texts[12], flags=re.IGNORECASE
        ).strip()

    return data

# Function to generate response
def generate_response(content, status_code):
    response = make_response(
        json.dumps(content, sort_keys=False), status_code
    )
    response.headers["Content-Type"] = "application/json"
    return response

# Fucntion to parse a multipart/form-data upload request
@functions_framework.http
def parse_multipart(request):
    if request.method != "POST":
        return generate_response({
            "status": "Method not allowed",
            "message": "Only POST method is allowed",
        }, 400)

    if "file" not in request.files:
        return generate_response({
            "status": "Bad request",
            "message": "No file part",
        }, 400)

    file = request.files.get("file")

    print(file.filename, type(file.filename))

    if file.filename == "":
        return generate_response({
            "status": "Bad request",
            "message": "No selected file",
        }, 400)

    if not (file and allowed_file(file.filename)):
        return generate_response({
            "status": "Not acceptable",
            "message": \
                "Only files with extension png, jpg, jpeg are allowed",
        }, 406)

    # Save images in temporary directory
    file_path = get_file_path(file.filename)
    file.save(file_path)

    # Optical Character Recognition on E-KTP
    preprocessing(file_path)
    texts = detect_text(file_path)
    data = extract_data(texts)

    # Remove image from temporary directory
    os.remove(file_path)

    return generate_response({
        "status": "Ok",
        "message": "Successfully extract E-KTP data",
        "data": data
    }, 200)

# Run the following command (line 223) in terminal to run program locally
# functions-framework --target parse_multipart --debug