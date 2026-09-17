class ConfidenceScorer:
    def calculate(self, *, extraction_confidence: float, metadata_completeness: float, source_reliability: float) -> float:
        values = (extraction_confidence, metadata_completeness, source_reliability)
        if any(not 0 <= value <= 1 for value in values):
            raise ValueError("all confidence inputs must be between 0 and 1")
        return round(extraction_confidence * 0.5 + metadata_completeness * 0.3 + source_reliability * 0.2, 4)

    @staticmethod
    def completeness(metadata: object) -> float:
        fields = ("title", "publisher", "publication_date", "language", "document_type", "license")
        present = sum(bool(getattr(metadata, field, None)) for field in fields)
        return present / len(fields)
