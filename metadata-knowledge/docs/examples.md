# Python integration example

```python
from metadata_knowledge.domain.models import ParsedDocument
from metadata_knowledge.extraction.rule_based import (
    RuleBasedMetadataExtractor,
    RuleBasedEntityExtractor,
)
from metadata_knowledge.normalization.metadata_normalizer import DefaultMetadataNormalizer
from metadata_knowledge.pipeline.metadata_pipeline import MetadataPipeline

pipeline = MetadataPipeline(
    metadata_extractor=RuleBasedMetadataExtractor(),
    entity_extractor=RuleBasedEntityExtractor(),
    normalizer=DefaultMetadataNormalizer(),
)

result = await pipeline.process(ParsedDocument(
    document_id="doc-001",
    source="cdc",
    title="Asthma advisory",
    text="Public health advisory discussing asthma.",
    file_type="pdf",
))
```
