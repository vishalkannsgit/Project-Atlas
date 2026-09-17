from enum import Enum


class EntityType(str, Enum):
    DISEASE = "DISEASE"
    DRUG = "DRUG"
    PROCEDURE = "PROCEDURE"
    SYMPTOM = "SYMPTOM"
    ORGANIZATION = "ORGANIZATION"
    SPECIALTY = "SPECIALTY"
    GUIDELINE = "GUIDELINE"
    LAB_TEST = "LAB_TEST"
    MEDICAL_DEVICE = "MEDICAL_DEVICE"


class DocumentType(str, Enum):
    RESEARCH_ARTICLE = "research_article"
    GUIDELINE = "guideline"
    SOP = "sop"
    ADVISORY = "advisory"
    REPORT = "report"
    WEB_PAGE = "web_page"
    UNKNOWN = "unknown"
