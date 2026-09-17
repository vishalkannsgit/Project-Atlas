from fastapi import APIRouter, HTTPException
from ..domain.models import ParsedDocument
from ..pipeline.metadata_pipeline import MetadataPipeline
from ..repositories.metadata_repository import InMemoryMetadataRepository
from ..extraction.rule_based import RuleBasedMetadataExtractor, RuleBasedEntityExtractor
from ..normalization.metadata_normalizer import DefaultMetadataNormalizer
from .schemas import ProcessResponse

router = APIRouter(prefix="/api/v1/metadata", tags=["metadata"])
_repository = InMemoryMetadataRepository()
_pipeline = MetadataPipeline(
    metadata_extractor=RuleBasedMetadataExtractor(),
    entity_extractor=RuleBasedEntityExtractor(),
    normalizer=DefaultMetadataNormalizer(),
    repository=_repository,
)


@router.post("/process", response_model=ProcessResponse)
async def process_document(document: ParsedDocument) -> ProcessResponse:
    return ProcessResponse(metadata=await _pipeline.process(document))


@router.get("/{document_id}", response_model=ProcessResponse)
async def get_metadata(document_id: str) -> ProcessResponse:
    metadata = await _repository.get(document_id)
    if metadata is None:
        raise HTTPException(status_code=404, detail="Metadata not found")
    return ProcessResponse(metadata=metadata)


@router.get("/{document_id}/entities")
async def get_entities(document_id: str):
    metadata = await _repository.get(document_id)
    if metadata is None:
        raise HTTPException(status_code=404, detail="Metadata not found")
    return {"document_id": document_id, "entities": metadata.entities}
