from ..domain.models import DocumentMetadata, ParsedDocument
from ..extraction.entity_extractor import EntityExtractor
from ..extraction.metadata_extractor import MetadataExtractor
from ..normalization.metadata_normalizer import MetadataNormalizer
from ..validation.metadata_validator import MetadataValidator
from ..enrichment.metadata_enricher import MetadataEnricher
from ..repositories.metadata_repository import MetadataRepository


class MetadataPipeline:
    """Application service. Dependencies are injected so other Atlas components remain decoupled."""
    def __init__(self, metadata_extractor: MetadataExtractor, entity_extractor: EntityExtractor,
                 normalizer: MetadataNormalizer, validator: MetadataValidator | None = None,
                 enricher: MetadataEnricher | None = None, repository: MetadataRepository | None = None):
        self.metadata_extractor = metadata_extractor
        self.entity_extractor = entity_extractor
        self.normalizer = normalizer
        self.validator = validator or MetadataValidator()
        self.enricher = enricher or MetadataEnricher()
        self.repository = repository

    async def process(self, document: ParsedDocument) -> DocumentMetadata:
        raw = await self.metadata_extractor.extract(document)
        entities = await self.entity_extractor.extract(document)
        metadata = DocumentMetadata(
            document_id=document.document_id,
            source=document.source,
            title=document.title,
            publisher=document.publisher,
            publication_date=document.published_at,
            version=document.version,
            language=document.language,
            authors=document.authors,
            license=document.license,
            entities=entities,
            **{k: v for k, v in raw.items() if k not in {
                "title", "publisher", "publication_date", "version", "language", "authors", "license"
            }},
        )
        metadata = await self.normalizer.normalize(metadata)
        metadata = await self.enricher.enrich(metadata)
        metadata = self.validator.validate(metadata)
        if self.repository:
            await self.repository.save(metadata)
        return metadata
