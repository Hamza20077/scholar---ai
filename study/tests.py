from io import BytesIO
import hashlib
import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from pypdf import PdfWriter

from .models import StudyArtifact, StudyDocument, StudyQuestion, TextChunk
from .services.ai import AIService, AIServiceError
from .services.documents import DocumentError, ExtractedPage, extract_pdf, make_chunks
from .services.retrieval import retrieve

User = get_user_model()


class DocumentServiceTests(TestCase):
    def test_chunking_keeps_all_text_and_overlaps(self):
        text = "alpha " * 350
        chunks = make_chunks(ExtractedPage(number=1, text=text))
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(chunks))
        self.assertIn(chunks[0][-40:], chunks[1])

    def test_scanned_pdf_is_rejected_with_clear_error(self):
        output = BytesIO()
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        writer.write(output)
        upload = SimpleUploadedFile("scan.pdf", output.getvalue(), content_type="application/pdf")
        with self.assertRaisesRegex(DocumentError, "No selectable text"):
            extract_pdf(upload)

    def test_non_pdf_is_rejected(self):
        upload = SimpleUploadedFile("notes.pdf", b"not a PDF", content_type="application/pdf")
        with self.assertRaisesRegex(DocumentError, "valid PDF"):
            extract_pdf(upload)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class StudyFlowTests(TestCase):
    def setUp(self):
        self.temp_media = tempfile.TemporaryDirectory()
        self.settings = override_settings(MEDIA_ROOT=self.temp_media.name)
        self.settings.enable()
        self.user = User.objects.create_user(username="student", password="StrongPassword123!")
        self.other = User.objects.create_user(username="another", password="StrongPassword123!")
        self.client.force_login(self.user)
        self.document = StudyDocument.objects.create(
            owner=self.user, title="Networks", file="documents/networks.pdf", sha256="a" * 64, page_count=2,
        )
        TextChunk.objects.create(document=self.document, page_number=1, ordinal=1, text="The transport layer provides reliable delivery using TCP.")
        TextChunk.objects.create(document=self.document, page_number=2, ordinal=1, text="IP routes packets between networks.")

    def tearDown(self):
        self.settings.disable()
        self.temp_media.cleanup()

    def test_dashboard_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_student_can_create_an_account(self):
        self.client.logout()
        response = self.client.post(reverse("signup"), {
            "username": "newstudent", "email": "student@example.test",
            "password1": "AnUncommonPassphrase!2026", "password2": "AnUncommonPassphrase!2026",
        })
        self.assertRedirects(response, reverse("dashboard"))
        self.assertTrue(User.objects.filter(username="newstudent").exists())

    def test_dashboard_lists_only_current_users_documents(self):
        StudyDocument.objects.create(owner=self.other, title="Private", file="private.pdf", sha256="b" * 64)
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "Networks")
        self.assertNotContains(response, "Private")

    def test_upload_extracts_and_indexes_text(self):
        payload = SimpleUploadedFile("lecture.pdf", b"%PDF-1.4\nactual test file", content_type="application/pdf")
        with patch("study.views.extract_pdf", return_value=[ExtractedPage(1, "A lecture about recursion and functions.")]):
            response = self.client.post(reverse("upload_document"), {"title": "Algorithms", "file": payload})
        self.assertRedirects(response, reverse("dashboard"))
        doc = StudyDocument.objects.get(title="Algorithms", owner=self.user)
        self.assertEqual(doc.page_count, 1)
        self.assertTrue(doc.chunks.filter(text__contains="recursion").exists())

    def test_duplicate_upload_is_rejected(self):
        content = b"%PDF-1.4\nactual test file"
        self.document.sha256 = hashlib.sha256(content).hexdigest()
        self.document.save(update_fields=["sha256"])
        payload = SimpleUploadedFile("networks.pdf", content, content_type="application/pdf")
        with patch("study.views.extract_pdf", return_value=[ExtractedPage(1, "Some notes")]):
            response = self.client.post(reverse("upload_document"), {"title": "Again", "file": payload})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(StudyDocument.objects.filter(owner=self.user).count(), 1)

    def test_question_uses_owned_chunks_and_persists_citations(self):
        with patch("study.views.AIService") as service_class:
            service_class.return_value.answer.return_value = "TCP provides reliable delivery [S1]."
            response = self.client.post(reverse("ask_question"), {"question": "How does TCP provide reliable delivery?", "documents": [self.document.pk]})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Networks, page 1")
        saved = StudyQuestion.objects.get(owner=self.user)
        self.assertEqual(saved.citations[0]["page"], 1)

    def test_question_without_relevant_text_does_not_call_ai(self):
        with patch("study.views.AIService") as service_class:
            response = self.client.post(reverse("ask_question"), {"question": "What is quantum tunneling?", "documents": [self.document.pk]})
        self.assertRedirects(response, reverse("dashboard"))
        service_class.assert_not_called()
        self.assertFalse(StudyQuestion.objects.exists())

    def test_generate_summary_persists_artifact(self):
        with patch("study.views.AIService") as service_class:
            service_class.return_value.summarize.return_value = "TCP supports reliable delivery."
            response = self.client.post(reverse("generate_artifact", args=[self.document.pk, "summary"]))
        artifact = StudyArtifact.objects.get(owner=self.user, kind="summary")
        self.assertRedirects(response, reverse("artifact_detail", args=[artifact.pk]))
        self.assertEqual(artifact.content["text"], "TCP supports reliable delivery.")

    def test_generate_quiz_persists_questions(self):
        questions = [{"question": "What does TCP provide?", "options": ["Reliable delivery", "Routing", "Encryption", "Compression"], "answer_index": 0, "explanation": "TCP supports reliable delivery.", "source": "S1"}] * 5
        with patch("study.views.AIService") as service_class:
            service_class.return_value.make_quiz.return_value = questions
            response = self.client.post(reverse("generate_artifact", args=[self.document.pk, "quiz"]))
        artifact = StudyArtifact.objects.get(owner=self.user, kind="quiz")
        self.assertRedirects(response, reverse("artifact_detail", args=[artifact.pk]))
        detail = self.client.get(reverse("artifact_detail", args=[artifact.pk]))
        self.assertContains(detail, "Check my answers")

    def test_other_user_cannot_view_or_delete_document(self):
        self.client.force_login(self.other)
        response = self.client.post(reverse("delete_document", args=[self.document.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(StudyDocument.objects.filter(pk=self.document.pk).exists())

    def test_health_endpoint(self):
        response = self.client.get(reverse("health"))
        self.assertEqual(response.json(), {"status": "ok"})

    def test_privacy_page_and_service_worker(self):
        self.assertEqual(self.client.get(reverse("privacy")).status_code, 200)
        response = self.client.get(reverse("service_worker"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Service-Worker-Allowed"], "/")

    def test_account_deletion_requires_password_and_confirmation(self):
        wrong = self.client.post(reverse("delete_account"), {"confirmation": "DELETE", "password": "wrong"})
        self.assertEqual(wrong.status_code, 400)
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())
        deleted = self.client.post(reverse("delete_account"), {"confirmation": "DELETE", "password": "StrongPassword123!"})
        self.assertRedirects(deleted, reverse("login"))
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())
        self.assertFalse(StudyDocument.objects.filter(pk=self.document.pk).exists())

    def test_retrieval_ranks_matching_page_first(self):
        sources = retrieve("TCP reliable delivery", [self.document.pk], self.user.pk)
        self.assertTrue(sources)
        self.assertEqual(sources[0]["page"], 1)


class AIServiceValidationTests(TestCase):
    def test_provider_auth_error_message_is_actionable(self):
        self.assertIn("valid, active OpenAI API key", AIService._status_error_message(401))

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    def test_quiz_rejects_invalid_provider_shape(self):
        service = AIService()
        with patch.object(service, "_complete", return_value='{"questions":[{"question":"Q?","options":["A"],"answer_index":0,"explanation":"E","source":"S1"}]}'):
            with self.assertRaises(AIServiceError):
                service.make_quiz([], 1)

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    def test_quiz_accepts_valid_grounded_questions(self):
        service = AIService()
        payload = '{"questions":[{"question":"Q?","options":["A","B","C","D"],"answer_index":0,"explanation":"The notes say this.","source":"S1"}]}'
        with patch.object(service, "_complete", return_value=payload):
            questions = service.make_quiz([{"document_title": "Notes", "page": 1, "text": "A note."}], 1)
        self.assertEqual(questions[0]["source"], "S1")

    @override_settings(AI_REQUESTS_PER_HOUR=1)
    def test_ai_request_quota_is_enforced_per_account(self):
        user = User.objects.create_user(username="quota", password="StrongPassword123!")
        AIService.reserve_usage(user.pk)
        with self.assertRaisesRegex(AIServiceError, "limit of 1"):
            AIService.reserve_usage(user.pk)
