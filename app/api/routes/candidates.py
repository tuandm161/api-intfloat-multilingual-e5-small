"""Candidate validation and human review API routes."""

from fastapi import APIRouter

from app.api.dependencies import DbSession, SettingsDependency
from app.core.enums import CandidateStatus, ErrorCode, QuestionStatus, QuestionType
from app.core.errors import AppError
from app.core.responses import success_response
from app.db.models.question import Question
from app.modules.audit.service import AuditService
from app.modules.embeddings.vector_index import embed_question
from app.modules.normalization.text_normalizer import TextNormalizer
from app.modules.paraphrase.schemas import CandidateEdit, ReviewRequest
from app.modules.paraphrase.service import ParaphraseService, candidate_to_dict
from app.modules.questions.service import QuestionService
from app.modules.validation.rules import EDITED_REVALIDATION_REQUIRED
from app.modules.validation.service import ValidationService

router = APIRouter(tags=["candidates"])


@router.post("/paraphrase-jobs/{job_id}/validate")
def validate_job(job_id: str, db: DbSession, settings: SettingsDependency) -> dict:
    return success_response(ValidationService(db, settings).validate_job(job_id))


@router.get("/paraphrase-candidates/{candidate_id}")
def get_candidate(candidate_id: str, db: DbSession) -> dict:
    return success_response(
        candidate_to_dict(ParaphraseService(db).get_candidate_or_fail(candidate_id))
    )


@router.post("/paraphrase-candidates/{candidate_id}/validate")
def validate_candidate(
    candidate_id: str, db: DbSession, settings: SettingsDependency
) -> dict:
    return success_response(
        ValidationService(db, settings).validate_candidate(candidate_id)
    )


@router.put("/paraphrase-candidates/{candidate_id}")
def edit_candidate(candidate_id: str, payload: CandidateEdit, db: DbSession) -> dict:
    service = ParaphraseService(db)
    candidate = service.get_candidate_or_fail(candidate_id)
    if candidate.status == CandidateStatus.SAVED.value:
        raise AppError(ErrorCode.VALIDATION_ERROR, "Không thể chỉnh sửa câu đã được lưu")
    before = candidate_to_dict(candidate)
    candidate.candidate_stem = TextNormalizer.normalize_for_display(payload.candidateStem)
    candidate.normalized_candidate_stem = TextNormalizer.normalize_for_comparison(
        payload.candidateStem
    )
    candidate.semantic_similarity_to_source = None
    candidate.lexical_difference_from_source = None
    candidate.duplicate_max_similarity = None
    candidate.duplicate_question_id = None
    candidate.duplicate_question_stem_snapshot = None
    candidate.label = None
    candidate.warnings = [EDITED_REVALIDATION_REQUIRED]
    candidate.status = CandidateStatus.GENERATED.value
    AuditService(db).log(
        "ParaphraseCandidate",
        candidate.id,
        "PARAPHRASE_CANDIDATE_EDITED",
        actor="demo-user",
        before=before,
        after=candidate_to_dict(candidate),
    )
    db.commit()
    return success_response(candidate_to_dict(candidate))


@router.post("/paraphrase-candidates/{candidate_id}/approve")
def approve_candidate(candidate_id: str, payload: ReviewRequest, db: DbSession) -> dict:
    candidate = ParaphraseService(db).get_candidate_or_fail(candidate_id)
    if candidate.status not in {
        CandidateStatus.VALIDATED.value,
        CandidateStatus.NEED_REVIEW.value,
    } or not candidate.label:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            "Câu diễn đạt lại phải được kiểm định trước khi duyệt",
        )
    before = candidate_to_dict(candidate)
    candidate.status = CandidateStatus.APPROVED.value
    candidate.reviewer_notes = payload.reviewerNotes
    AuditService(db).log(
        "ParaphraseCandidate",
        candidate.id,
        "PARAPHRASE_CANDIDATE_APPROVED",
        actor="demo-user",
        before=before,
        after=candidate_to_dict(candidate),
    )
    db.commit()
    return success_response({"candidateId": candidate.id, "status": candidate.status})


@router.post("/paraphrase-candidates/{candidate_id}/reject")
def reject_candidate(candidate_id: str, payload: ReviewRequest, db: DbSession) -> dict:
    candidate = ParaphraseService(db).get_candidate_or_fail(candidate_id)
    if candidate.status == CandidateStatus.SAVED.value:
        raise AppError(ErrorCode.VALIDATION_ERROR, "Không thể từ chối câu đã được lưu")
    before = candidate_to_dict(candidate)
    candidate.status = CandidateStatus.REJECTED.value
    candidate.reviewer_notes = payload.reviewerNotes
    AuditService(db).log(
        "ParaphraseCandidate",
        candidate.id,
        "PARAPHRASE_CANDIDATE_REJECTED",
        actor="demo-user",
        before=before,
        after=candidate_to_dict(candidate),
    )
    db.commit()
    return success_response({"candidateId": candidate.id, "status": candidate.status})


@router.post("/paraphrase-candidates/{candidate_id}/save-as-question")
def save_as_question(
    candidate_id: str,
    db: DbSession,
    settings: SettingsDependency,
) -> dict:
    candidate = ParaphraseService(db).get_candidate_or_fail(candidate_id)
    if candidate.status != CandidateStatus.APPROVED.value:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            "Chỉ có thể lưu câu diễn đạt lại đã được duyệt",
        )
    source = QuestionService(db).get_or_fail(candidate.source_question_id)
    suffix = len(QuestionService(db).repository.children(source.id)) + 1
    new_id = f"{source.id}-P{suffix}"
    while db.get(Question, new_id):
        suffix += 1
        new_id = f"{source.id}-P{suffix}"
    question = Question(
        id=new_id,
        stem=candidate.candidate_stem,
        option_a=source.option_a,
        option_b=source.option_b,
        option_c=source.option_c,
        option_d=source.option_d,
        correct_answer=source.correct_answer,
        explanation=source.explanation,
        topic=source.topic,
        difficulty=source.difficulty,
        language=source.language,
        source_document=source.source_document,
        question_type=QuestionType.PARAPHRASE.value,
        status=QuestionStatus.APPROVED.value,
        parent_question_id=source.id,
        created_by="demo-user",
        reviewed_by="demo-user",
    )
    db.add(question)
    db.flush()
    embed_question(db, question, settings)
    candidate.status = CandidateStatus.SAVED.value
    AuditService(db).log(
        "Question",
        question.id,
        "QUESTION_PARAPHRASE_SAVED",
        actor="demo-user",
        after={"parentQuestionId": source.id, "candidateId": candidate.id},
    )
    db.commit()
    return success_response(
        {"candidateId": candidate.id, "newQuestionId": question.id, "status": candidate.status}
    )
