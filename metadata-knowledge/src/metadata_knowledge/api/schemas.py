from pydantic import BaseModel
from ..domain.models import ParsedDocument, DocumentMetadata


class ProcessRequest(ParsedDocument):
    pass


class ProcessResponse(BaseModel):
    metadata: DocumentMetadata
