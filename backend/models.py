from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.config import MAX_TEXT


class Model(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')


class ResumeFileInfo(Model):
    format: Literal['PDF', 'DOCX', 'TXT']
    text_chars: int = Field(ge=0)
    section_names: list[str] = Field(default_factory=list)
    tables: int | None = None
    columns: bool | None = None
    text_boxes: int | None = None
    header_footer_contact: bool | None = None
    formatting_issues: list[str] = Field(default_factory=list)


class CandidateProfile(Model):
    name: str = ''
    email: str = ''
    summary: str = ''
    education: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    normalized_skills: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    experience: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    possible_roles: list[str] = Field(default_factory=list)
    experience_years: float | None = Field(default=None, ge=0, le=70)
    sections: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    document: ResumeFileInfo | None = None


class ResumeAnalysisRequest(Model):
    candidate: CandidateProfile


class ResumeInsight(Model):
    statement_id: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=120)
    issue: str = Field(min_length=1, max_length=600)
    rewrite: str = Field(default='', max_length=1000)
    question: str = Field(default='', max_length=400)


class ResumeInsights(Model):
    summary: str = Field(min_length=1, max_length=800)
    strengths: list[str] = Field(default_factory=list, max_length=3)
    improvements: list[ResumeInsight] = Field(min_length=1, max_length=2)


class JobInput(Model):
    company: str = ''
    role: str = ''
    location: str = ''
    job_url: str = ''
    job_description: str = Field(default='', max_length=MAX_TEXT)
    source: str = 'User supplied'
    posted_at: str = ''
    valid_through: str = ''


class JobProfile(JobInput):
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    experience_required: str = ''
    min_experience_years: float | None = None
    education_required: str = ''
    tools: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    seniority: str = 'Unknown'
    warnings: list[str] = Field(default_factory=list)


class MatchRequest(Model):
    candidate: CandidateProfile
    job: JobProfile


class MatchResult(Model):
    score: float | None = None
    components: dict[str, float | None] = Field(default_factory=dict)
    weights_used: dict[str, float] = Field(default_factory=dict)
    evidence_coverage: float = 0
    strong_matches: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    relevant_projects: list[dict] = Field(default_factory=list)
    explanation: str = ''
    warnings: list[str] = Field(default_factory=list)


class JobSearchRequest(Model):
    candidate: CandidateProfile
    target_role: str = Field(default='', max_length=150)
    company: str = ''
    location: str = ''
    job_type: str = ''
    limit: int = Field(default=5, ge=1, le=5)


class Contact(Model):
    name: str = ''
    role: str = ''
    company: str = ''
    department: str = ''
    location: str = ''
    profile_url: str = ''
    source: str = ''
    evidence: str = ''
    email: str = ''
    email_status: Literal['Verified', 'Likely', 'Public', 'Inferred', 'Unknown'] = 'Unknown'
    email_source: str = ''
    confidence: float | None = None
    email_checks: dict = Field(default_factory=dict)
    inferred_emails: list[str] = Field(default_factory=list)
    relevance_score: float = 0
    relevance_components: dict[str, float] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class ContactRequest(Model):
    company: str = Field(min_length=2)
    target_role: str = Field(min_length=2)
    company_domain: str = ''
    person: Contact | None = None
    find_email: bool = False
    allow_patterns: bool = False
    limit: int = Field(default=5, ge=1, le=5)


class EmailRequest(MatchRequest):
    employee: Contact
    purpose: Literal['Networking', 'Referral', 'Job application'] = 'Networking'
    company_context: str = Field(default='', max_length=3000)
    tone: Literal['Professional', 'Concise', 'Friendly', 'Technical'] = 'Professional'


class GeneratedEmail(Model):
    subject: str = Field(min_length=1, max_length=150)
    body: str = Field(min_length=1, max_length=4000)
