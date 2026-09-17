import re
from ..domain.enums import DocumentType, EntityType
from ..domain.models import Entity, ParsedDocument
from .metadata_extractor import MetadataExtractor
from .entity_extractor import EntityExtractor


class RuleBasedMetadataExtractor(MetadataExtractor):
    """Dependency-free baseline extractor. Replace/augment with an LLM adapter later."""

    async def extract(self, document: ParsedDocument) -> dict:
        text = document.text
        lowered = text.lower()
        doc_type = DocumentType.UNKNOWN
        if "guideline" in lowered or "clinical practice guideline" in lowered:
            doc_type = DocumentType.GUIDELINE
        elif "standard operating procedure" in lowered or re.search(r"\bsop\b", lowered):
            doc_type = DocumentType.SOP
        elif "advisory" in lowered or "public health alert" in lowered:
            doc_type = DocumentType.ADVISORY
        elif document.file_type.lower() in {"html", "htm"}:
            doc_type = DocumentType.WEB_PAGE
        elif "abstract" in lowered or "methods" in lowered:
            doc_type = DocumentType.RESEARCH_ARTICLE
        elif "report" in lowered:
            doc_type = DocumentType.REPORT

        keywords = self._keywords(text)
        return {
            "title": document.title,
            "publisher": document.publisher,
            "publication_date": document.published_at,
            "version": document.version,
            "language": document.language,
            "keywords": keywords,
            "document_type": doc_type,
            "authors": document.authors,
            "license": document.license,
        }

    @staticmethod
    def _keywords(text: str) -> list[str]:
        # Conservative candidate extraction; avoids pretending arbitrary words are authoritative keywords.
        candidates = re.findall(r"\b[A-Z][A-Za-z0-9-]{3,}(?:\s+[A-Z][A-Za-z0-9-]{2,}){0,2}\b", text)
        seen: set[str] = set()
        result: list[str] = []
        for item in candidates:
            normalized = item.strip()
            key = normalized.casefold()
            if key not in seen and len(result) < 20:
                seen.add(key)
                result.append(normalized)
        return result


class RuleBasedEntityExtractor(EntityExtractor):
    """Small deterministic baseline; production LLM/NLP adapters can implement EntityExtractor."""

    PATTERNS = {
        EntityType.DISEASE: [r"\btype 2 diabetes(?: mellitus)?\b", r"\bhypertension\b", r"\basthma\b", r"\bcancer\b"],
        EntityType.DRUG: [r"\binsulin\b", r"\bmetformin\b", r"\baspirin\b", r"\bamoxicillin\b"],
        EntityType.PROCEDURE: [r"\bMRI\b", r"\bCT scan\b", r"\bsurgery\b", r"\bbiopsy\b"],
        EntityType.LAB_TEST: [r"\bHbA1c\b", r"\bcomplete blood count\b", r"\bCBC\b", r"\bglucose test\b"],
        EntityType.MEDICAL_DEVICE: [r"\bventilator\b", r"\bpacemaker\b", r"\binsulin pump\b"],
    }

    async def extract(self, document: ParsedDocument) -> list[Entity]:
        entities: list[Entity] = []
        for entity_type, patterns in self.PATTERNS.items():
            for pattern in patterns:
                for match in re.finditer(pattern, document.text, re.IGNORECASE):
                    name = match.group(0)
                    entities.append(Entity(
                        name=name,
                        normalized_name=name.casefold(),
                        entity_type=entity_type,
                        confidence=0.80,
                        start=match.start(),
                        end=match.end(),
                    ))
        return self._deduplicate(entities)

    @staticmethod
    def _deduplicate(entities: list[Entity]) -> list[Entity]:
        seen: set[tuple[str, EntityType]] = set()
        output: list[Entity] = []
        for entity in entities:
            key = (entity.normalized_name or entity.name.casefold(), entity.entity_type)
            if key not in seen:
                seen.add(key)
                output.append(entity)
        return output
