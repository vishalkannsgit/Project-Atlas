import io
import logging
from typing import Dict, Any

from pypdf import PdfReader
from docx import Document as DocxDocument
from pptx import Presentation
from openpyxl import load_workbook

logger = logging.getLogger("atlas.metadata")


class MetadataExtractor:
    @staticmethod
    def extract_pdf_metadata(file_bytes: bytes) -> Dict[str, Any]:
        data: Dict[str, Any] = {"page_count": 0}
        try:
            reader = PdfReader(io.BytesIO(file_bytes))
            data["page_count"] = len(reader.pages)
            if reader.metadata:
                info = reader.metadata
                if info.title:
                    data["title"] = str(info.title)
                if info.author:
                    data["author"] = str(info.author)
                if info.creator:
                    data["creator"] = str(info.creator)
        except Exception as exc:
            logger.warning("Failed extracting PDF metadata: %s", exc)
        return data

    @staticmethod
    def extract_docx_metadata(file_bytes: bytes) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        try:
            doc = DocxDocument(io.BytesIO(file_bytes))
            core = doc.core_properties
            if core.title:
                data["title"] = core.title
            if core.author:
                data["author"] = core.author
            if core.created:
                data["created"] = core.created.isoformat()
            if core.modified:
                data["modified"] = core.modified.isoformat()
            data["paragraph_count"] = len(doc.paragraphs)
        except Exception as exc:
            logger.warning("Failed extracting DOCX metadata: %s", exc)
        return data

    @staticmethod
    def extract_pptx_metadata(file_bytes: bytes) -> Dict[str, Any]:
        data: Dict[str, Any] = {"slide_count": 0}
        try:
            prs = Presentation(io.BytesIO(file_bytes))
            data["slide_count"] = len(prs.slides)
            core = prs.core_properties
            if core.title:
                data["title"] = core.title
            if core.author:
                data["author"] = core.author
            if core.created:
                data["created"] = core.created.isoformat()
        except Exception as exc:
            logger.warning("Failed extracting PPTX metadata: %s", exc)
        return data

    @staticmethod
    def extract_xlsx_metadata(file_bytes: bytes) -> Dict[str, Any]:
        data: Dict[str, Any] = {"sheet_count": 0, "sheet_names": []}
        try:
            wb = load_workbook(io.BytesIO(file_bytes), read_only=True)
            data["sheet_count"] = len(wb.sheetnames)
            data["sheet_names"] = wb.sheetnames
            core = wb.properties
            if core and core.creator:
                data["author"] = core.creator
            wb.close()
        except Exception as exc:
            logger.warning("Failed extracting XLSX metadata: %s", exc)
        return data

    def extract(self, file_format: str, file_bytes: bytes) -> Dict[str, Any]:
        """
        Routes the in-memory byte buffer to the corresponding parser.
        Falls back to an empty dictionary on error or unsupported format.
        """
        fmt = file_format.lower().lstrip(".")
        if fmt == "pdf":
            return self.extract_pdf_metadata(file_bytes)
        elif fmt == "docx":
            return self.extract_docx_metadata(file_bytes)
        elif fmt == "pptx":
            return self.extract_pptx_metadata(file_bytes)
        elif fmt == "xlsx":
            return self.extract_xlsx_metadata(file_bytes)
        return {}


metadata_extractor = MetadataExtractor()