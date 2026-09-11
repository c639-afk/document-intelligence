# AI / Tool Usage Declaration

## Purpose

This document declares the AI models, OCR tools, libraries, and AI-assisted development tools used in the Document Intelligence Platform.

## AI and Tooling Used

### 1. Google Gemini

**Purpose:** Multimodal financial document extraction.

Google Gemini is used by the backend extraction service to analyze the original uploaded document together with supporting OCR/native PDF text context.

It is responsible for:
- Identifying the document type.
- Extracting meaningful visible fields.
- Extracting invoice line items.
- Extracting structured tables and comparative periods.
- Returning evidence and page numbers where available.
- Returning missing values as `null`.
- Following the project's fixed `ExtractionResponse` schema.
- Avoiding unsupported inference.

The application uses the `google-genai` Python SDK. The project uses the **Google Gemini API through its free tier** for AI-based document extraction.

### 2. Tesseract OCR

**Purpose:** Text extraction from scanned/image documents.

Tesseract is used for:
- JPG/JPEG/PNG documents.
- Scanned PDFs where native PDF text extraction is insufficient.

OCR is performed locally by the backend. The application records whether OCR was used during processing.

### 3. pypdf

**Purpose:** Native PDF text extraction.

For PDFs containing sufficient native text, `pypdf` is used before falling back to OCR.

### 4. pdf2image and Pillow

**Purpose:** Converting PDF pages to images for OCR and handling image documents.

`pdf2image` converts scanned PDF pages into images, while Pillow is used for image loading/processing.

### 5. ChatGPT / AI-assisted development

ChatGPT was used as a development assistance tool during the project for tasks such as:
- Reviewing the assignment requirements.
- Planning the application architecture.
- Assisting with implementation and debugging.
- Reviewing validation logic and test coverage.
- Reviewing deployment configuration.
- Assisting with README and submission documentation.
- Creating supporting documentation artifacts such as the architecture diagram and presentation content.

The final application code, configuration, tests, deployment, and integration were reviewed and tested as part of the project development process.

## AI Decision Boundaries

AI extraction is intentionally separated from deterministic financial validation.

Gemini is used for document understanding and structured extraction. Financial calculations are performed by the backend validation service using deterministic `Decimal` arithmetic and a tolerance of `0.01`.

The system does not ask the LLM to decide whether a financial calculation is correct. Instead, extracted values are passed to independent validation logic.

Missing information is not invented. Where required inputs for a validation are unavailable, the validation result can be `NOT_APPLICABLE`.

## Human Responsibility

AI tools were used to assist development and document understanding, but the project implementation includes deterministic validation, automated tests, API testing, deployment checks, and persistence verification.

The developer is responsible for reviewing the resulting implementation and ensuring that the submitted system meets the assignment requirements.

## Known AI-Related Limitation

Gemini API availability is subject to model/API quotas and rate limits. If the configured Gemini daily quota is exhausted, the API returns a structured `GEMINI_QUOTA_EXCEEDED` error rather than fabricating an extraction result.

For production use, this would be addressed with appropriate quota management, model capacity planning, retries/backoff where appropriate, monitoring, and an operational fallback strategy.
