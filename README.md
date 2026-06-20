# Book Image OCR PDF

Turn scanned, image-only PDFs into searchable PDFs while preserving the original page appearance.

The application adds an invisible OCR text layer to each page. The scanned page remains visible and unchanged, so text can be searched, selected, and copied without reconstructing the book layout.

## Download and run

Download the Windows release ZIP, extract it, and run `BookImageOCR.exe`.

The release bundles Tesseract OCR plus Korean, English, and Traditional Chinese (Hanja) language data. Users do not need to install Python or Tesseract separately.

## Features

- Searchable and selectable Korean, English, and Hanja text
- Original compressed page images are retained to keep output files small
- Conservative graphic detection leaves charts, screenshots, and illustrations out of the OCR layer
- A second OCR check prevents large body-text regions from being mistakenly classified as graphics
- Desktop progress display with percentage, elapsed time, and estimated time remaining

## For developers

```powershell
pip install -r requirements.txt
python app.py
```

To create a portable Windows build that includes OCR runtime files:

```powershell
.\build_windows.ps1
```

The result is written to `dist\BookImageOCR`. Zip that folder as a release asset.

## Privacy and copyright

OCR runs locally on the user's computer. The application does not upload PDF files or recognized text.

Users are responsible for ensuring that they have the right to process, copy, and distribute the documents they use with this application.

## License

This project is MIT licensed. Bundled OCR components and language data retain their own licenses; see [NOTICE.md](NOTICE.md).
