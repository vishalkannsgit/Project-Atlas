import pytest
from metadata_knowledge.domain.models import ParsedDocument
from metadata_knowledge.extraction.rule_based import RuleBasedMetadataExtractor, RuleBasedEntityExtractor
from metadata_knowledge.normalization.metadata_normalizer import DefaultMetadataNormalizer
from metadata_knowledge.pipeline.metadata_pipeline import MetadataPipeline


@pytest.mark.asyncio
async def test_pipeline_extracts_metadata_and_entities():
    pipeline = MetadataPipeline(RuleBasedMetadataExtractor(), RuleBasedEntityExtractor(), DefaultMetadataNormalizer())
    result = await pipeline.process(ParsedDocument(
        document_id="PMC-1", source="pubmed_central", title="Type 2 Diabetes Guideline",
        text="Clinical guideline about Type 2 diabetes and insulin. HbA1c is monitored.", file_type="xml",
        language="en", publisher="NIH"
    ))
    assert result.document_id == "PMC-1"
    assert result.document_type.value == "guideline"
    assert any(e.entity_type.value == "DISEASE" for e in result.entities)
    assert 0 <= result.confidence_score <= 1
