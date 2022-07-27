# Identify

Optical Character Recognition (OCR) to extract Indonesian Identity Card (E-KTP) data using Google Cloud Platform.

## Architecture

Soon...

## Deployment

```shell
gcloud services enable \
  cloudbuild.googleapis.com \
  cloudfunctions.googleapis.com \
  vision.googleapis.com
```

```shell
gcloud config set functions/region asia-southeast2
```

```shell
gcloud functions deploy ocr-service \                                                                                                      
  --runtime python39 \
  --trigger-http \
  --entry-point parse_multipart \
  --allow-unauthenticated
```

## License

Distributed under the MIT License. See `LICENSE` for more information.

## Contact

Mochammad Arya Salsabila - Aryasalsabila789@gmail.com
