from django.contrib import admin

from .models import AIUsage, StudyArtifact, StudyDocument, StudyQuestion, TextChunk


@admin.register(StudyDocument)
class StudyDocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "page_count", "created_at")
    search_fields = ("title", "owner__username")
    readonly_fields = ("sha256", "page_count", "created_at")


admin.site.register(StudyArtifact)
admin.site.register(StudyQuestion)
admin.site.register(AIUsage)
admin.site.register(TextChunk)
