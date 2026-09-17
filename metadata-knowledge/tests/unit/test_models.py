import pytest
from pydantic import ValidationError
from metadata_knowledge.domain.models import Entity
from metadata_knowledge.domain.enums import EntityType


def test_entity_confidence_is_bounded():
    with pytest.raises(ValidationError):
        Entity(name="test", entity_type=EntityType.DRUG, confidence=1.1)
