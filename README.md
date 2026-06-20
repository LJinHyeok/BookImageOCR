# Book Image OCR PDF

[한국어](#한국어) | [English](#english)

## 한국어

스캔본이나 캡처 이미지로만 이루어진 PDF를 검색·드래그·복사가 가능한 PDF로 바꿉니다. 원래 페이지 이미지는 그대로 유지하고, OCR로 인식한 텍스트 레이어만 추가합니다.

### 다운로드 및 실행

Windows 릴리스 ZIP을 내려받아 압축을 풀고 `BookImageOCR.exe`를 실행하세요.

배포본에는 Tesseract OCR과 한국어, 영어, 한자(번체 중국어) 인식 데이터가 포함되어 있습니다. Python이나 Tesseract를 따로 설치할 필요가 없습니다.

### 주요 기능

- 한국어, 영어, 한자 텍스트 검색·선택·복사
- 원본 스캔 이미지를 유지해 출력 PDF 용량 최소화
- 차트, 프로그램 화면, 삽화 등의 그림 영역은 OCR 텍스트 레이어에서 보수적으로 제외
- 그림으로 잘못 분류된 긴 본문은 추가 OCR 검사 후 본문으로 복구
- 진행률, 경과 시간, 예상 남은 시간을 표시하는 데스크톱 UI
- 모든 OCR 작업을 로컬 컴퓨터에서 처리

### 개발 및 빌드

```powershell
pip install -r requirements.txt
python app.py
```

Tesseract와 언어 데이터를 포함한 Windows 포터블 앱을 만들려면:

```powershell
.\build_windows.ps1
```

결과물은 `dist\BookImageOCR`에 생성됩니다.

### 개인정보 및 저작권

PDF와 인식된 텍스트는 외부 서버로 전송되지 않습니다. 사용자는 처리·복사·배포하려는 문서에 대해 필요한 권한을 보유해야 합니다.

## English

Turn scanned, image-only PDFs into searchable PDFs while keeping the original page appearance. The application preserves the scanned page image and adds an invisible OCR text layer.

### Download and run

Download the Windows release ZIP, extract it, and run `BookImageOCR.exe`.

The release bundles Tesseract OCR with Korean, English, and Traditional Chinese language data. No separate Python or Tesseract installation is required.

### Features

- Search, select, and copy Korean, English, and Hanja text
- Reuse original compressed page images to keep output PDFs small
- Conservatively exclude charts, screenshots, and illustrations from the OCR text layer
- Re-check likely graphic regions so long body text is not accidentally excluded
- Desktop progress, elapsed-time, and ETA display
- Local-only OCR processing

### Build from source

```powershell
pip install -r requirements.txt
python app.py
```

Create the portable Windows distribution with bundled OCR runtime files:

```powershell
.\build_windows.ps1
```

The output is written to `dist\BookImageOCR`.

### Privacy and copyright

PDF files and recognized text are processed locally and are never uploaded by the application. Users are responsible for ensuring they have the right to process, copy, and distribute their documents.

## License

This project is MIT licensed. Bundled OCR components and language data retain their own licenses; see [NOTICE.md](NOTICE.md).
