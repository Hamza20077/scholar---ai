from django.conf import settings
from django.db import models


class StudyDocument(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="study_documents")
    title = models.CharField(max_length=180)
    file = models.FileField(upload_to="documents/%Y/%m/")
    sha256 = models.CharField(max_length=64)
    file_size_bytes = models.PositiveBigIntegerField(default=0)
    page_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["owner", "sha256"], name="unique_user_document_hash")]

    def __str__(self) -> str:
        return self.title


class TextChunk(models.Model):
    document = models.ForeignKey(StudyDocument, on_delete=models.CASCADE, related_name="chunks")
    page_number = models.PositiveIntegerField()
    ordinal = models.PositiveIntegerField()
    text = models.TextField()

    class Meta:
        ordering = ["document_id", "page_number", "ordinal"]
        indexes = [models.Index(fields=["document", "page_number"])]


class StudyQuestion(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="study_questions")
    question = models.CharField(max_length=1000)
    answer = models.TextField()
    citations = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class AIUsage(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ai_usage")
    created_at = models.DateTimeField(auto_now_add=True)


class StudyArtifact(models.Model):
    class Kind(models.TextChoices):
        SUMMARY = "summary", "Summary"
        QUIZ = "quiz", "Practice quiz"

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="study_artifacts")
    document = models.ForeignKey(StudyDocument, on_delete=models.CASCADE, related_name="artifacts")
    kind = models.CharField(max_length=12, choices=Kind.choices)
    title = models.CharField(max_length=180)
    content = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
