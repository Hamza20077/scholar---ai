import os

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from .forms import AskQuestionForm, DeleteAccountForm, SignUpForm, UploadDocumentForm
from .models import StudyArtifact, StudyDocument, StudyQuestion, TextChunk
from .services.ai import AIService, AIServiceError
from .services.documents import DocumentError, extract_pdf, make_chunks, sha256_file
from .services.retrieval import retrieve


@require_GET
def health(request):
    return JsonResponse({"status": "ok"})


@require_GET
def privacy(request):
    return render(request, "study/privacy.html", {"support_email": settings.SUPPORT_EMAIL})


@require_GET
def service_worker(request):
    response = render(request, "study/service-worker.js", content_type="application/javascript")
    response["Service-Worker-Allowed"] = "/"
    response["Cache-Control"] = "no-cache"
    return response


def signup(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = SignUpForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        return redirect("dashboard")
    return render(request, "study/signup.html", {"form": form})


@login_required
def dashboard(request):
    documents = StudyDocument.objects.filter(owner=request.user)
    return render(request, "study/dashboard.html", {
        "documents": documents,
        "artifacts": StudyArtifact.objects.filter(owner=request.user)[:6],
        "questions": StudyQuestion.objects.filter(owner=request.user)[:6],
        "ask_form": AskQuestionForm(user=request.user),
        "has_api_key": bool(os.environ.get("OPENAI_API_KEY", "").strip()),
        "max_upload_mb": settings.MAX_UPLOAD_MB,
    })


@login_required
@require_POST
def upload_document(request):
    form = UploadDocumentForm(request.POST, request.FILES)
    if not form.is_valid():
        return render(request, "study/dashboard.html", _dashboard_context(request, upload_form=form), status=400)
    upload = form.cleaned_data["file"]
    try:
        if StudyDocument.objects.filter(owner=request.user).count() >= settings.MAX_DOCUMENTS_PER_USER:
            form.add_error(None, f"This account has reached its {settings.MAX_DOCUMENTS_PER_USER}-document limit.")
            return render(request, "study/dashboard.html", _dashboard_context(request, upload_form=form), status=400)
        current_storage = sum(StudyDocument.objects.filter(owner=request.user).values_list("file_size_bytes", flat=True))
        storage_limit = settings.MAX_TOTAL_STORAGE_MB_PER_USER * 1024 * 1024
        if current_storage + upload.size > storage_limit:
            form.add_error("file", "This upload would exceed your account’s storage limit.")
            return render(request, "study/dashboard.html", _dashboard_context(request, upload_form=form), status=400)
        digest = sha256_file(upload)
        pages = extract_pdf(upload)
        if StudyDocument.objects.filter(owner=request.user, sha256=digest).exists():
            form.add_error("file", "You have already uploaded this document.")
            return render(request, "study/dashboard.html", _dashboard_context(request, upload_form=form), status=400)
        document = StudyDocument(owner=request.user, title=form.cleaned_data["title"].strip(), sha256=digest, file_size_bytes=upload.size, page_count=len(pages))
        try:
            with transaction.atomic():
                document.file.save(upload.name, upload, save=False)
                document.save()
                TextChunk.objects.bulk_create([
                    TextChunk(document=document, page_number=page.number, ordinal=ordinal, text=chunk)
                    for page in pages
                    for ordinal, chunk in enumerate(make_chunks(page), start=1)
                ])
        except Exception:
            if document.file:
                default_storage.delete(document.file.name)
            raise
    except DocumentError as exc:
        form.add_error("file", str(exc))
        return render(request, "study/dashboard.html", _dashboard_context(request, upload_form=form), status=400)
    except IntegrityError:
        form.add_error("file", "You have already uploaded this document.")
        return render(request, "study/dashboard.html", _dashboard_context(request, upload_form=form), status=400)
    messages.success(request, f"“{document.title}” is ready to study.")
    return redirect("dashboard")


def _dashboard_context(request, **extra):
    return {
        "documents": StudyDocument.objects.filter(owner=request.user),
        "artifacts": StudyArtifact.objects.filter(owner=request.user)[:6],
        "questions": StudyQuestion.objects.filter(owner=request.user)[:6],
        "ask_form": AskQuestionForm(user=request.user),
        "has_api_key": bool(os.environ.get("OPENAI_API_KEY", "").strip()),
        "max_upload_mb": settings.MAX_UPLOAD_MB,
        **extra,
    }


@login_required
@require_POST
def ask_question(request):
    form = AskQuestionForm(request.POST, user=request.user)
    if not form.is_valid():
        messages.error(request, "Choose at least one of your documents and enter a question.")
        return redirect("dashboard")
    question = form.cleaned_data["question"].strip()
    documents = list(form.cleaned_data["documents"])
    sources = retrieve(question, [doc.pk for doc in documents], request.user.pk)
    if not sources:
        messages.warning(request, "I couldn’t find relevant passages in those notes. Try using terms from the material.")
        return redirect("dashboard")
    try:
        service = AIService()
        AIService.reserve_usage(request.user.pk)
        answer = service.answer(question, sources)
    except AIServiceError as exc:
        messages.error(request, str(exc))
        return redirect("dashboard")
    citation_rows = [
        {"marker": f"S{index}", "document_title": source["document_title"], "page": source["page"], "excerpt": source["text"]}
        for index, source in enumerate(sources, start=1)
    ]
    StudyQuestion.objects.create(owner=request.user, question=question, answer=answer, citations=citation_rows)
    return render(request, "study/answer.html", {"question": question, "answer": answer, "citations": citation_rows})


def _document_sources(document: StudyDocument, limit: int = 24) -> list[dict]:
    return [
        {"document_id": document.pk, "document_title": document.title, "page": chunk.page_number, "text": chunk.text}
        for chunk in TextChunk.objects.filter(document=document).order_by("page_number", "ordinal")[:limit]
    ]


@login_required
@require_POST
def generate_artifact(request, document_id: int, kind: str):
    document = get_object_or_404(StudyDocument, pk=document_id, owner=request.user)
    if kind not in {StudyArtifact.Kind.SUMMARY, StudyArtifact.Kind.QUIZ}:
        return redirect("dashboard")
    sources = _document_sources(document)
    if not sources:
        messages.error(request, "This document has no extracted text to study.")
        return redirect("dashboard")
    try:
        service = AIService()
        AIService.reserve_usage(request.user.pk)
        if kind == StudyArtifact.Kind.SUMMARY:
            content = {"text": service.summarize(sources)}
            title = f"Summary: {document.title}"
        else:
            questions = service.make_quiz(sources, count=5)
            content = {"questions": questions}
            title = f"Practice quiz: {document.title}"
    except AIServiceError as exc:
        messages.error(request, str(exc))
        return redirect("dashboard")
    artifact = StudyArtifact.objects.create(owner=request.user, document=document, kind=kind, title=title, content=content)
    return redirect("artifact_detail", artifact_id=artifact.pk)


@login_required
def artifact_detail(request, artifact_id: int):
    artifact = get_object_or_404(StudyArtifact, pk=artifact_id, owner=request.user)
    return render(request, "study/artifact.html", {"artifact": artifact})


@login_required
@require_POST
def delete_document(request, document_id: int):
    document = get_object_or_404(StudyDocument, pk=document_id, owner=request.user)
    if document.file:
        default_storage.delete(document.file.name)
    title = document.title
    document.delete()
    messages.success(request, f"“{title}” and its saved study materials were deleted.")
    return redirect("dashboard")


@login_required
@require_POST
def delete_artifact(request, artifact_id: int):
    artifact = get_object_or_404(StudyArtifact, pk=artifact_id, owner=request.user)
    artifact.delete()
    messages.success(request, "Study material deleted.")
    return redirect("dashboard")


@login_required
@require_POST
def delete_account(request):
    form = DeleteAccountForm(request.POST)
    if form.is_valid() and request.user.check_password(form.cleaned_data["password"]):
        for document in StudyDocument.objects.filter(owner=request.user):
            if document.file:
                default_storage.delete(document.file.name)
        user = request.user
        logout(request)
        user.delete()
        messages.success(request, "Your account and saved study data have been deleted.")
        return redirect("login")
    if form.is_valid():
        form.add_error("password", "The password did not match your account.")
    return render(request, "study/dashboard.html", _dashboard_context(request, delete_form=form), status=400)
